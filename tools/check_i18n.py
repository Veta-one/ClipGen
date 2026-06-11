"""Validate ClipGen language catalog consistency."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LANG_DIR = ROOT / "lang"


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else key
            result.update(_flatten(child, child_prefix))
        return result
    return {prefix: value}


def _contains_cyrillic(value: str) -> bool:
    return any("А" <= char <= "я" or char in "Ёё" for char in value)


def main() -> int:
    catalogs = {
        "en": json.loads((LANG_DIR / "en.json").read_text(encoding="utf-8")),
        "ru": json.loads((LANG_DIR / "ru.json").read_text(encoding="utf-8")),
    }
    flat = {language: _flatten(data) for language, data in catalogs.items()}

    ok = True
    for left, right in (("en", "ru"), ("ru", "en")):
        missing = sorted(set(flat[left]) - set(flat[right]))
        if missing:
            ok = False
            print(f"{right}.json is missing {len(missing)} keys:")
            for key in missing:
                print(f"  {key}")

    english_cyrillic = [
        (key, value)
        for key, value in flat["en"].items()
        if isinstance(value, str) and _contains_cyrillic(value)
    ]
    if english_cyrillic:
        ok = False
        print("en.json contains Cyrillic text:")
        for key, value in english_cyrillic:
            print(f"  {key}: {value}")

    if ok:
        print("i18n catalogs are consistent.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
