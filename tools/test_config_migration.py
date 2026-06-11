"""Regression checks for settings.json migration safety."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clipgen.core.config import ConfigManager


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")


def _load(path: Path) -> ConfigManager:
    return ConfigManager(str(path))


def test_legacy_config_keeps_user_data(tmp: Path) -> None:
    config_path = tmp / "settings.json"
    _write_json(
        config_path,
        {
            "language": "ru",
            "api_keys": [{"key": "KEEP_GEMINI_KEY", "active": True}],
            "openai_api_keys": [{"key": "KEEP_OPENAI_KEY", "active": True}],
            "proxy_string": "KEEP_PROXY",
            "hotkeys": [
                {
                    "combination": "Ctrl+F1",
                    "name": "KEEP_NAME",
                    "prompt": "KEEP_PROMPT",
                    "log_color": "#fff",
                }
            ],
            "transcription": {
                "enabled": True,
                "model": "base",
                "device": "cpu",
                "compute_type": "int8",
            },
        },
    )

    cm = _load(config_path)
    assert cm.config["api_keys"][0]["key"] == "KEEP_GEMINI_KEY"
    assert cm.config["openai_api_keys"][0]["key"] == "KEEP_OPENAI_KEY"
    assert cm.config["proxy_string"] == "KEEP_PROXY"
    assert cm.config["hotkeys"][0]["prompt"] == "KEEP_PROMPT"
    assert cm.config["hotkeys"][0]["transcription_strip_trailing_period"] is False
    assert cm.config["transcription"]["engine"] == "whisper"
    assert cm.config["transcription"]["whisper"]["model"] == "base"
    assert cm.config["transcription"]["whisper"]["device"] == "cpu"


def test_bad_section_types_do_not_reset_secrets(tmp: Path) -> None:
    config_path = tmp / "settings.json"
    _write_json(
        config_path,
        {
            "api_keys": [{"key": "KEEP_GEMINI_KEY", "active": True}],
            "openai_api_keys": [{"key": "KEEP_OPENAI_KEY", "active": True}],
            "proxy_string": "KEEP_PROXY",
            "hotkeys": "bad-hotkeys-section",
            "transcription": "bad-transcription-section",
        },
    )

    cm = _load(config_path)
    assert cm.config["api_keys"][0]["key"] == "KEEP_GEMINI_KEY"
    assert cm.config["openai_api_keys"][0]["key"] == "KEEP_OPENAI_KEY"
    assert cm.config["proxy_string"] == "KEEP_PROXY"
    assert isinstance(cm.config["hotkeys"], list)
    assert isinstance(cm.config["transcription"], dict)
    assert not list(tmp.glob("settings.corrupt.*.json.bak"))


def test_corrupt_json_is_backed_up(tmp: Path) -> None:
    config_path = tmp / "settings.json"
    config_path.write_text('{"api_keys": [{"key": "KEEP"', encoding="utf-8")

    cm = _load(config_path)
    assert "hotkeys" in cm.config
    backups = list(tmp.glob("settings.corrupt.*.json.bak"))
    assert len(backups) == 1
    assert "KEEP" in backups[0].read_text(encoding="utf-8")


def run_all() -> None:
    tests = (
        test_legacy_config_keeps_user_data,
        test_bad_section_types_do_not_reset_secrets,
        test_corrupt_json_is_backed_up,
    )
    for test in tests:
        with tempfile.TemporaryDirectory(prefix="clipgen-config-migration-") as tmp_dir:
            test(Path(tmp_dir))


def main() -> int:
    run_all()
    print("config migration checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
