"""OpenAI compatible API provider (OpenRouter, etc.)."""

import base64
import threading
from typing import Dict, Any, Optional, List

from openai import OpenAI

from .base import APIProvider


class OpenAIProvider(APIProvider):
    """Provider for OpenAI-compatible APIs."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

    @property
    def name(self) -> str:
        return "openai"

    @property
    def api_keys_key(self) -> str:
        return "openai_api_keys"

    @property
    def active_model_key(self) -> str:
        return "openai_active_model"

    @property
    def base_url(self) -> str:
        return self.config.get("openai_base_url", "https://openrouter.ai/api/v1")

    def get_active_key(self) -> Optional[Dict[str, Any]]:
        """Get the active API key data."""
        for key_data in self.config.get(self.api_keys_key, []):
            if key_data.get("active"):
                return key_data
        return None

    def get_active_key_value(self) -> Optional[str]:
        """Get the active API key string."""
        key_data = self.get_active_key()
        return key_data.get("key") if key_data else None

    def reconfigure(self, api_key: str) -> None:
        """OpenAI client is created per-request, no reconfiguration needed."""
        pass

    def _create_client(self) -> OpenAI:
        """Create an OpenAI client with current config."""
        api_key = self.get_active_key_value()
        return OpenAI(base_url=self.base_url, api_key=api_key)

    def generate(
        self,
        prompt: str,
        text: str,
        cancel_event: threading.Event,
        is_image: bool = False,
        image_data: Optional[str] = None,
        model_override: Optional[str] = None
    ) -> str:
        """Generate response using OpenAI-compatible API.

        Args:
            prompt: Instruction prompt
            text: User text (ignored if is_image)
            cancel_event: Cancellation event
            is_image: Whether processing an image
            image_data: Base64 encoded image
            model_override: Override model name (uses config default if None)

        Returns:
            Generated text
        """
        if cancel_event.is_set():
            raise ValueError("Cancelled")

        model_name = model_override or self.config.get(self.active_model_key, "gpt-3.5-turbo")
        client = self._create_client()

        messages: List[Dict[str, Any]] = []

        if is_image and image_data:
            # Multimodal message with image
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_data}"}
                    }
                ]
            })
        else:
            # Text-only message
            messages.append({
                "role": "user",
                "content": f"{prompt}\n\n{text}"
            })

        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.7,
            timeout=60
        )

        return response.choices[0].message.content
