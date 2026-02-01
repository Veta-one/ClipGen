"""Internationalization - language file loading and merging."""

import os
import json
from typing import Dict, Any, List

from ..core.constants import resource_path


class I18nManager:
    """Manages language resources with internal/external file merging."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.lang: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        """Load language, merging internal (fresh) with user's file."""
        language = self.config.get("language", "en")

        internal_path = resource_path(os.path.join("lang", f"{language}.json"))
        external_dir = "lang"
        external_path = os.path.join(external_dir, f"{language}.json")

        os.makedirs(external_dir, exist_ok=True)

        # Load internal (bundled) language file
        loaded_data = {}
        if os.path.exists(internal_path):
            try:
                with open(internal_path, "r", encoding="utf-8") as f:
                    loaded_data = json.load(f)
            except Exception as e:
                print(f"Error loading internal lang: {e}")
                loaded_data = self._create_default_english()
        else:
            loaded_data = self._create_default_english()

        # Merge with user's customizations
        if os.path.exists(external_path):
            try:
                with open(external_path, "r", encoding="utf-8") as f:
                    user_data = json.load(f)
                self._recursive_update(loaded_data, user_data)
            except Exception as e:
                print(f"Error merging user lang file: {e}")

        # Save merged result for user to edit
        try:
            with open(external_path, "w", encoding="utf-8") as f:
                json.dump(loaded_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving updated lang file: {e}")

        self.lang = loaded_data

    def get(self, key: str, default: str = "") -> str:
        """Get a translation by dot-separated key path."""
        parts = key.split(".")
        result = self.lang
        for part in parts:
            if isinstance(result, dict) and part in result:
                result = result[part]
            else:
                return default
        return result if isinstance(result, str) else default

    def __getitem__(self, key: str) -> Any:
        """Allow dict-like access: lang['key']"""
        return self.lang[key]

    def __contains__(self, key: str) -> bool:
        """Allow 'in' operator."""
        return key in self.lang

    def get_available_languages(self) -> List[str]:
        """Get list of available language codes."""
        lang_dir = "lang"
        languages = []

        if os.path.exists(lang_dir):
            for filename in os.listdir(lang_dir):
                if filename.endswith('.json'):
                    languages.append(filename[:-5])  # Remove .json

        if not languages:
            languages = ["en", "ru"]

        return sorted(languages)

    @staticmethod
    def _recursive_update(base_dict: Dict, user_dict: Dict) -> Dict:
        """Recursively update base_dict with values from user_dict."""
        for key, value in user_dict.items():
            if key in base_dict:
                if isinstance(value, dict) and isinstance(base_dict[key], dict):
                    I18nManager._recursive_update(base_dict[key], value)
                else:
                    base_dict[key] = value
        return base_dict

    @staticmethod
    def _create_default_english() -> Dict[str, Any]:
        """Creates a dictionary with default English strings."""
        return {
            "app_title": "ClipGen",
            "settings": {
                "autostart_label": "Run at Windows startup",
                "api_key_label": "Gemini API Key:",
                "gemini_models_label": "Gemini Models:",
                "language_label": "Language:",
                "hotkeys_title": "Hotkey Settings",
                "action_name_label": "Action name:",
                "prompt_label": "Prompt:",
                "log_color_label": "Log color:",
                "add_hotkey_button": "Add new action",
                "proxy_title": "Proxy (VPN bypass)",
                "proxy_enable_label": "Enable",
                "proxy_hint": "Format: login:password@ip:port (no http://)"
            },
            "updates": {
                "title": "ClipGen Update Available",
                "message": "A new version is available: <b>v{new_version}</b><br><br>Do you want to visit the download page?",
                "download_button": "Go to website",
                "skip_button": "Skip this version"
            },
            "tabs": {
                "logs": "Logs",
                "settings": "Settings",
                "prompts": "Prompts",
                "help": "Help"
            },
            "logs": {
                "key_switched": "Quota exceeded. Switched to key: {key_name}. Retrying...",
                "clear_logs": "Clear logs",
                "check_updates": "Check for updates",
                "checking_updates": "Checking for updates...",
                "update_not_found": "You have the latest version.",
                "instructions": "Instructions",
                "stop_task": "Stop",
                "app_started": "ClipGen started",
                "execution_time": "Executed in {seconds:.2f} sec.",
                "stop_request_sent": "Stop request sent...",
                "task_cancelled": "Task cancelled by user.",
                "task_cancelled_during_request": "Task cancelled during request execution."
            },
            "dialogs": {
                "confirm_delete_title": "Confirm Deletion",
                "confirm_delete_message": "Are you sure you want to delete the action '{action_name}'?",
                "confirm_delete_api_key_message": "Are you sure you want to delete the API key '{key_identifier}'?"
            },
            "tooltips": {}
        }
