"""Validate that a ClipGen binary release directory is safe to publish."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BLOCKED_NAMES = {
    "settings.json",
    "fault_log.txt",
    "error_log.txt",
    "startup_error.txt",
    "transcription_diagnostics.txt",
    "build.log",
}

TEXT_SUFFIXES = {
    ".cfg",
    ".conf",
    ".env",
    ".ini",
    ".json",
    ".log",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
}

SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"sk-or-v1-[0-9A-Za-z]{20,}"),
    re.compile(r"sk-[0-9A-Za-z_-]{20,}"),
    re.compile(r'"proxy_string"\s*:\s*"(?!\s*")[^"]+"'),
]


def _is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES


def _scan_text_file(path: Path) -> list[str]:
    try:
        if path.stat().st_size > 5 * 1024 * 1024:
            return []
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return [f"cannot read: {exc}"]

    hits: list[str] = []
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            hits.append(f"matches secret pattern: {pattern.pattern}")
    return hits


def check_release_dir(target: Path, allow_models: bool = False) -> list[str]:
    problems: list[str] = []

    if not target.exists():
        return [f"release directory does not exist: {target}"]
    if not target.is_dir():
        return [f"release target is not a directory: {target}"]

    exe_path = target / "ClipGen.exe"
    if not exe_path.exists():
        problems.append("ClipGen.exe is missing")

    if not allow_models and (target / "Models").exists():
        problems.append("Models directory is present; do not ship local model cache by default")

    for path in target.rglob("*"):
        if path.name in BLOCKED_NAMES:
            problems.append(f"blocked local artifact present: {path.relative_to(target)}")
        if path.is_file() and _is_text_file(path):
            for hit in _scan_text_file(path):
                problems.append(f"{path.relative_to(target)}: {hit}")

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check a ClipGen release directory for local-only files and secrets."
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=str(ROOT / "dist"),
        help="Release directory to check. Defaults to ./dist.",
    )
    parser.add_argument(
        "--allow-models",
        action="store_true",
        help="Allow a Models directory in the release target.",
    )
    args = parser.parse_args(argv)

    target = Path(args.target).resolve()
    problems = check_release_dir(target, allow_models=args.allow_models)
    if problems:
        print(f"Release artifact check failed for {target}:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"Release artifact check passed for {target}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
