"""Main application class with composition-based architecture."""

import os
import sys
import time
import datetime
import random
import threading
import logging
from queue import Queue

from PyQt5.QtWidgets import QApplication

from .core.config import ConfigManager
from .core.constants import __version__, APPLICATION_PATH
from .utils.i18n import I18nManager
from .utils.proxy import apply_proxy
from .utils.autostart import is_autostart_enabled
from .utils.clipboard import ClipboardHandler
from .api.gemini import GeminiProvider
from .api.openai_compat import OpenAIProvider
from .api.processor import TextProcessor
from .hotkeys.listener import HotkeyListener
from .hotkeys.manager import HotkeyManager
from .testing.tester import APITester
from .ui.main_window import MainWindow

logger = logging.getLogger('ClipGen')

# Colors
ACCENT_BLUE = "#A3BFFA"
ERROR_RED = "#FF5555"


class ClipGenApp:
    """Main application using composition over inheritance."""

    def __init__(self):
        """Initialize application components."""
        # Configuration
        self.config = ConfigManager()

        # Apply proxy settings
        apply_proxy(self.config.config)

        # Internationalization
        self.i18n = I18nManager(self.config.config)

        # API providers
        self.gemini = GeminiProvider(self.config.config)
        self.openai = OpenAIProvider(self.config.config)

        # Threading
        self.task_lock = threading.Lock()

        # Hotkey management (create listener first for clipboard sync)
        self.hotkey_queue = Queue()
        self.hotkey_manager = HotkeyManager(
            self.config.config,
            self.config.save
        )
        self.hotkey_listener = HotkeyListener(
            self.config.config,
            self.hotkey_queue
        )

        # Clipboard handler (synced with hotkey listener)
        self.clipboard = ClipboardHandler(
            on_pasting_change=self.hotkey_listener.set_pasting
        )

        # API tester
        self.tester = APITester(self.config.config, self.task_lock)

        # Text processor
        self.processor = TextProcessor(
            config=self.config.config,
            gemini=self.gemini,
            openai=self.openai,
            clipboard=self.clipboard,
            save_callback=self.config.save,
            lang=self.i18n.lang
        )

        # Apply UI scaling BEFORE creating QApplication
        scale = self.config.config.get("ui_scale", 1.0)
        if scale != 1.0:
            os.environ["QT_SCALE_FACTOR"] = str(scale)

        # Qt application
        self.qt_app = QApplication(sys.argv)

        # Main window
        self.window = MainWindow(self)

        # Connect processor callbacks to window signals
        self._connect_processor_callbacks()

        # Start hotkey listener
        self.hotkey_listener.start()

        # Start queue worker
        self._start_queue_worker()

        # Log startup
        logger.info(f"ClipGen v{__version__} started")

        # Sync autostart button
        self.window.settings_tab.set_autostart_checked(is_autostart_enabled())

        # Refresh UI
        self.window.refresh_all_signal.emit()

        # Load welcome message asynchronously
        threading.Thread(target=self._load_welcome_message, daemon=True).start()

    def _connect_processor_callbacks(self) -> None:
        """Connect processor callbacks to window signals."""
        self.processor.on_start = lambda: self.window.start_working_signal.emit()
        self.processor.on_success = lambda d: self.window.success_signal.emit(d)
        self.processor.on_error = lambda: self.window.error_signal.emit()
        self.processor.on_key_switch = lambda n: self.window.flash_tray_signal.emit()
        self.processor.on_log = lambda m, c: self.window.log_signal.emit(m, c)
        self.processor.on_explanation = lambda t, c: self.window.show_explanation_signal.emit(t, c)

    def _start_queue_worker(self) -> None:
        """Start the hotkey queue worker thread."""
        def worker():
            while True:
                try:
                    event = self.hotkey_queue.get(timeout=1.0)
                    if event is None:
                        break

                    action = event.get("action", "")
                    prompt = event.get("prompt", "")

                    # Process in a new thread
                    threading.Thread(
                        target=self.processor.handle_hotkey,
                        args=(action, prompt),
                        daemon=True
                    ).start()

                except Exception:
                    continue

        self.queue_worker_thread = threading.Thread(target=worker, daemon=True)
        self.queue_worker_thread.start()

    def run(self) -> int:
        """Run the application.

        Returns:
            Exit code
        """
        self.window.show()
        return self.qt_app.exec_()

    def _load_welcome_message(self) -> None:
        """Load welcome message asynchronously."""
        try:
            time.sleep(0.5)  # Wait for UI to be ready
            welcome_message = self._generate_welcome_message()
            self.window.log_signal.emit(welcome_message, ACCENT_BLUE)
        except Exception as e:
            # Fallback to simple message
            self.window.log_signal.emit(
                self.i18n.lang.get("welcome_back", "Welcome back!"),
                ACCENT_BLUE
            )

            # Show error
            error_details = str(e).lower()
            err_dict = self.i18n.lang.get("errors", {})
            final_msg = str(e)

            if "429" in error_details and ("quota" in error_details or "exhausted" in error_details):
                final_msg = err_dict.get("gemini_quota_exceeded_friendly", "Error 429: Quota exceeded")
            elif "503" in error_details or "overloaded" in error_details:
                final_msg = err_dict.get("gemini_service_unavailable", "Error 503: Service unavailable")
            elif "timeout" in error_details or "deadline" in error_details or "504" in error_details:
                final_msg = err_dict.get("gemini_timeout_error", "Error: Timeout")
            elif "connection" in error_details or "stream removed" in error_details or "failed to connect" in error_details:
                final_msg = err_dict.get("gemini_connection_error", "Error: Connection failed")
            elif "400" in error_details and "api key" in error_details:
                final_msg = err_dict.get("gemini_400_invalid_key", "Error: Invalid Key")
            elif "404" in error_details and "not found" in error_details:
                model_name = self.config.config.get("active_model", "Unknown")
                final_msg = err_dict.get("gemini_404_model_not_found", "Error: Model not found").format(model_name=model_name)

            self.window.log_signal.emit(f"Error: {final_msg}", ERROR_RED)

    def _generate_welcome_message(self) -> str:
        """Generate welcome message from AI using active provider."""
        import google.generativeai as genai
        from google.generativeai import GenerationConfig
        from openai import OpenAI

        lang = self.i18n.lang
        config = self.config.config

        # Get current time and date
        now = datetime.datetime.now()
        hour = now.hour
        formatted_date = now.strftime("%d.%m.%Y")

        # Get weekday
        weekdays = lang.get("weekdays", ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        weekday = weekdays[now.weekday()] if len(weekdays) > now.weekday() else now.strftime("%A")

        # Get time of day and greeting
        time_of_day_dict = lang.get("time_of_day", {"morning": "morning", "day": "afternoon", "evening": "evening", "night": "night"})
        greetings_dict = lang.get("greetings", {"morning": "Good morning!", "day": "Good afternoon!", "evening": "Good evening!", "night": "Good night!"})

        if 5 <= hour < 12:
            time_of_day = time_of_day_dict.get("morning", "morning")
            greeting = greetings_dict.get("morning", "Good morning!")
        elif 12 <= hour < 17:
            time_of_day = time_of_day_dict.get("day", "afternoon")
            greeting = greetings_dict.get("day", "Good afternoon!")
        elif 17 <= hour < 22:
            time_of_day = time_of_day_dict.get("evening", "evening")
            greeting = greetings_dict.get("evening", "Good evening!")
        else:
            time_of_day = time_of_day_dict.get("night", "night")
            greeting = greetings_dict.get("night", "Good night!")

        # Get random prompt
        prompts = lang.get("welcome_prompts", [
            "Write a short greeting starting with '{greeting}'."
        ])
        prompt = random.choice(prompts).format(
            formatted_date=formatted_date,
            weekday=weekday,
            time_of_day=time_of_day,
            greeting=greeting
        )

        # Make API request using active provider
        provider = config.get("provider", "gemini")
        max_attempts = len(config.get("api_keys", [])) * 2
        if max_attempts == 0:
            max_attempts = 1

        for attempt in range(max_attempts):
            try:
                if provider == "gemini":
                    # Direct Gemini API call (like original)
                    active_model = config.get("active_model", "gemini-2.0-flash")
                    model = genai.GenerativeModel(active_model)
                    response = model.generate_content(
                        prompt,
                        generation_config=GenerationConfig(temperature=0.9, max_output_tokens=2048),
                        request_options={'timeout': 30}
                    )
                    if response and response.text.strip():
                        return response.text.strip()
                    else:
                        raise ValueError("Empty response")
                else:
                    # OpenAI compatible API
                    active_key = None
                    for k in config.get("openai_api_keys", []):
                        if k.get("active"):
                            active_key = k.get("key")
                            break

                    if not active_key:
                        raise ValueError("No active OpenAI API key")

                    base_url = config.get("openai_base_url")
                    active_model = config.get("openai_active_model", "gpt-3.5-turbo")

                    client = OpenAI(base_url=base_url, api_key=active_key)
                    response = client.chat.completions.create(
                        model=active_model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.9,
                        max_tokens=2048,
                        timeout=30
                    )
                    if response.choices and response.choices[0].message.content:
                        return response.choices[0].message.content.strip()
                    else:
                        raise ValueError("Empty response")

            except Exception as e:
                err_str = str(e).lower()
                # If quota error and auto-switch enabled
                if "429" in err_str and ("quota" in err_str or "exhausted" in err_str):
                    if config.get("auto_switch_api_keys", False):
                        # Try to switch key
                        if provider == "gemini":
                            new_key = self.gemini.switch_to_next_key()
                        else:
                            new_key = self.openai.switch_to_next_key()
                        if new_key:
                            continue

                # Last attempt - raise error
                if attempt >= max_attempts - 1:
                    raise e

        return lang.get("welcome_error", "Welcome to ClipGen!")

    def shutdown(self) -> None:
        """Shut down the application."""
        logger.info("Shutting down...")

        # Stop hotkey listener
        self.hotkey_listener.stop()

        # Stop queue worker
        self.hotkey_queue.put(None)

        # Save settings
        self.config.save()

        # Hide window and tray
        self.window.hide()
        self.window.tray.hide()

        # Quit Qt
        self.qt_app.quit()
