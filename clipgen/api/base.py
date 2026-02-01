"""Abstract base class for API providers."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import threading


class APIProvider(ABC):
    """Abstract base class for AI API providers."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize provider with config.

        Args:
            config: Application config dict
        """
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'gemini', 'openai')."""
        pass

    @property
    @abstractmethod
    def api_keys_key(self) -> str:
        """Config key for API keys list."""
        pass

    @property
    @abstractmethod
    def active_model_key(self) -> str:
        """Config key for active model name."""
        pass

    @abstractmethod
    def get_active_key(self) -> Optional[Dict[str, Any]]:
        """Get the active API key data."""
        pass

    @abstractmethod
    def generate(
        self,
        prompt: str,
        text: str,
        cancel_event: threading.Event,
        is_image: bool = False,
        image_data: Optional[str] = None,
        model_override: Optional[str] = None
    ) -> str:
        """Generate response from API.

        Args:
            prompt: System/instruction prompt
            text: User text to process
            cancel_event: Event to check for cancellation
            is_image: Whether processing an image
            image_data: Base64 encoded image data
            model_override: Override model name (uses config default if None)

        Returns:
            Generated text response
        """
        pass

    @abstractmethod
    def reconfigure(self, api_key: str) -> None:
        """Reconfigure provider with new API key."""
        pass

    def switch_to_next_key(self) -> Optional[str]:
        """Switch to the next API key in rotation.

        Returns:
            Name of the new key, or None if not possible
        """
        keys = self.config.get(self.api_keys_key, [])
        if len(keys) < 2:
            return None

        current_index = -1
        for i, key in enumerate(keys):
            if key.get("active"):
                current_index = i
                break

        if current_index >= 0:
            keys[current_index]["active"] = False

        next_index = (current_index + 1) % len(keys)
        keys[next_index]["active"] = True

        new_key = keys[next_index].get("key")
        if new_key:
            self.reconfigure(new_key)

        return keys[next_index].get("name", f"Key {next_index + 1}")
