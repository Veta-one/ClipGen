"""Hotkey configuration management."""

from typing import Dict, Any, List, Optional, Callable


class HotkeyManager:
    """Manages hotkey configuration - add, update, delete."""

    def __init__(
        self,
        config: Dict[str, Any],
        save_callback: Callable[[], None],
        refresh_callback: Optional[Callable[[], None]] = None
    ):
        """Initialize manager.

        Args:
            config: Application config
            save_callback: Function to save settings
            refresh_callback: Function to refresh UI
        """
        self.config = config
        self.save = save_callback
        self.refresh = refresh_callback or (lambda: None)

    @property
    def hotkeys(self) -> List[Dict[str, Any]]:
        """Get list of hotkeys."""
        return self.config.get("hotkeys", [])

    def add(
        self,
        combination: str = "Ctrl+F9",
        name: str = "New Action",
        prompt: str = "",
        log_color: str = "#FFFFFF"
    ) -> int:
        """Add a new hotkey.

        Args:
            combination: Key combination (e.g., "Ctrl+F1")
            name: Action name
            prompt: Processing prompt
            log_color: Color for log messages

        Returns:
            Index of new hotkey
        """
        if "hotkeys" not in self.config:
            self.config["hotkeys"] = []

        new_hotkey = {
            "combination": combination,
            "name": name,
            "prompt": prompt,
            "log_color": log_color,
            "use_custom_model": False,
            "custom_provider": None,
            "custom_model": None,
            "learning_mode": False,
            "learning_prompt": ""
        }

        self.config["hotkeys"].append(new_hotkey)
        self.save()
        self.refresh()

        return len(self.config["hotkeys"]) - 1

    def delete(self, index: int) -> bool:
        """Delete a hotkey.

        Args:
            index: Index of hotkey to delete

        Returns:
            True if successful
        """
        hotkeys = self.hotkeys
        if not (0 <= index < len(hotkeys)):
            return False

        del hotkeys[index]
        self.save()
        self.refresh()
        return True

    def update_combination(self, index: int, combination: str) -> bool:
        """Update hotkey combination.

        Args:
            index: Hotkey index
            combination: New key combination

        Returns:
            True if successful
        """
        hotkeys = self.hotkeys
        if not (0 <= index < len(hotkeys)):
            return False

        hotkeys[index]["combination"] = combination
        self.save()
        return True

    def update_name(self, index: int, name: str) -> bool:
        """Update hotkey name.

        Args:
            index: Hotkey index
            name: New name

        Returns:
            True if successful
        """
        hotkeys = self.hotkeys
        if not (0 <= index < len(hotkeys)):
            return False

        hotkeys[index]["name"] = name
        self.save()
        return True

    def update_prompt(self, index: int, prompt: str) -> bool:
        """Update hotkey prompt.

        Args:
            index: Hotkey index
            prompt: New prompt

        Returns:
            True if successful
        """
        hotkeys = self.hotkeys
        if not (0 <= index < len(hotkeys)):
            return False

        hotkeys[index]["prompt"] = prompt
        self.save()
        return True

    def update_color(self, index: int, color: str) -> bool:
        """Update hotkey log color.

        Args:
            index: Hotkey index
            color: New color (hex)

        Returns:
            True if successful
        """
        hotkeys = self.hotkeys
        if not (0 <= index < len(hotkeys)):
            return False

        hotkeys[index]["log_color"] = color
        self.save()
        return True

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find hotkey by name.

        Args:
            name: Action name to find

        Returns:
            Hotkey dict or None
        """
        for hotkey in self.hotkeys:
            if hotkey.get("name") == name:
                return hotkey
        return None

    def is_combination_used(self, combination: str, exclude_index: int = -1) -> bool:
        """Check if combination is already used.

        Args:
            combination: Key combination to check
            exclude_index: Index to exclude from check

        Returns:
            True if combination is used by another hotkey
        """
        combo_lower = combination.lower()
        for i, hotkey in enumerate(self.hotkeys):
            if i == exclude_index:
                continue
            if hotkey.get("combination", "").lower() == combo_lower:
                return True
        return False

    def update_use_custom_model(self, index: int, enabled: bool) -> bool:
        """Update hotkey use_custom_model flag.

        Args:
            index: Hotkey index
            enabled: Whether to use custom model

        Returns:
            True if successful
        """
        hotkeys = self.hotkeys
        if not (0 <= index < len(hotkeys)):
            return False

        hotkeys[index]["use_custom_model"] = enabled
        self.save()
        return True

    def update_custom_provider(self, index: int, provider: Optional[str]) -> bool:
        """Update hotkey custom provider.

        Args:
            index: Hotkey index
            provider: Provider name ("gemini" or "openai") or None

        Returns:
            True if successful
        """
        hotkeys = self.hotkeys
        if not (0 <= index < len(hotkeys)):
            return False

        hotkeys[index]["custom_provider"] = provider
        self.save()
        return True

    def update_custom_model(self, index: int, model: Optional[str]) -> bool:
        """Update hotkey custom model.

        Args:
            index: Hotkey index
            model: Model name or None

        Returns:
            True if successful
        """
        hotkeys = self.hotkeys
        if not (0 <= index < len(hotkeys)):
            return False

        hotkeys[index]["custom_model"] = model
        self.save()
        return True

    def update_learning_mode(self, index: int, enabled: bool) -> bool:
        """Update hotkey learning_mode flag.

        Args:
            index: Hotkey index
            enabled: Whether to enable learning mode

        Returns:
            True if successful
        """
        hotkeys = self.hotkeys
        if not (0 <= index < len(hotkeys)):
            return False

        hotkeys[index]["learning_mode"] = enabled
        self.save()
        return True

    def update_learning_prompt(self, index: int, prompt: str) -> bool:
        """Update hotkey learning_prompt.

        Args:
            index: Hotkey index
            prompt: Custom learning prompt or empty for default

        Returns:
            True if successful
        """
        hotkeys = self.hotkeys
        if not (0 <= index < len(hotkeys)):
            return False

        hotkeys[index]["learning_prompt"] = prompt
        self.save()
        return True
