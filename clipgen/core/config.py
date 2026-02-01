"""Configuration management - loading, saving, merging settings."""

import os
import json
import copy
from typing import Any, Dict, Optional

from .constants import DEFAULT_CONFIG


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
                print("DEBUG: Config migrated to new version.")
                self.save()

        except FileNotFoundError:
            print(f"Config file not found, creating default at {self.config_path}")
            self.config = copy.deepcopy(DEFAULT_CONFIG)
            self.save()
        except json.JSONDecodeError as e:
            print(f"Error parsing settings, resetting to default: {e}")
            self.config = copy.deepcopy(DEFAULT_CONFIG)
            self.save()
        except Exception as e:
            print(f"Error loading settings, resetting to default: {e}")
            self.config = copy.deepcopy(DEFAULT_CONFIG)
            self.save()

    def _migrate_config(self) -> bool:
        """Migrate old config format to new. Returns True if changes were made."""
        config_changed = False

        # Add missing top-level keys
        for key, default_val in DEFAULT_CONFIG.items():
            if key not in self.config:
                self.config[key] = copy.deepcopy(default_val)
                config_changed = True

        # Migrate api_keys structure
        if "api_keys" in self.config:
            for key_data in self.config["api_keys"]:
                if "name" not in key_data:
                    key_data["name"] = ""
                    config_changed = True
                if "usage_timestamps" not in key_data:
                    key_data["usage_timestamps"] = []
                    config_changed = True

        # Migrate openai_api_keys structure
        if "openai_api_keys" in self.config:
            for key_data in self.config["openai_api_keys"]:
                if "name" not in key_data:
                    key_data["name"] = ""
                    config_changed = True
                if "usage_timestamps" not in key_data:
                    key_data["usage_timestamps"] = []
                    config_changed = True

        return config_changed

    def save(self) -> None:
        """Save current configuration to file."""
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=4)

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
