"""Main application class with composition-based architecture."""

import os
import sys
import time
import datetime
import random
import threading
import logging
from queue import Queue, Empty

from PyQt5.QtWidgets import QApplication

from .core.config import ConfigManager
from .core.constants import __version__, APPLICATION_PATH
from .utils.i18n import I18nManager
from .utils.proxy import apply_proxy
from .utils.autostart import is_autostart_enabled
from .utils.clipboard import ClipboardHandler
from .utils.process_guard import sweep_orphaned_helpers_async
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
        # Startup milestones go to fault_log.txt — frozen startup hangs are
        # otherwise undebuggable (no console, no logs yet).
        from .main import _bootstrap_log as _mark

        _mark("app: loading config")
        # Configuration
        self.config = ConfigManager()

        # Apply proxy settings
        apply_proxy(self.config.config)

        # Internationalization
        self.i18n = I18nManager(self.config.config)

        _mark("app: creating providers")
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

        # Voice transcription components are lazy-initialized — created only
        # when the user enables transcription (or when a transcription hotkey
        # actually fires). They depend on faster-whisper / sounddevice which
        # may not be installed yet.
        self.model_manager = None
        self.transcriber = None

        # Apply UI scaling BEFORE creating QApplication
        scale = self.config.config.get("ui_scale", 1.0)
        if scale != 1.0:
            os.environ["QT_SCALE_FACTOR"] = str(scale)

        _mark("app: creating QApplication")
        # Qt application
        self.qt_app = QApplication(sys.argv)

        _mark("app: building MainWindow")
        # Main window
        self.window = MainWindow(self)
        _mark("app: MainWindow ready")

        # Connect processor callbacks to window signals
        self._connect_processor_callbacks()

        _mark("app: init transcription")
        # Build transcription pipeline if user enabled it.
        self._maybe_init_transcription()

        _mark("app: starting hotkey listener")
        # Start hotkey listener
        self.hotkey_listener.start()

        # Start queue worker
        self._start_queue_worker()

        # Kill transcription helper processes orphaned by a previous run
        # (e.g. after a crash) so model weights don't pile up in memory.
        sweep_orphaned_helpers_async()

        # Log startup
        logger.info(f"ClipGen v{__version__} started")

        # Sync autostart button
        self.window.settings_tab.set_autostart_checked(is_autostart_enabled())

        _mark("app: init complete")
        # Refresh UI
        self.window.refresh_all_signal.emit()

        # Welcome message: only fire when transcription preload is OFF.
        # When preload is ON, parallel httpx/Gemini network IO during
        # CUDA model init has been observed to coincide with native
        # access violations in CTranslate2. Skipping welcome on those
        # launches keeps the startup path clean for diagnosing the crash.
        tr_cfg = self.config.config.get("transcription", {})
        if not tr_cfg.get("preload_on_start", False):
            threading.Thread(
                target=self._load_welcome_message_when_idle,
                daemon=True,
            ).start()
        else:
            # Just emit a one-line greeting so the log isn't empty.
            self.window.log_signal.emit(
                self.i18n.lang.get("logs", {}).get("app_started", "ClipGen started"),
                ACCENT_BLUE,
            )

    def _connect_processor_callbacks(self) -> None:
        """Connect processor callbacks to window signals."""
        self.processor.on_start = lambda: self.window.start_working_signal.emit()
        self.processor.on_success = lambda d: self.window.success_signal.emit(d)
        self.processor.on_error = lambda: self.window.error_signal.emit()
        self.processor.on_key_switch = lambda n: self.window.flash_tray_signal.emit()
        self.processor.on_log = lambda m, c: self.window.log_signal.emit(m, c)
        self.processor.on_explanation = lambda t, c: self.window.show_explanation_signal.emit(t, c)

    def _start_queue_worker(self) -> None:
        """Start the hotkey queue worker thread.

        Routes events to either the AI text processor or the voice
        transcriber depending on the hotkey ``type``.
        """
        def worker():
            while True:
                try:
                    event = self.hotkey_queue.get(timeout=1.0)
                except Empty:
                    continue
                if event is None:
                    break

                try:
                    kind = event.get("kind", "text_action")

                    if kind == "transcription_start":
                        if not self._ensure_transcription_ready():
                            continue
                        self.transcriber.on_press(event.get("hotkey") or {})
                        continue

                    if kind == "transcription_stop":
                        if self.transcriber is None:
                            continue
                        self.transcriber.on_release(event.get("hotkey") or {})
                        continue

                    # Default: AI text action
                    action = event.get("action", "")
                    prompt = event.get("prompt", "")
                    threading.Thread(
                        target=self.processor.handle_hotkey,
                        args=(action, prompt),
                        daemon=True
                    ).start()

                except Exception:
                    logger.exception("Hotkey queue worker failed to dispatch event")
                    continue

        self.queue_worker_thread = threading.Thread(target=worker, daemon=True)
        self.queue_worker_thread.start()

    # ------------------------------------------------------------------ transcription

    def _ensure_transcription_ready(self) -> bool:
        """Ensure transcriber/model_manager exist before dispatching events.

        Returns True if available, False and logs an error otherwise.
        """
        tr_cfg = self.config.config.get("transcription", {})
        if not tr_cfg.get("enabled", False):
            self.window.log_signal.emit(
                self.i18n.lang.get("logs", {}).get(
                    "transcription_disabled",
                    "Voice transcription is disabled in settings"
                ),
                ERROR_RED,
            )
            return False

        if self.transcriber is None:
            ok = self._maybe_init_transcription(force=True)
            if not ok:
                return False

        return self.transcriber is not None

    def _maybe_init_transcription(self, force: bool = False) -> bool:
        """Lazily build the configured ASR engine and the Transcriber.

        Imports the heavyweight ML modules only when this is called and
        only for the engine the user actually picked. Returns True when
        the components were created (or already existed).
        """
        if self.transcriber is not None:
            return True

        tr_cfg = self.config.config.get("transcription", {})
        if not force and not tr_cfg.get("enabled", False):
            return False

        try:
            from .transcription.deps import check_dependencies_for_engine
            from .transcription.engine_factory import create_asr_manager
            from .transcription.transcriber import Transcriber
        except Exception as exc:
            logger.exception("Failed to import transcription module")
            self.window.log_signal.emit(
                f"Transcription init failed: {exc}", ERROR_RED
            )
            return False

        engine = (tr_cfg.get("engine") or "whisper").lower()

        # Check the lightweight required deps first; CUDA libs are optional.
        missing = check_dependencies_for_engine(engine, include_cuda=False)
        if missing:
            logs = self.i18n.lang.get("logs", {})
            # Prefer an engine-specific message so the user knows which deps
            # to install and isn't told "Whisper" when they picked Parakeet.
            template = logs.get(
                f"transcription_deps_missing_{engine}",
                logs.get(
                    "transcription_deps_missing",
                    "Transcription dependencies not installed. Open Settings to install."
                ),
            )
            self.window.log_signal.emit(
                template.format(packages=", ".join(missing)) if "{packages}" in template else template,
                ERROR_RED,
            )
            return False

        self.model_manager = create_asr_manager(
            self.config.config, self.i18n.lang
        )
        self.transcriber = Transcriber(
            self.config.config,
            self.i18n.lang,
            self.model_manager,
            self.clipboard,
        )

        # Wire signals through to the main window.
        self.model_manager.log_signal.connect(self.window.log_signal)
        self.model_manager.state_changed.connect(
            self.window.transcription_state_signal
        )
        self.model_manager.info_signal.connect(
            self.window.transcription_info_signal
        )

        self.transcriber.log_signal.connect(self.window.log_signal)
        self.transcriber.ui_state_changed.connect(
            self.window.transcription_ui_signal
        )
        self.transcriber.transcribing_time_signal.connect(
            self.window.transcription_time_signal
        )

        # Optional preload at startup.
        # Defer via QTimer so Qt has fully finished its own DLL loading
        # before we touch CUDA — kicking off heavy ML init too early in
        # the frozen .exe boot sequence has been observed to crash with a
        # 0xC0000005 access violation.
        if tr_cfg.get("preload_on_start", False):
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(3000, self.model_manager.load_async)

        return True

    def _reinit_transcription(self, new_engine: str) -> bool:
        """Hot-switch the ASR engine: tear down the current one and re-init.

        Skipped while a recording is active so we don't pull the model out
        from under an in-flight transcription. Returns True on success.
        """
        new_engine = (new_engine or "whisper").lower()
        # Refuse the swap mid-recording — UI must wait until release.
        if self.transcriber is not None and getattr(self.transcriber, "_active", False):
            self.window.log_signal.emit(
                self.i18n.lang.get("logs", {}).get(
                    "transcription_switch_busy",
                    "Cannot switch engine while a recording is in progress."
                ),
                ERROR_RED,
            )
            return False

        # Remember whether transcription was enabled so we know whether to
        # rebuild after the engine change.
        tr_cfg = self.config.config.setdefault("transcription", {})
        tr_cfg["engine"] = new_engine
        try:
            self.config.save()
        except Exception:
            logger.exception("Failed to save engine choice")

        # Tear down the previous engine + transcriber so the next call to
        # ``_maybe_init_transcription`` starts from a clean slate.
        if self.transcriber is not None:
            try:
                self.transcriber.shutdown()
            except Exception:
                logger.exception("Transcriber shutdown failed during reinit")
        if self.model_manager is not None:
            try:
                self.model_manager.shutdown(release_model=True)
            except Exception:
                logger.exception("Model manager shutdown failed during reinit")
        self.transcriber = None
        self.model_manager = None

        if not tr_cfg.get("enabled", False):
            return True  # disabled — nothing to spin up

        return self._maybe_init_transcription(force=True)

    def run(self) -> int:
        """Run the application.

        Returns:
            Exit code
        """
        self.window.show()
        return self.qt_app.exec_()

    def _load_welcome_message_when_idle(self) -> None:
        """Wait until any in-flight model download/load is done, then post
        the AI welcome message. Keeps the log readable on first launch when
        Whisper weights are downloading.
        """
        # If transcription is enabled and the model manager is busy
        # downloading or loading, hold off — otherwise the multi-paragraph
        # welcome card visually buries the download progress.
        try:
            for _ in range(120):  # up to 2 minutes
                mm = getattr(self, "model_manager", None)
                if mm is None:
                    break
                state = mm.get_state()
                if state in ("downloading", "loading"):
                    time.sleep(1.0)
                    continue
                break
        except Exception:
            pass
        self._load_welcome_message()

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
                            # Persist the rotation so a restart doesn't fall
                            # back to the exhausted key.
                            try:
                                self.config.save()
                            except Exception:
                                logger.exception("Failed to persist API key rotation")
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

        # Voice transcription cleanup (no-op if it was never initialized).
        if self.transcriber is not None:
            try:
                self.transcriber.shutdown()
            except Exception:
                logger.exception("Transcriber shutdown failed")
        if self.model_manager is not None:
            try:
                self.model_manager.shutdown()
            except Exception:
                logger.exception("Model manager shutdown failed")

        # Save settings
        self.config.save()

        # Hide window and tray
        self.window.hide()
        self.window.tray.hide()

        # Quit Qt
        self.qt_app.quit()
