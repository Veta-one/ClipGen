"""Generic list manager for API keys and models."""

import copy
from typing import Dict, Any, List, Optional, Callable


class ConfigListManager:
    """Manages lists in config (API keys, models) with common operations."""

    def __init__(
        self,
        config: Dict[str, Any],
        list_key: str,
        active_field: str,
        default_item: Dict[str, Any],
        save_callback: Callable[[], None],
        refresh_callback: Optional[Callable[[], None]] = None
    ):
        """Initialize list manager.

        Args:
            config: Application config dict
            list_key: Key in config for the list (e.g., "api_keys")
            active_field: Field name for active flag or active item name
            default_item: Template for new items
            save_callback: Function to call after changes
            refresh_callback: Function to refresh UI after changes
        """
        self.config = config
        self.list_key = list_key
        self.active_field = active_field
        self.default_item = default_item
        self.save = save_callback
        self.refresh = refresh_callback or (lambda: None)

    @property
    def items(self) -> List[Dict[str, Any]]:
        """Get the list of items."""
        return self.config.get(self.list_key, [])

    def add(self, item: Optional[Dict[str, Any]] = None) -> int:
        """Add a new item to the list.

        Args:
            item: Item to add, or None to use default

        Returns:
            Index of the new item
        """
        new_item = copy.deepcopy(item or self.default_item)

        if self.list_key not in self.config:
            self.config[self.list_key] = []

        items = self.items

        # If this is the first item, make it active
        if len(items) == 0 and "active" in new_item:
            new_item["active"] = True

        items.append(new_item)
        self.save()
        self.refresh()

        return len(items) - 1

    def delete(self, index: int) -> bool:
        """Delete an item from the list.

        Args:
            index: Index of item to delete

        Returns:
            True if deletion was successful
        """
        items = self.items
        if not (0 <= index < len(items)):
            return False

        # Check if deleting active item
        was_active = items[index].get("active", False)

        del items[index]

        # If deleted item was active and there are remaining items
        if was_active and len(items) > 0:
            items[0]["active"] = True

        self.save()
        self.refresh()
        return True

    def set_active(self, index: int) -> bool:
        """Set an item as active.

        Args:
            index: Index of item to activate

        Returns:
            True if operation was successful
        """
        items = self.items
        if not (0 <= index < len(items)):
            return False

        # For items with "active" boolean field
        if "active" in items[0]:
            for i, item in enumerate(items):
                item["active"] = (i == index)
        else:
            # For models with external active field (e.g., active_model)
            active_name = items[index].get("name")
            if active_name and self.active_field in self.config:
                self.config[self.active_field] = active_name

        self.save()
        self.refresh()
        return True

    def update_field(self, index: int, field: str, value: Any) -> bool:
        """Update a field in an item.

        Args:
            index: Index of item to update
            field: Field name to update
            value: New value

        Returns:
            True if operation was successful
        """
        items = self.items
        if not (0 <= index < len(items)):
            return False

        old_value = items[index].get(field)
        items[index][field] = value

        # If updating name and this item is active, update active reference
        if field == "name" and self.active_field in self.config:
            if self.config[self.active_field] == old_value:
                self.config[self.active_field] = value

        self.save()
        return True

    def get_active_index(self) -> int:
        """Get index of active item.

        Returns:
            Index of active item, or -1 if none found
        """
        items = self.items

        # For items with "active" boolean field
        for i, item in enumerate(items):
            if item.get("active"):
                return i

        # For models with external active field
        if self.active_field in self.config:
            active_name = self.config[self.active_field]
            for i, item in enumerate(items):
                if item.get("name") == active_name:
                    return i

        return -1

    def get_active(self) -> Optional[Dict[str, Any]]:
        """Get the active item.

        Returns:
            Active item dict, or None if none found
        """
        index = self.get_active_index()
        if index >= 0:
            return self.items[index]
        return None

    def get_active_value(self, field: str = "key") -> Optional[str]:
        """Get a field value from the active item.

        Args:
            field: Field name to get

        Returns:
            Field value, or None if no active item
        """
        active = self.get_active()
        return active.get(field) if active else None
