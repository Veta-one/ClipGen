"""Text processor - coordinates API calls with clipboard and UI."""

import time
import logging
import threading
from queue import Queue, Empty
from typing import Dict, Any, Optional, Callable

from .gemini import GeminiProvider
from .openai_compat import OpenAIProvider
from ..utils.clipboard import ClipboardHandler

logger = logging.getLogger('ClipGen')


class TextProcessor:
    """Processes text/images through AI APIs with retry and key rotation."""

    def __init__(
        self,
        config: Dict[str, Any],
        gemini: GeminiProvider,
        openai: OpenAIProvider,
        clipboard: ClipboardHandler,
        save_callback: Callable[[], None],
        lang: Dict[str, Any]
    ):
        """Initialize processor.

        Args:
            config: Application config
            gemini: Gemini provider instance
            openai: OpenAI provider instance
            clipboard: Clipboard handler
            save_callback: Function to save settings
            lang: Language strings
        """
        self.config = config
        self.gemini = gemini
        self.openai = openai
        self.clipboard = clipboard
        self.save = save_callback
        self.lang = lang

        self.genai_lock = threading.Lock()
        self.task_lock = threading.Lock()
        self.current_task_event: Optional[threading.Event] = None

        # Callbacks for UI updates (set by app)
        self.on_start: Optional[Callable[[], None]] = None
        self.on_success: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[], None]] = None
        self.on_key_switch: Optional[Callable[[str], None]] = None
        self.on_log: Optional[Callable[[str, str], None]] = None
        self.on_explanation: Optional[Callable[[str, str], None]] = None  # text, hotkey_color

    def _get_provider(self, hotkey: dict = None):
        """Get provider based on hotkey settings or global config.

        Args:
            hotkey: Hotkey dict with optional custom_provider

        Returns:
            Provider instance (gemini or openai)
        """
        # Check hotkey-specific override
        if hotkey and hotkey.get("use_custom_model"):
            provider_name = hotkey.get("custom_provider")
            if provider_name:
                return self.openai if provider_name == "openai" else self.gemini

        # Fallback to global setting
        provider_name = self.config.get("provider", "gemini")
        return self.openai if provider_name == "openai" else self.gemini

    def _get_model_name(self, hotkey: dict = None) -> Optional[str]:
        """Get model name based on hotkey settings or global config.

        Args:
            hotkey: Hotkey dict with optional custom_model

        Returns:
            Model name string or None for default
        """
        # Check hotkey-specific override
        if hotkey and hotkey.get("use_custom_model"):
            custom_model = hotkey.get("custom_model")
            if custom_model:
                return custom_model

        # Return None to use provider's default from config
        return None

    def _update_key_timestamp(self, provider) -> None:
        """Update usage timestamp for active key."""
        key_data = provider.get_active_key()
        if key_data:
            now = time.time()
            if "usage_timestamps" not in key_data:
                key_data["usage_timestamps"] = []
            key_data["usage_timestamps"].append(now)
            # Keep only last 24 hours
            key_data["usage_timestamps"] = [
                ts for ts in key_data["usage_timestamps"]
                if now - ts < 86400
            ]

    def process(
        self,
        action_name: str,
        prompt: str,
        text: str = "",
        is_image: bool = False,
        image_data: Optional[str] = None
    ) -> str:
        """Process text or image through AI API.

        Args:
            action_name: Name of the action (for logging)
            prompt: Instruction prompt
            text: Text to process
            is_image: Whether processing an image
            image_data: Base64 image data

        Returns:
            Processed result text, or empty string on error
        """
        # Find hotkey info for logging and custom model
        hotkey = next(
            (h for h in self.config.get("hotkeys", []) if h["name"] == action_name),
            None
        )
        combo = hotkey["combination"] if hotkey else ""

        # Get provider and model based on hotkey settings
        provider = self._get_provider(hotkey)
        provider_name = provider.name
        model_override = self._get_model_name(hotkey)

        # Create cancel event
        cancel_event = threading.Event()
        with self.task_lock:
            self.current_task_event = cancel_event

        # Try to acquire lock
        if not self.genai_lock.acquire(blocking=False):
            logger.warning(f"[{combo}: {action_name}] Busy.")
            with self.task_lock:
                self.current_task_event = None
            if self.on_error:
                self.on_error()
            return ""

        try:
            logger.info(f"[{combo}: {action_name}] Processing via {provider_name}...")

            # Calculate max attempts based on number of keys
            api_keys = self.config.get(provider.api_keys_key, [])
            max_attempts = max(len(api_keys) * 2, 1)

            attempt = 0
            success_result = None
            last_error = None

            while attempt < max_attempts:
                attempt += 1

                key_data = provider.get_active_key()
                if not key_data or not key_data.get("key"):
                    logger.error(f"[{combo}: {action_name}] API Key not set for {provider_name}")
                    if self.on_error:
                        self.on_error()
                    return ""

                if "YOUR_KEY" in key_data.get("key", ""):
                    logger.error(f"[{combo}: {action_name}] API Key not configured")
                    if self.on_error:
                        self.on_error()
                    return ""

                # Use a queue to get result from worker thread
                result_queue: Queue = Queue()

                def worker():
                    try:
                        result = provider.generate(
                            prompt=prompt,
                            text=text,
                            cancel_event=cancel_event,
                            is_image=is_image,
                            image_data=image_data,
                            model_override=model_override
                        )
                        result_queue.put(result)
                    except Exception as e:
                        result_queue.put(e)

                worker_thread = threading.Thread(target=worker, daemon=True)
                worker_thread.start()

                # Wait for worker with cancellation check
                while worker_thread.is_alive():
                    if cancel_event.is_set():
                        logger.warning("Cancelled.")
                        return ""
                    time.sleep(0.1)

                # Get result
                try:
                    result = result_queue.get_nowait()
                except Empty:
                    return ""

                if isinstance(result, Exception):
                    err_str = str(result).lower()

                    # Check for quota error
                    if "429" in err_str or "quota" in err_str:
                        if self.config.get("auto_switch_api_keys", False):
                            new_key_name = provider.switch_to_next_key()
                            if new_key_name:
                                if self.on_key_switch:
                                    self.on_key_switch(new_key_name)
                                if self.on_log:
                                    self.on_log(f"Switched to {new_key_name}", "#FF5555")
                                continue

                    last_error = result
                    break
                else:
                    success_result = result
                    break

            if success_result:
                # Update usage statistics
                self._update_key_timestamp(provider)
                self.save()
                return success_result

            if last_error:
                raise last_error
            return ""

        except Exception as e:
            err_str = str(e).lower()
            err_dict = self.lang.get("errors", {})
            final_msg = str(e)

            # Translate common errors
            if "429" in err_str and "quota" in err_str:
                final_msg = err_dict.get("gemini_quota_exceeded_friendly", "Error 429: Quota exceeded")
            elif "503" in err_str or "overloaded" in err_str:
                final_msg = err_dict.get("gemini_service_unavailable", "Error 503: Service unavailable")
            elif "timeout" in err_str or "deadline" in err_str or "504" in err_str:
                final_msg = err_dict.get("gemini_timeout_error", "Error: Timeout")
            elif "connection" in err_str or "stream removed" in err_str or "failed to connect" in err_str:
                final_msg = err_dict.get("gemini_connection_error", "Error: Connection failed")
            elif "400" in err_str and "api key" in err_str:
                final_msg = err_dict.get("gemini_400_invalid_key", "Error: Invalid Key")
            elif "404" in err_str and "not found" in err_str:
                model_name = self.config.get("active_model", "Unknown")
                final_msg = err_dict.get("gemini_404_model_not_found", "Error: Model not found").format(model_name=model_name)

            if self.on_log:
                self.on_log(f"Error: {final_msg}", "#FF5555")

            logger.error(f"{final_msg}")
            return ""

        finally:
            self.genai_lock.release()
            with self.task_lock:
                self.current_task_event = None

    def handle_hotkey(self, action_name: str, prompt: str) -> None:
        """Handle a hotkey press - copy, process, paste.

        Args:
            action_name: Name of the action
            prompt: Processing prompt
        """
        if self.on_start:
            self.on_start()

        start_time = time.time()
        timestamp = time.strftime('%H:%M:%S')

        # Find hotkey for logging
        hotkey = next(
            (h for h in self.config.get("hotkeys", []) if h["name"] == action_name),
            None
        )
        combo = hotkey["combination"] if hotkey else ""
        color = hotkey["log_color"] if hotkey else "#FFFFFF"

        # Log action header
        if self.on_log:
            self.on_log(f"{combo}: {action_name} - {timestamp}", color)

        try:
            # Simulate Ctrl+C
            self.clipboard.simulate_copy()

            # Get clipboard content
            content, is_image = self.clipboard.get_content()

            if not content:
                empty_msg = self.lang.get("errors", {}).get("empty_clipboard", "Clipboard is empty")
                if self.on_log:
                    self.on_log(empty_msg, "#FFDD55")
                if self.on_error:
                    self.on_error()
                return

            # Process
            result = self.process(
                action_name=action_name,
                prompt=prompt,
                text="" if is_image else content,
                is_image=is_image,
                image_data=content if is_image else None
            )

            if result:
                # Set result to clipboard
                self.clipboard.set_text(result)

                # Learning mode: start parallel explanation request
                if hotkey and hotkey.get("learning_mode") and not is_image:
                    original_text = content
                    threading.Thread(
                        target=self._get_explanation,
                        args=(original_text, result, hotkey),
                        daemon=True
                    ).start()

                # Simulate Ctrl+V
                self.clipboard.simulate_paste()

                duration = time.time() - start_time

                # Log execution time
                if self.on_log:
                    time_msg = self.lang.get("logs", {}).get("execution_time", "Executed in {seconds:.2f} sec.")
                    self.on_log(time_msg.format(seconds=duration), "#888888")

                # Log result
                if self.on_log:
                    self.on_log(result, color)

                if self.on_success:
                    self.on_success(f"{duration:.1f}")  # Format: 1.2 (no "s")
            else:
                if self.on_error:
                    self.on_error()

        except Exception as e:
            error_msg = str(e)
            if self.on_log:
                self.on_log(f"Error: {error_msg}", "#FF5555")
            if self.on_error:
                self.on_error()

    def cancel_current(self) -> None:
        """Cancel current operation."""
        with self.task_lock:
            if self.current_task_event:
                self.current_task_event.set()

    def _get_explanation(
        self,
        original: str,
        result: str,
        hotkey: dict
    ) -> None:
        """Get explanation for changes in background thread.

        Runs in a separate daemon thread, does not block main processing.

        Args:
            original: Original text before processing
            result: Text after AI processing
            hotkey: Hotkey configuration with learning_prompt
        """
        try:
            # Skip if texts are identical or nearly identical
            if original.strip() == result.strip():
                return

            # Get learning prompt (custom or default from language file)
            learning_prompt = hotkey.get("learning_prompt", "").strip()

            # Check if saved prompt is a default prompt from any language
            # If so, use current language's default instead
            default_prompt_markers = [
                "You are a language tutor",  # English default start
                "Ты — языковой репетитор",   # Russian default start
            ]
            is_default = not learning_prompt or any(
                marker in learning_prompt for marker in default_prompt_markers
            )

            if is_default:
                learning_prompt = self.lang.get(
                    "default_learning_prompt",
                    "Compare original with result and explain significant changes."
                )

            # Add language instruction from language file
            lang_instruction = self.lang.get("settings", {}).get(
                "learning_language_instruction",
                "IMPORTANT: Respond in the same language as the original text."
            )
            lang_instruction = f"\n\n{lang_instruction}"

            # Format prompt with texts
            try:
                formatted_prompt = learning_prompt.format(
                    original=original,
                    result=result
                )
            except KeyError:
                # If placeholders missing, append texts
                formatted_prompt = f"{learning_prompt}\n\nOriginal: {original}\n\nResult: {result}"

            # Add language instruction
            formatted_prompt += lang_instruction

            # Get provider (use same as main request)
            provider = self._get_provider(hotkey)
            model_override = self._get_model_name(hotkey)

            # Create cancel event (independent from main task)
            cancel_event = threading.Event()

            # Make API request
            explanation = provider.generate(
                prompt=formatted_prompt,
                text="",
                cancel_event=cancel_event,
                is_image=False,
                image_data=None,
                model_override=model_override
            )

            # Send to UI if not empty
            if explanation and explanation.strip() and self.on_explanation:
                hotkey_color = hotkey.get("log_color", "#FFFFFF")
                self.on_explanation(explanation.strip(), hotkey_color)

        except Exception as e:
            logger.warning(f"Failed to get explanation: {e}")
