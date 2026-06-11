"""Update checker - checks GitHub releases for new versions."""

import json
import logging
import re
import threading
import urllib.request
from typing import Callable, Optional

logger = logging.getLogger('ClipGen')


_LANG_BLOCK_RE = re.compile(
    r"<!--\s*lang:([a-zA-Z-]+)\s*-->(.*?)<!--\s*/lang\s*-->",
    re.DOTALL | re.IGNORECASE,
)


def extract_notes_blocks(body: str) -> dict:
    """Return all language blocks from a release body as ``{code: text}``.

    Release bodies may carry several language variants wrapped in HTML
    comments, which GitHub hides on the rendered release page:

        <!-- lang:ru -->
        ...русский текст...
        <!-- /lang -->

        <!-- lang:en -->
        ...english text...
        <!-- /lang -->

    Anything outside the marked blocks (visible separators/headers for the
    GitHub page) is dropped. Returns an empty dict for releases published
    before this convention — callers must fall back to the raw body.
    """
    blocks: dict = {}
    if not body:
        return blocks
    for match in _LANG_BLOCK_RE.finditer(body):
        code = match.group(1).strip().lower()
        blocks.setdefault(code, match.group(2).strip())
    return blocks


def extract_localized_notes(body: str, lang_code: str) -> str:
    """Pick the release-notes block matching the UI language.

    Falls back to English, then to the first block, then to the unmodified
    body (releases without language markers must keep working).
    """
    if not body:
        return body
    blocks = extract_notes_blocks(body)
    if not blocks:
        return body
    code = (lang_code or "en").strip().lower()
    if code in blocks:
        return blocks[code]
    if "en" in blocks:
        return blocks["en"]
    return next(iter(blocks.values()))


def _parse_version(text: str) -> Optional[tuple]:
    """Parse '2.4.1' / 'v2.4.1' into a comparable tuple, or None."""
    try:
        return tuple(int(x) for x in text.strip().lstrip("vV").split("."))
    except (ValueError, AttributeError):
        return None


def select_releases(data: list, current_version: str) -> tuple:
    """Split a GitHub /releases payload into (latest, missed_history).

    ``latest`` is the highest-versioned published release dict (or None).
    ``missed_history`` lists ``(version, body)`` for every release the
    user has not seen yet — newer than ``current_version`` but older than
    ``latest`` — sorted newest first. Drafts and prereleases are ignored.
    """
    current = _parse_version(current_version) or ()
    published = []
    for release in data or []:
        if release.get("draft") or release.get("prerelease"):
            continue
        version = _parse_version(release.get("tag_name", ""))
        if version is None:
            continue
        published.append((version, release))
    if not published:
        return None, []

    published.sort(key=lambda item: item[0], reverse=True)
    latest_version, latest = published[0]
    history = [
        (".".join(map(str, version)), release.get("body", ""))
        for version, release in published[1:]
        if version > current
    ]
    return latest, history


class UpdateChecker(threading.Thread):
    """Background thread to check for updates on GitHub."""

    GITHUB_API_URL = "https://api.github.com/repos/Veta-one/ClipGen/releases?per_page=15"

    def __init__(
        self,
        current_version: str,
        skipped_version: str,
        found_callback: Callable[[str, str, str, list], None],
        not_found_callback: Callable[[], None],
        is_manual: bool = False
    ):
        """Initialize update checker.

        Args:
            current_version: Current app version (e.g., "2.1.0")
            skipped_version: Version user chose to skip
            found_callback: Called with (version, url, release_notes, history)
                when an update is found; ``history`` is a list of
                ``(version, body)`` for releases the user skipped over.
            not_found_callback: Called when no update or on manual check with no update
            is_manual: True if user manually triggered the check
        """
        super().__init__()
        self.current_version = current_version
        self.skipped_version = skipped_version
        self.found_callback = found_callback
        self.not_found_callback = not_found_callback
        self.is_manual = is_manual
        self.daemon = True

    def run(self) -> None:
        """Check for updates."""
        try:
            with urllib.request.urlopen(self.GITHUB_API_URL, timeout=5) as response:
                data = json.loads(response.read().decode())

            latest, history = select_releases(data, self.current_version)
            if latest is None:
                if self.is_manual:
                    self.not_found_callback()
                return

            latest_tag = latest.get("tag_name", "").replace("v", "")
            html_url = latest.get("html_url", "")
            body = latest.get("body", "")

            if self._is_newer_version(latest_tag):
                if self.is_manual or latest_tag != self.skipped_version:
                    self.found_callback(latest_tag, html_url, body, history)
                    return

            if self.is_manual:
                self.not_found_callback()

        except Exception as e:
            logger.warning("Update check failed: %s", e)
            if self.is_manual:
                self.not_found_callback()

    def _is_newer_version(self, latest: str) -> bool:
        """Compare version strings."""
        current_parts = _parse_version(self.current_version)
        latest_parts = _parse_version(latest)
        if current_parts is None or latest_parts is None:
            return False
        return latest_parts > current_parts
