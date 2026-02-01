"""Update checker - checks GitHub releases for new versions."""

import json
import threading
import urllib.request
from typing import Callable, Optional


class UpdateChecker(threading.Thread):
    """Background thread to check for updates on GitHub."""

    GITHUB_API_URL = "https://api.github.com/repos/Veta-one/ClipGen/releases/latest"

    def __init__(
        self,
        current_version: str,
        skipped_version: str,
        found_callback: Callable[[str, str, str], None],
        not_found_callback: Callable[[], None],
        is_manual: bool = False
    ):
        """Initialize update checker.

        Args:
            current_version: Current app version (e.g., "2.1.0")
            skipped_version: Version user chose to skip
            found_callback: Called with (version, url, release_notes) when update found
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

            latest_tag = data.get("tag_name", "").replace("v", "")
            html_url = data.get("html_url", "")
            body = data.get("body", "")

            if self._is_newer_version(latest_tag):
                if self.is_manual or latest_tag != self.skipped_version:
                    self.found_callback(latest_tag, html_url, body)
                    return

            if self.is_manual:
                self.not_found_callback()

        except Exception as e:
            print(f"Update check failed: {e}")
            if self.is_manual:
                self.not_found_callback()

    def _is_newer_version(self, latest: str) -> bool:
        """Compare version strings."""
        try:
            current_parts = [int(x) for x in self.current_version.split('.')]
            latest_parts = [int(x) for x in latest.split('.')]
            return latest_parts > current_parts
        except ValueError:
            return False
