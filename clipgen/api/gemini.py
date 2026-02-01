"""Google Gemini API provider."""

import io
import threading
from typing import Dict, Any, Optional

import google.generativeai as genai
from google.generativeai import GenerationConfig, types
from PIL import Image

from .base import APIProvider


class GeminiProvider(APIProvider):
    """Provider for Google Gemini API."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._configure_initial()

    def _configure_initial(self) -> None:
        """Configure genai with initial API key."""
        key = self.get_active_key_value()
        if key and key != "YOUR_API_KEY_HERE":
            genai.configure(api_key=key)

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def api_keys_key(self) -> str:
        return "api_keys"

    @property
    def active_model_key(self) -> str:
        return "active_model"

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
        """Reconfigure genai with new API key."""
        genai.configure(api_key=api_key)

    def generate(
        self,
        prompt: str,
        text: str,
        cancel_event: threading.Event,
        is_image: bool = False,
        image_data: Optional[str] = None,
        model_override: Optional[str] = None
    ) -> str:
        """Generate response using Gemini.

        Args:
            prompt: Instruction prompt
            text: User text (ignored if is_image)
            cancel_event: Cancellation event
            is_image: Whether processing clipboard image
            image_data: Base64 image or PIL Image object
            model_override: Override model name (uses config default if None)

        Returns:
            Generated text
        """
        if cancel_event.is_set():
            raise ValueError("Cancelled")

        model_name = model_override or self.config.get(self.active_model_key, "gemini-2.0-flash")
        model = genai.GenerativeModel(model_name)

        # Safety settings - allow all content
        safety_settings = {
            types.HarmCategory.HARM_CATEGORY_HARASSMENT: types.HarmBlockThreshold.BLOCK_NONE,
            types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: types.HarmBlockThreshold.BLOCK_NONE,
            types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: types.HarmBlockThreshold.BLOCK_NONE,
            types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: types.HarmBlockThreshold.BLOCK_NONE,
        }

        gen_config = GenerationConfig(temperature=0.7)

        # Build content
        if is_image and image_data:
            # image_data can be PIL Image or base64 string
            if isinstance(image_data, str):
                # Base64 string - need to decode
                import base64
                image_bytes = base64.b64decode(image_data)
                image = Image.open(io.BytesIO(image_bytes))
            else:
                image = image_data

            content = [prompt, image]
        else:
            content = [prompt, text]

        response = model.generate_content(
            content,
            generation_config=gen_config,
            safety_settings=safety_settings,
            request_options={'timeout': 60}
        )

        if not response.parts:
            raise ValueError("Empty response from Gemini")

        return response.text.strip()
