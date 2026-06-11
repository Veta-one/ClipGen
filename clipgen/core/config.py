"""Configuration management - loading, saving, merging settings."""

import os
import json
import copy
import logging
import shutil
import time
from typing import Any, Dict, Optional

from .constants import DEFAULT_CONFIG

logger = logging.getLogger('ClipGen')


class ConfigManager:
    """Manages application configuration with automatic migration."""

    def __init__(self, config_path: str = "settings.json"):
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        """Load settings from file, migrating if necessary."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)

            config_changed = self._migrate_config()

            if config_changed:
                logger.info("Config migrated to new version")
                self.save()

        except FileNotFoundError:
            logger.info("Config file not found, creating default at %s", self.config_path)
            self.config = copy.deepcopy(DEFAULT_CONFIG)
            self.save()
        except json.JSONDecodeError as e:
            backup_path = self._backup_unreadable_config()
            logger.error(
                "Error parsing settings; reset to default. Backup: %s. Error: %s",
                backup_path or "failed",
                e,
            )
            self._reset_to_default()
        except Exception as e:
            backup_path = self._backup_unreadable_config()
            logger.error(
                "Error loading settings; reset to default. Backup: %s. Error: %s",
                backup_path or "failed",
                e,
            )
            self._reset_to_default()

    def _reset_to_default(self) -> None:
        """Reset config in memory and persist a clean default config."""
        self.config = copy.deepcopy(DEFAULT_CONFIG)
        self.save()

    def _backup_unreadable_config(self) -> Optional[str]:
        """Copy a broken config aside before replacing it with defaults."""
        if not os.path.exists(self.config_path):
            return None

        base_dir = os.path.dirname(os.path.abspath(self.config_path))
        base_name = os.path.basename(self.config_path)
        stem, ext = os.path.splitext(base_name)
        ext = ext or ".json"
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        backup_path = os.path.join(base_dir, f"{stem}.corrupt.{timestamp}{ext}.bak")

        try:
            shutil.copy2(self.config_path, backup_path)
            return backup_path
        except Exception:
            logger.exception("Failed to back up unreadable config")
            return None

    def _migrate_config(self) -> bool:
        """Migrate old config format to new. Returns True if changes were made."""
        config_changed = False
        if not isinstance(self.config, dict):
            raise ValueError("settings root must be a JSON object")

        # Add missing top-level keys
        for key, default_val in DEFAULT_CONFIG.items():
            if key not in self.config:
                self.config[key] = copy.deepcopy(default_val)
                config_changed = True

        # Migrate api_keys structure
        if not isinstance(self.config.get("api_keys"), list):
            self.config["api_keys"] = copy.deepcopy(DEFAULT_CONFIG.get("api_keys", []))
            config_changed = True
        else:
            for key_data in self.config["api_keys"]:
                if not isinstance(key_data, dict):
                    continue
                if "name" not in key_data:
                    key_data["name"] = ""
                    config_changed = True
                if "usage_timestamps" not in key_data:
                    key_data["usage_timestamps"] = []
                    config_changed = True

        # Migrate openai_api_keys structure
        if not isinstance(self.config.get("openai_api_keys"), list):
            self.config["openai_api_keys"] = copy.deepcopy(DEFAULT_CONFIG.get("openai_api_keys", []))
            config_changed = True
        else:
            for key_data in self.config["openai_api_keys"]:
                if not isinstance(key_data, dict):
                    continue
                if "name" not in key_data:
                    key_data["name"] = ""
                    config_changed = True
                if "usage_timestamps" not in key_data:
                    key_data["usage_timestamps"] = []
                    config_changed = True

        # Migrate hotkeys to add type and transcription fields
        if not isinstance(self.config.get("hotkeys"), list):
            self.config["hotkeys"] = copy.deepcopy(DEFAULT_CONFIG.get("hotkeys", []))
            config_changed = True
        else:
            valid_hotkeys = []
            for hotkey in self.config["hotkeys"]:
                if not isinstance(hotkey, dict):
                    config_changed = True
                    continue
                if "type" not in hotkey:
                    hotkey["type"] = "text_action"
                    config_changed = True
                if "transcription_language" not in hotkey:
                    hotkey["transcription_language"] = "auto"
                    config_changed = True
                if "transcription_initial_prompt" not in hotkey:
                    hotkey["transcription_initial_prompt"] = ""
                    config_changed = True
                if "transcription_strip_trailing_period" not in hotkey:
                    hotkey["transcription_strip_trailing_period"] = False
                    config_changed = True
                valid_hotkeys.append(hotkey)
            if len(valid_hotkeys) != len(self.config["hotkeys"]):
                self.config["hotkeys"] = valid_hotkeys or copy.deepcopy(DEFAULT_CONFIG.get("hotkeys", []))
                config_changed = True

        # Modular ASR engine migration + deep-merge of transcription section.
        if "transcription" in self.config and "transcription" in DEFAULT_CONFIG:
            if not isinstance(self.config.get("transcription"), dict):
                self.config["transcription"] = copy.deepcopy(DEFAULT_CONFIG["transcription"])
                config_changed = True

            if self._migrate_transcription_engines():
                config_changed = True

            default_tr = DEFAULT_CONFIG["transcription"]
            user_tr = self.config["transcription"]
            for key, default_val in default_tr.items():
                if key not in user_tr:
                    user_tr[key] = copy.deepcopy(default_val)
                    config_changed = True
            # Nested audio dict
            if isinstance(default_tr.get("audio"), dict):
                if not isinstance(user_tr.get("audio"), dict):
                    user_tr["audio"] = copy.deepcopy(default_tr["audio"])
                    config_changed = True
                else:
                    for k, v in default_tr["audio"].items():
                        if k not in user_tr["audio"]:
                            user_tr["audio"][k] = copy.deepcopy(v)
                            config_changed = True
            # Engine sub-dicts: ensure newly added keys propagate to existing users.
            for engine_key in ("whisper", "parakeet"):
                default_sub = default_tr.get(engine_key)
                if not isinstance(default_sub, dict):
                    continue
                user_sub = user_tr.get(engine_key)
                if not isinstance(user_sub, dict):
                    user_tr[engine_key] = copy.deepcopy(default_sub)
                    config_changed = True
                    continue
                for k, v in default_sub.items():
                    if k not in user_sub:
                        user_sub[k] = copy.deepcopy(v)
                        config_changed = True
            # Drop deprecated global initial_prompt — moved to per-hotkey only.
            if "initial_prompt" in user_tr:
                del user_tr["initial_prompt"]
                config_changed = True

        return config_changed

    # Whisper-specific keys that lived at the flat ``transcription.*`` level
    # before the modular ASR refactor and now belong under ``whisper.*``.
    _WHISPER_FLAT_KEYS = (
        "model",
        "device",
        "compute_type",
        "beam_size",
        "vad_filter",
        "vad_min_duration_seconds",
        "whisper_initial_prompt",
        "postprocess_prompt",
        "model_path_override",
        "isolate_inference_process",
    )

    def _migrate_transcription_engines(self) -> bool:
        """Migrate flat transcription config (pre-modular) to nested engines.

        Pre-refactor: Whisper-specific keys lived directly under
        ``config["transcription"]``. Post-refactor: they live under
        ``config["transcription"]["whisper"]``, with a sibling ``parakeet``
        block and an ``engine`` selector.

        Idempotent — returns False once the structure is already nested.
        """
        tr = self.config.get("transcription", {})
        if not isinstance(tr, dict):
            return False

        # Skip if migration already happened.
        already_nested = isinstance(tr.get("whisper"), dict) and "engine" in tr
        flat_present = any(k in tr for k in self._WHISPER_FLAT_KEYS)
        if already_nested and not flat_present:
            return False

        whisper_sub = tr.get("whisper")
        if not isinstance(whisper_sub, dict):
            whisper_sub = {}

        moved_any = False
        for key in self._WHISPER_FLAT_KEYS:
            if key in tr:
                whisper_sub.setdefault(key, tr.pop(key))
                moved_any = True

        if whisper_sub:
            tr["whisper"] = whisper_sub

        if "engine" not in tr:
            tr["engine"] = "whisper"
            moved_any = True

        if moved_any:
            logger.info("Migrated transcription config to modular engine layout")
        return moved_any

    def save(self) -> None:
        """Save current configuration atomically."""
        target = os.path.abspath(self.config_path)
        directory = os.path.dirname(target)
        os.makedirs(directory, exist_ok=True)

        tmp_path = f"{target}.tmp-{os.getpid()}-{int(time.time() * 1000)}"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, target)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                logger.debug("Failed to remove temp config file %s", tmp_path, exc_info=True)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value by key."""
        return self.config.get(key, default)

    def set(self, key: str, value: Any, save: bool = True) -> None:
        """Set a config value and optionally save."""
        self.config[key] = value
        if save:
            self.save()

    def __getitem__(self, key: str) -> Any:
        """Allow dict-like access: config['key']"""
        return self.config[key]

    def __setitem__(self, key: str, value: Any) -> None:
        """Allow dict-like assignment: config['key'] = value"""
        self.config[key] = value

    def __contains__(self, key: str) -> bool:
        """Allow 'in' operator: 'key' in config"""
        return key in self.config

    @staticmethod
    def recursive_update(base_dict: Dict, user_dict: Dict) -> Dict:
        """Recursively update base_dict with values from user_dict."""
        for key, value in user_dict.items():
            if key in base_dict:
                if isinstance(value, dict) and isinstance(base_dict[key], dict):
                    ConfigManager.recursive_update(base_dict[key], value)
                else:
                    base_dict[key] = value
        return base_dict

    # === Gemini API Keys ===

    def get_active_api_key(self) -> Optional[Dict]:
        """Get the active Gemini API key data dict."""
        for key_data in self.config.get("api_keys", []):
            if key_data.get("active"):
                return key_data
        return None

    def get_active_api_key_value(self) -> Optional[str]:
        """Get the active Gemini API key string."""
        key_data = self.get_active_api_key()
        return key_data.get("key") if key_data else None

    def switch_to_next_api_key(self) -> Optional[str]:
        """Switch to the next Gemini API key. Returns the new key name."""
        api_keys = self.config.get("api_keys", [])
        if len(api_keys) < 2:
            return None

        current_index = -1
        for i, key in enumerate(api_keys):
            if key.get("active"):
                current_index = i
                break

        if current_index >= 0:
            api_keys[current_index]["active"] = False

        next_index = (current_index + 1) % len(api_keys)
        api_keys[next_index]["active"] = True

        self.save()
        return api_keys[next_index].get("name", f"Key {next_index + 1}")

    # === OpenAI API Keys ===

    def get_active_openai_key(self) -> Optional[Dict]:
        """Get the active OpenAI API key data dict."""
        for key_data in self.config.get("openai_api_keys", []):
            if key_data.get("active"):
                return key_data
        return None

    def get_active_openai_key_value(self) -> Optional[str]:
        """Get the active OpenAI API key string."""
        key_data = self.get_active_openai_key()
        return key_data.get("key") if key_data else None

    def switch_to_next_openai_key(self) -> Optional[str]:
        """Switch to the next OpenAI API key. Returns the new key name."""
        api_keys = self.config.get("openai_api_keys", [])
        if len(api_keys) < 2:
            return None

        current_index = -1
        for i, key in enumerate(api_keys):
            if key.get("active"):
                current_index = i
                break

        if current_index >= 0:
            api_keys[current_index]["active"] = False

        next_index = (current_index + 1) % len(api_keys)
        api_keys[next_index]["active"] = True

        self.save()
        return api_keys[next_index].get("name", f"Key {next_index + 1}")
