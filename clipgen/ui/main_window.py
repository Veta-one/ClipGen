"""Main application window."""

import logging
import os
import time
from typing import Optional

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QStackedWidget, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon
from ctypes import windll, c_bool, c_int, byref

logger = logging.getLogger("ClipGen")

from .styles import Styles
from .tray import TrayIconManager
from .tabs import LogTab, SettingsTab, PromptsTab, HelpTab
from .dialogs import InfoMessageBox, CustomMessageBox
from .notifications import ToastNotification
from .overlay import (
    TranscriptionOverlay,
    STATE_HIDDEN,
    STATE_LOADING,
    STATE_RECORDING,
    STATE_TRANSCRIBING,
    STATE_READY as OV_READY,
    STATE_ERROR as OV_ERROR,
)
from ..core.constants import resource_path


class MainWindow(QMainWindow):
    """Main application window with tabs."""

    # Signals for cross-thread communication
    log_signal = pyqtSignal(str, str)  # message, color
    flash_tray_signal = pyqtSignal()
    start_working_signal = pyqtSignal()
    success_signal = pyqtSignal(str)  # duration
    error_signal = pyqtSignal()
    refresh_all_signal = pyqtSignal()
    show_explanation_signal = pyqtSignal(str, str)  # explanation text, hotkey_color for learning mode

    # Update signals (called from background thread)
    # version, url, notes, history: list[(version, body)] of skipped releases
    update_found_signal = pyqtSignal(str, str, str, object)
    update_not_found_signal = pyqtSignal()

    # Voice transcription signals (cross-thread safe)
    transcription_state_signal = pyqtSignal(str)            # model state
    transcription_ui_signal = pyqtSignal(str, str)          # ui state, message
    transcription_info_signal = pyqtSignal(dict)            # runtime info dict
    transcription_time_signal = pyqtSignal(str)             # elapsed seconds

    def __init__(self, app):
        """Initialize main window.

        Args:
            app: ClipGenApp instance
        """
        super().__init__()
        self.app = app
        self.config = app.config.config
        self.lang = app.i18n.lang

        self.is_pinned = False
        self.working_timer = QTimer(self)
        self.start_time = 0

        # Model test timers for live updates
        self.model_test_start_times = {}  # {(provider, index): start_time}
        self.model_test_qtimers = {}  # {(provider, index): QTimer}

        self._setup_window()
        self._setup_ui()
        self._setup_tray()
        self._connect_signals()

    def _setup_window(self) -> None:
        """Set up window properties."""
        from .. import __version__
        app_title = self.lang.get("app_title", "ClipGen")
        self.setWindowTitle(f"{app_title} v{__version__}")
        self.setMinimumSize(300, 200)
        self.resize(554, 632)

        # Apply global application styles (tooltips, etc)
        self._apply_global_styles()

        # Apply dark theme to window
        self.setStyleSheet(Styles.main_window())

        # Set window icon
        icon_path = resource_path("ClipGen.ico")
        if os.path.exists(icon_path):
            app_icon = QIcon(icon_path)
            self.setWindowIcon(app_icon)
            from PyQt5.QtWidgets import QApplication as QtApp
            QtApp.instance().setWindowIcon(app_icon)

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Action buttons (hotkeys display)
        self._setup_action_buttons(layout)

        # Navigation
        self._setup_navigation(layout)

        # Content stack
        self.content_stack = QStackedWidget()
        layout.addWidget(self.content_stack, 1)

        # Create tabs
        self.log_tab = LogTab(self.lang)
        self.log_tab.set_config(self.config)  # For smart log formatting
        self.settings_tab = SettingsTab(self.config, self.lang)
        self.prompts_tab = PromptsTab(self.config, self.lang)
        self.help_tab = HelpTab(self.lang)

        self.content_stack.addWidget(self.log_tab)      # Index 0
        self.content_stack.addWidget(self.settings_tab)  # Index 1
        self.content_stack.addWidget(self.prompts_tab)   # Index 2
        self.content_stack.addWidget(self.help_tab)      # Index 3

        # Toast notification for learning mode
        self.toast = ToastNotification()

        # Top-right overlay for transcription status
        self.transcription_overlay = TranscriptionOverlay(self.lang)

    def _setup_action_buttons(self, layout: QVBoxLayout) -> None:
        """Set up hotkey action buttons."""
        self.action_widget = QWidget()
        self.action_layout = QVBoxLayout(self.action_widget)
        self.action_layout.setAlignment(Qt.AlignTop)
        self.action_layout.setSpacing(5)
        self.action_layout.setContentsMargins(0, 0, 0, 0)

        self.action_buttons = {}

        # Timer for resize updates
        self.button_resize_timer = QTimer()
        self.button_resize_timer.setSingleShot(True)
        self.button_resize_timer.timeout.connect(self._refresh_action_buttons)

        layout.addWidget(self.action_widget, stretch=0)

    def _refresh_action_buttons(self) -> None:
        """Refresh action buttons from config."""
        # Clear existing buttons
        for widget in self.action_widget.findChildren(QPushButton):
            widget.deleteLater()
        self.action_buttons.clear()

        # Clear existing layouts
        while self.action_layout.count():
            item = self.action_layout.takeAt(0)
            if item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()

        width = self.action_widget.width()
        if width <= 0:
            width = 500  # Default width on first run

        buttons_per_row = max(1, width // 160)
        hotkeys = self.config.get("hotkeys", [])
        num_rows = (len(hotkeys) + buttons_per_row - 1) // buttons_per_row if hotkeys else 0
        rows = [[] for _ in range(num_rows)]

        tooltips = self.lang.get("tooltips", {})
        tooltip_template = tooltips.get("main_action_button", "Press {combination}")

        for i, hotkey in enumerate(hotkeys):
            row_idx = i // buttons_per_row
            color = hotkey.get("log_color", "#FFFFFF")
            name = hotkey.get("name", "")
            combination = hotkey.get("combination", "")
            hotkey_type = hotkey.get("type", "text_action")
            is_voice = hotkey_type == "transcription"

            display_name = (f"[voice] {name}" if is_voice else name)
            btn = QPushButton(display_name)
            btn.setToolTip(tooltip_template.format(combination=combination))
            btn.setFixedHeight(30)
            btn.setStyleSheet(f"""
                QPushButton {{
                    color: {color};
                    background-color: #333333;
                    border-radius: 10px;
                    padding: 5px 10px;
                }}
                QPushButton:hover {{
                    background-color: {color};
                    color: #333333;
                }}
                QPushButton:pressed {{
                    background-color: {color}80;
                }}
            """)

            if is_voice:
                # Push-to-talk semantics on the action button.
                btn.pressed.connect(
                    lambda h=hotkey: self._trigger_voice_press(h)
                )
                btn.released.connect(
                    lambda h=hotkey: self._trigger_voice_release(h)
                )
            else:
                btn.clicked.connect(
                    lambda checked, h=hotkey: self._trigger_hotkey(h)
                )

            rows[row_idx].append(btn)
            self.action_buttons[combination] = btn

        for row in rows:
            row_layout = QHBoxLayout()
            row_layout.setSpacing(8)
            for btn in row:
                btn.setMinimumWidth(0)
                row_layout.addWidget(btn, stretch=1)
            self.action_layout.addLayout(row_layout)

    def _trigger_hotkey(self, hotkey: dict) -> None:
        """Trigger a hotkey action via queue."""
        self.app.hotkey_queue.put({
            "kind": "text_action",
            "action": hotkey.get("name", ""),
            "prompt": hotkey.get("prompt", "")
        })

    def _trigger_voice_press(self, hotkey: dict) -> None:
        """Push-to-talk press from action button."""
        self.app.hotkey_queue.put({
            "kind": "transcription_start",
            "action": hotkey.get("name", ""),
            "hotkey": hotkey,
        })

    def _trigger_voice_release(self, hotkey: dict) -> None:
        """Push-to-talk release from action button."""
        self.app.hotkey_queue.put({
            "kind": "transcription_stop",
            "action": hotkey.get("name", ""),
            "hotkey": hotkey,
        })

    def _setup_navigation(self, layout: QVBoxLayout) -> None:
        """Set up navigation buttons."""
        nav_widget = QWidget()
        nav_layout = QHBoxLayout(nav_widget)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(5)

        tabs = self.lang.get("tabs", {})

        self.nav_buttons = []
        nav_style = Styles.nav_button()  # Single stylesheet for all buttons
        tooltips = self.lang.get("tooltips", {})

        # Tab keys with their tooltip keys
        tab_configs = [
            ("logs", "Logs", "logs_tab"),
            ("settings", "Settings", "settings_tab"),
            ("prompts", "Prompts", "prompts_tab"),
            ("help", "Help", "help_tab")
        ]

        for i, (key, default, tooltip_key) in enumerate(tab_configs):
            btn = QPushButton(tabs.get(key, default))
            btn.setStyleSheet(nav_style)
            btn.setProperty("active", "true" if i == 0 else "false")
            btn.setToolTip(tooltips.get(tooltip_key, ""))
            btn.clicked.connect(lambda checked, idx=i: self._switch_tab(idx))
            nav_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        nav_layout.addStretch()

        # Pin button (transparent, changes color on hover)
        self.pin_button = QPushButton("•")
        self.pin_button.setFixedSize(28, 28)
        self.pin_button.setObjectName("pinButton")
        self.pin_button.setToolTip(
            self.lang.get("tooltips", {}).get("pin_window", "Pin/Unpin window on top")
        )
        self.pin_button.setStyleSheet("""
            QPushButton#pinButton {
                font-size: 16px;
                background-color: transparent;
                border: none;
                color: #888888;
            }
            QPushButton#pinButton:hover {
                color: #A3BFFA;
            }
        """)
        self.pin_button.clicked.connect(self._toggle_pin)
        nav_layout.addWidget(self.pin_button)

        layout.addWidget(nav_widget)

    def _switch_tab(self, index: int) -> None:
        """Switch to a tab."""
        self.content_stack.setCurrentIndex(index)

        for i, btn in enumerate(self.nav_buttons):
            btn.setProperty("active", "true" if i == index else "false")
            # Force style refresh without changing stylesheet
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _toggle_pin(self) -> None:
        """Toggle always-on-top."""
        self.is_pinned = not self.is_pinned
        flags = self.windowFlags()

        if self.is_pinned:
            self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
            self.pin_button.setText("■")
        else:
            self.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
            self.pin_button.setText("•")

        self.show()

    def _setup_tray(self) -> None:
        """Set up system tray icon."""
        self.tray = TrayIconManager(self, self.lang)
        self.tray.on_show_hide = self._toggle_visibility
        self.tray.on_quit = self._quit_application
        self.tray.show()

    def _connect_signals(self) -> None:
        """Connect all signals."""
        # Log signal
        self.log_signal.connect(self.log_tab.append_log)

        # Tray signals
        self.flash_tray_signal.connect(self.tray.flash_warning)
        self.start_working_signal.connect(self._start_working)
        self.success_signal.connect(self._on_success)
        self.error_signal.connect(self._on_error)

        # Working timer
        self.working_timer.timeout.connect(self._update_working_time)

        # Settings tab signals
        self._connect_settings_signals()

        # Prompts tab signals
        self._connect_prompts_signals()

        # Log tab buttons
        self.log_tab.stop_button.clicked.connect(self._stop_current_task)
        self.log_tab.check_updates_button.clicked.connect(self._check_updates)
        self.log_tab.instructions_button.clicked.connect(self._show_instructions)

        # Refresh signal
        self.refresh_all_signal.connect(self._refresh_all)

        # Update signals
        self.update_found_signal.connect(self._on_update_found)
        self.update_not_found_signal.connect(self._on_update_not_found)

        # Learning mode explanation signal
        self.show_explanation_signal.connect(self._show_explanation)

        # Transcription signals
        self.transcription_ui_signal.connect(self._on_transcription_ui_state)
        self.transcription_state_signal.connect(self._on_transcription_model_state)
        self.transcription_info_signal.connect(self._on_transcription_info)
        self.transcription_time_signal.connect(self._on_transcription_time)

        # Auto-check for updates after 3 seconds
        QTimer.singleShot(3000, self._auto_check_updates)

    def _auto_check_updates(self) -> None:
        """Automatic update check on startup (silent, no log)."""
        from ..utils.updates import UpdateChecker
        from .. import __version__

        checker = UpdateChecker(
            __version__,
            self.config.get("skipped_version", ""),
            lambda v, u, n, h: self.update_found_signal.emit(v, u, n, h),
            lambda: None,  # No callback for not found (silent)
            is_manual=False
        )
        checker.start()

    def _connect_settings_signals(self) -> None:
        """Connect settings tab signals to app methods."""
        st = self.settings_tab

        # Provider
        st.provider_changed.connect(self._on_provider_changed)

        # Gemini
        st.gemini_key_added.connect(lambda: self._add_key("gemini"))
        st.gemini_key_deleted.connect(lambda i: self._delete_key("gemini", i))
        st.gemini_key_activated.connect(lambda i: self._activate_key("gemini", i))
        st.gemini_key_updated.connect(lambda i, t: self._update_key("gemini", i, t))
        st.gemini_key_test.connect(lambda i: self._test_key("gemini", i))

        st.gemini_model_added.connect(lambda: self._add_model("gemini"))
        st.gemini_model_deleted.connect(lambda i: self._delete_model("gemini", i))
        st.gemini_model_activated.connect(lambda i: self._activate_model("gemini", i))
        st.gemini_model_updated.connect(lambda i, t: self._update_model("gemini", i, t))
        st.gemini_model_test.connect(lambda i: self._test_model("gemini", i))

        # OpenAI
        st.openai_base_url_changed.connect(self._on_base_url_changed)
        st.openai_key_added.connect(lambda: self._add_key("openai"))
        st.openai_key_deleted.connect(lambda i: self._delete_key("openai", i))
        st.openai_key_activated.connect(lambda i: self._activate_key("openai", i))
        st.openai_key_updated.connect(lambda i, t: self._update_key("openai", i, t))
        st.openai_key_test.connect(lambda i: self._test_key("openai", i))

        st.openai_model_added.connect(lambda: self._add_model("openai"))
        st.openai_model_deleted.connect(lambda i: self._delete_model("openai", i))
        st.openai_model_activated.connect(lambda i: self._activate_model("openai", i))
        st.openai_model_updated.connect(lambda i, t: self._update_model("openai", i, t))
        st.openai_model_test.connect(lambda i: self._test_model("openai", i))

        # Other
        st.autostart_toggled.connect(self._on_autostart_toggled)
        st.auto_switch_toggled.connect(self._on_auto_switch_toggled)
        st.visibility_toggled.connect(self._on_visibility_toggled)
        st.proxy_enabled_changed.connect(self._on_proxy_enabled)
        st.proxy_type_changed.connect(self._on_proxy_type)
        st.proxy_string_changed.connect(self._on_proxy_string)
        st.language_changed.connect(self._on_language_changed)
        st.scale_changed.connect(self._on_scale_changed)

        # Transcription
        st.transcription_enable_toggled.connect(self._on_tr_enable_toggled)
        st.transcription_preload_toggled.connect(self._on_tr_preload_toggled)
        st.transcription_load_clicked.connect(self._on_tr_load_clicked)
        st.transcription_unload_clicked.connect(self._on_tr_unload_clicked)
        st.transcription_install_clicked.connect(self._on_tr_install_clicked)
        st.transcription_engine_changed.connect(self._on_tr_engine_changed)
        st.transcription_model_changed.connect(self._on_tr_model_changed)
        st.transcription_device_changed.connect(self._on_tr_device_changed)
        st.transcription_compute_changed.connect(self._on_tr_compute_changed)
        st.transcription_auto_unload_changed.connect(self._on_tr_auto_unload_changed)
        st.transcription_default_language_changed.connect(self._on_tr_default_lang_changed)
        st.transcription_beam_size_changed.connect(self._on_tr_beam_changed)
        st.transcription_vad_toggled.connect(self._on_tr_vad_toggled)
        st.transcription_hallucinations_toggled.connect(self._on_tr_hall_toggled)
        st.transcription_feedback_sounds_toggled.connect(self._on_tr_sounds_toggled)
        st.transcription_input_device_changed.connect(self._on_tr_input_device_changed)
        st.parakeet_provider_changed.connect(self._on_parakeet_provider_changed)
        st.parakeet_quantization_changed.connect(self._on_parakeet_quantization_changed)

    def _connect_prompts_signals(self) -> None:
        """Connect prompts tab signals."""
        pt = self.prompts_tab

        pt.hotkey_added.connect(self._add_hotkey)
        pt.hotkey_deleted.connect(self._delete_hotkey)
        pt.combination_changed.connect(
            lambda i, c: self.app.hotkey_manager.update_combination(i, c)
        )
        pt.name_changed.connect(
            lambda i, n: self.app.hotkey_manager.update_name(i, n)
        )
        pt.prompt_changed.connect(
            lambda i, p: self.app.hotkey_manager.update_prompt(i, p)
        )
        pt.color_changed.connect(
            lambda i, c: self.app.hotkey_manager.update_color(i, c)
        )
        pt.use_custom_model_changed.connect(
            lambda i, v: self.app.hotkey_manager.update_use_custom_model(i, v)
        )
        pt.custom_provider_changed.connect(
            lambda i, v: self.app.hotkey_manager.update_custom_provider(i, v)
        )
        pt.custom_model_changed.connect(
            lambda i, v: self.app.hotkey_manager.update_custom_model(i, v)
        )
        pt.learning_mode_changed.connect(
            lambda i, v: self.app.hotkey_manager.update_learning_mode(i, v)
        )
        pt.learning_prompt_changed.connect(
            lambda i, v: self.app.hotkey_manager.update_learning_prompt(i, v)
        )
        pt.type_changed.connect(self._on_hotkey_type_changed)
        pt.transcription_language_changed.connect(
            lambda i, v: self.app.hotkey_manager.update_transcription_language(i, v)
        )
        pt.transcription_initial_prompt_changed.connect(
            lambda i, v: self.app.hotkey_manager.update_transcription_initial_prompt(i, v)
        )
        pt.transcription_strip_trailing_period_changed.connect(
            lambda i, v: self.app.hotkey_manager.update_transcription_strip_trailing_period(i, v)
        )

    # === Event Handlers ===

    def _on_provider_changed(self, index: int) -> None:
        self.config["provider"] = "gemini" if index == 0 else "openai"
        self.app.config.save()

    def _on_base_url_changed(self, text: str) -> None:
        self.config["openai_base_url"] = text.strip()
        self.app.config.save()

    def _add_key(self, provider: str) -> None:
        key = "api_keys" if provider == "gemini" else "openai_api_keys"
        self.config[key].append({
            "key": "", "name": "New Key", "usage_timestamps": [], "active": False
        })
        if len(self.config[key]) == 1:
            self.config[key][0]["active"] = True
        self.app.config.save()
        self._refresh_all()

    def _delete_key(self, provider: str, index: int) -> None:
        key = "api_keys" if provider == "gemini" else "openai_api_keys"
        if 0 <= index < len(self.config[key]):
            key_data = self.config[key][index]
            key_value = key_data.get("key", "")
            key_name = key_data.get("name", "")

            # Show confirmation if key has data
            if key_value or key_name:
                dialogs_lang = self.lang.get("dialogs", {})
                identifier = key_name if key_name else f"#{index + 1}"
                msg = dialogs_lang.get("confirm_delete_api_key_message", "Delete API key '{key_identifier}'?")
                msg = msg.replace("{key_identifier}", identifier)

                dialog = CustomMessageBox(
                    self,
                    dialogs_lang.get("confirm_delete_title", "Confirm Deletion"),
                    msg,
                    dialogs_lang.get("yes_button", "Yes"),
                    dialogs_lang.get("no_button", "No")
                )
                if dialog.exec_() != dialog.Accepted:
                    return

            was_active = key_data.get("active", False)
            del self.config[key][index]
            if was_active and len(self.config[key]) > 0:
                self.config[key][0]["active"] = True
            self.app.config.save()
            self._refresh_all()

    def _activate_key(self, provider: str, index: int) -> None:
        key = "api_keys" if provider == "gemini" else "openai_api_keys"
        for i, k in enumerate(self.config[key]):
            k["active"] = (i == index)
        self.app.config.save()

        if provider == "gemini":
            self.app.gemini._configure_initial()

    def _update_key(self, provider: str, index: int, text: str) -> None:
        key = "api_keys" if provider == "gemini" else "openai_api_keys"
        if 0 <= index < len(self.config[key]):
            self.config[key][index]["key"] = text
            self.app.config.save()

    def _test_key(self, provider: str, index: int) -> None:
        import threading

        # Update button to testing status immediately
        self.settings_tab.update_test_button_status(provider, "key", index, "testing")

        # Also update config status
        key = "api_keys" if provider == "gemini" else "openai_api_keys"
        if 0 <= index < len(self.config.get(key, [])):
            self.config[key][index]["test_status"] = "testing"

        def run_test():
            result = None
            if provider == "gemini":
                result = self.app.tester.test_gemini_key(index)
            else:
                result = self.app.tester.test_openai_key(index)

            # Update config status based on result
            keys = self.config.get(key, [])
            if 0 <= index < len(keys):
                keys[index]["test_status"] = "success" if result and result.success else "error"

            self.app.config.save()
            self.refresh_all_signal.emit()

        threading.Thread(target=run_test, daemon=True).start()

    def _add_model(self, provider: str) -> None:
        key = "gemini_models" if provider == "gemini" else "openai_models"
        self.config[key].append({
            "name": "new-model", "test_status": "not_tested", "test_duration": 0.0
        })
        self.app.config.save()
        self._refresh_all()

    def _delete_model(self, provider: str, index: int) -> None:
        key = "gemini_models" if provider == "gemini" else "openai_models"
        active_key = "active_model" if provider == "gemini" else "openai_active_model"

        if 0 <= index < len(self.config[key]):
            model_data = self.config[key][index]
            model_name = model_data.get("name", "")

            # Show confirmation if model has a name
            if model_name and model_name != "new-model":
                dialogs_lang = self.lang.get("dialogs", {})
                msg = dialogs_lang.get("confirm_delete_model_message", "Delete model '{model_name}'?")
                msg = msg.replace("{model_name}", model_name)

                dialog = CustomMessageBox(
                    self,
                    dialogs_lang.get("confirm_delete_title", "Confirm Deletion"),
                    msg,
                    dialogs_lang.get("yes_button", "Yes"),
                    dialogs_lang.get("no_button", "No")
                )
                if dialog.exec_() != dialog.Accepted:
                    return

            was_active = model_name == self.config.get(active_key)
            del self.config[key][index]
            if was_active and len(self.config[key]) > 0:
                self.config[active_key] = self.config[key][0]["name"]
            self.app.config.save()
            self._refresh_all()

    def _activate_model(self, provider: str, index: int) -> None:
        key = "gemini_models" if provider == "gemini" else "openai_models"
        active_key = "active_model" if provider == "gemini" else "openai_active_model"

        if 0 <= index < len(self.config[key]):
            self.config[active_key] = self.config[key][index]["name"]
            self.app.config.save()

    def _update_model(self, provider: str, index: int, text: str) -> None:
        key = "gemini_models" if provider == "gemini" else "openai_models"
        active_key = "active_model" if provider == "gemini" else "openai_active_model"

        if 0 <= index < len(self.config[key]):
            old_name = self.config[key][index]["name"]
            self.config[key][index]["name"] = text
            if self.config.get(active_key) == old_name:
                self.config[active_key] = text
            self.app.config.save()

    def _test_model(self, provider: str, index: int) -> None:
        import threading
        key = "gemini_models" if provider == "gemini" else "openai_models"

        if 0 <= index < len(self.config[key]):
            self.config[key][index]["test_status"] = "testing"

        # Update button to testing status
        self.settings_tab.update_test_button_status(provider, "model", index, "testing")

        # Start live timer
        timer_key = (provider, index)
        start_time = time.time()
        self.model_test_start_times[timer_key] = start_time

        # A rapid re-click would otherwise overwrite the previous QTimer in
        # the dict while it keeps ticking in the background.
        old_timer = self.model_test_qtimers.pop(timer_key, None)
        if old_timer is not None:
            old_timer.stop()
            old_timer.deleteLater()

        # Create and start QTimer for live updates
        timer = QTimer(self)
        timer.timeout.connect(lambda: self._update_model_test_timer_display(provider, index))
        timer.start(100)  # Update every 100ms
        self.model_test_qtimers[timer_key] = timer

        def run_test():
            try:
                if provider == "gemini":
                    self.app.tester.test_gemini_model(index)
                else:
                    self.app.tester.test_openai_model(index, start_time)
                self.app.config.save()
            finally:
                # Stop timer (must be done in main thread)
                self.refresh_all_signal.emit()

        threading.Thread(target=run_test, daemon=True).start()

    def _update_model_test_timer_display(self, provider: str, index: int) -> None:
        """Update the timer display during model testing."""
        timer_key = (provider, index)
        key = "gemini_models" if provider == "gemini" else "openai_models"

        # Check if still testing
        models = self.config.get(key, [])
        if index >= len(models) or models[index].get("test_status") != "testing":
            # Stop timer
            timer = self.model_test_qtimers.pop(timer_key, None)
            if timer is not None:
                timer.stop()
                timer.deleteLater()
            if timer_key in self.model_test_start_times:
                del self.model_test_start_times[timer_key]
            return

        # Update time label
        if timer_key in self.model_test_start_times:
            elapsed = time.time() - self.model_test_start_times[timer_key]
            self.settings_tab.update_model_time_label(provider, index, f"{elapsed:.1f}s")

    def _on_autostart_toggled(self, checked: bool) -> None:
        from ..utils.autostart import set_autostart
        set_autostart(checked)

    def _on_auto_switch_toggled(self) -> None:
        self.config["auto_switch_api_keys"] = not self.config.get("auto_switch_api_keys", False)
        self.app.config.save()
        self._refresh_all()

    def _on_visibility_toggled(self, visible: bool) -> None:
        self.config["api_keys_visible"] = visible
        self.app.config.save()
        self._refresh_all()

    def _on_proxy_enabled(self, enabled: bool) -> None:
        self.config["proxy_enabled"] = enabled
        self.app.config.save()
        from ..utils.proxy import apply_proxy
        apply_proxy(self.config)

    def _on_proxy_type(self, proxy_type: str) -> None:
        self.config["proxy_type"] = proxy_type
        self.app.config.save()
        from ..utils.proxy import apply_proxy
        apply_proxy(self.config)

    def _on_proxy_string(self, proxy_string: str) -> None:
        self.config["proxy_string"] = proxy_string
        self.app.config.save()

    def _on_language_changed(self, language: str) -> None:
        self.config["language"] = language
        self.app.config.save()
        self.app.i18n.load()
        self.lang = self.app.i18n.lang

        # Update processor language for learning mode prompts
        self.app.processor.lang = self.app.i18n.lang

        # Propagate language to transcription components if active.
        if getattr(self.app, "transcriber", None) is not None:
            self.app.transcriber.update_lang(self.app.i18n.lang)
        if getattr(self.app, "model_manager", None) is not None:
            self.app.model_manager.update_lang(self.app.i18n.lang)
        if hasattr(self, "transcription_overlay"):
            self.transcription_overlay.update_lang(self.app.i18n.lang)

        # Update all UI elements with new language
        self._update_all_language()

    def _update_all_language(self) -> None:
        """Update all UI elements with the current language."""
        from .. import __version__
        lang = self.lang

        # Update window title with version
        app_title = lang.get("app_title", "ClipGen")
        self.setWindowTitle(f"{app_title} v{__version__}")

        # Update navigation buttons
        tabs = lang.get("tabs", {})
        tab_keys = [("logs", "Logs"), ("settings", "Settings"), ("prompts", "Prompts"), ("help", "Help")]
        for i, (key, default) in enumerate(tab_keys):
            if i < len(self.nav_buttons):
                self.nav_buttons[i].setText(tabs.get(key, default))

        # Update all tabs
        self.log_tab.update_language(lang)
        self.settings_tab.update_language(lang)
        self.prompts_tab.update_language(lang)
        self.help_tab.update_language(lang)

        # Update tray menu
        self.tray.update_menu_text(lang)

        # Update pin button tooltip
        self.pin_button.setToolTip(
            lang.get("tooltips", {}).get("pin_window", "Pin/Unpin window on top")
        )

        # Update action buttons (they use hotkey names from config, not lang)
        self._refresh_action_buttons()

    def _on_scale_changed(self, delta: float) -> None:
        current = self.config.get("ui_scale", 1.0)
        new_scale = round(current + delta, 1)
        new_scale = max(0.8, min(3.0, new_scale))

        if new_scale != current:
            self.config["ui_scale"] = new_scale
            self.app.config.save()
            self.settings_tab.scale_label.setText(f"{int(new_scale * 100)}%")
            title = self.lang.get("dialogs", {}).get("restart_required_title", "Restart Required")
            message = self.lang.get("dialogs", {}).get(
                "restart_required_message",
                "Scale changed to {scale}%.<br>Please restart the app to apply changes."
            ).format(scale=int(new_scale * 100))
            dialog = InfoMessageBox(self, title, message)
            dialog.exec_()

    def _add_hotkey(self) -> None:
        self.app.hotkey_manager.add()
        self.prompts_tab.refresh()
        self._refresh_action_buttons()

    def _on_hotkey_type_changed(self, index: int, hotkey_type: str) -> None:
        """Persist hotkey type and refresh action buttons (label changes)."""
        self.app.hotkey_manager.update_type(index, hotkey_type)
        self._refresh_action_buttons()

    def _delete_hotkey(self, index: int) -> None:
        hotkeys = self.config.get("hotkeys", [])
        if 0 <= index < len(hotkeys):
            hotkey_data = hotkeys[index]
            action_name = hotkey_data.get("name", "")
            prompt = hotkey_data.get("prompt", "")
            default_action_name = self.lang.get("default_action_name", "New Action")
            default_prompt = self.lang.get("default_prompt", "")

            # Show confirmation if hotkey has custom data
            if action_name and action_name != default_action_name or prompt and prompt != default_prompt:
                dialogs_lang = self.lang.get("dialogs", {})
                display_name = action_name if action_name else f"#{index + 1}"
                msg = dialogs_lang.get("confirm_delete_message", "Delete action '{action_name}'?")
                msg = msg.replace("{action_name}", display_name)

                dialog = CustomMessageBox(
                    self,
                    dialogs_lang.get("confirm_delete_title", "Confirm Deletion"),
                    msg,
                    dialogs_lang.get("yes_button", "Yes"),
                    dialogs_lang.get("no_button", "No")
                )
                if dialog.exec_() != dialog.Accepted:
                    return

        self.app.hotkey_manager.delete(index)
        self.prompts_tab.refresh()
        self._refresh_action_buttons()

    def _stop_current_task(self) -> None:
        self.app.processor.cancel_current()
        if getattr(self.app, "model_manager", None) is not None:
            self.app.model_manager.cancel_transcription()

    def _check_updates(self) -> None:
        from ..utils.updates import UpdateChecker
        from .. import __version__

        # Log that we're checking (with line break before)
        self.log_tab.append_log("", "#888888")  # Empty line for spacing
        self.log_tab.append_log(
            self.lang.get("logs", {}).get("checking_updates", "Checking for updates..."),
            "#A3BFFA"
        )

        # Use lambdas that emit signals (thread-safe)
        checker = UpdateChecker(
            __version__,
            self.config.get("skipped_version", ""),
            lambda v, u, n, h: self.update_found_signal.emit(v, u, n, h),
            lambda: self.update_not_found_signal.emit(),
            is_manual=True
        )
        checker.start()

    def _on_update_found(self, version: str, url: str, notes: str,
                         history=None) -> None:
        """Show update dialog when new version found.

        ``history`` carries ``(version, body)`` for releases between the
        user's installed version and the new one — rendered on demand via
        an expand link so each release's notes only describe that release.
        """
        import re
        import webbrowser
        from PyQt5.QtWidgets import QDialog
        from ..utils.updates import extract_notes_blocks

        raw_body = notes
        history = [
            (str(ver), body) for ver, body in (history or [])
            if isinstance(body, str) and body.strip()
        ]

        # Release bodies can be multilingual. Open on the UI language
        # (English for any non-Russian locale); the dialog shows a switcher
        # so the user can flip between the available variants. Releases
        # published without markers pass through unchanged.
        blocks = extract_notes_blocks(notes)
        ui_lang = (self.config.get("language", "en") or "en").strip().lower()
        default_code = None
        if blocks:
            if ui_lang in blocks:
                default_code = ui_lang
            elif "en" in blocks:
                default_code = "en"
            else:
                default_code = next(iter(blocks))
            notes = blocks[default_code]

        self.tray.set_update()

        # Log update info
        updates_lang = self.lang.get("updates", {})
        self.log_tab.append_log(
            f"{updates_lang.get('title', 'Update Available')}: v{version}",
            "#28A745"
        )

        # Log release notes if available
        if notes:
            # Clean up markdown for plain text log
            clean_notes = (notes.replace("### ", "").replace("## ", "")
                           .replace("**", "").replace("* ", "• "))
            for line in clean_notes.strip().split("\n"):
                if line.strip():
                    self.log_tab.append_log(f"  {line.strip()}", "#AAAAAA")

        # Build dialog content
        title = updates_lang.get("title", "ClipGen Update Available")
        header = updates_lang.get("message", "A new version is available: <b>v{new_version}</b>").format(
            new_version=version
        )

        # Format release notes (markdown subset -> Qt rich text)
        def notes_to_html(raw: str) -> str:
            formatted = raw.replace("\r\n", "<br>").replace("\n", "<br>")
            # Bold text
            while "**" in formatted:
                formatted = formatted.replace("**", "<b>", 1).replace("**", "</b>", 1)
            # Headers (both ## and ###)
            formatted = re.sub(
                r'#{2,3}\s+(.*?)(<br>|$)',
                r'<h3 style="color: #A3BFFA; margin: 10px 0 5px 0;">\1</h3>',
                formatted
            )
            # Bullet points
            formatted = formatted.replace("* ", "&nbsp;&nbsp;• ")
            return (f"<hr style='border: 1px solid #444; margin: 10px 0;'>"
                    f"<div style='font-family: sans-serif;'>{formatted}</div>")

        def lang_block(body: str, code) -> str:
            """Pick a language block from any release body, with fallbacks."""
            body_blocks = extract_notes_blocks(body)
            if not body_blocks:
                return body
            if code and code in body_blocks:
                return body_blocks[code]
            if "en" in body_blocks:
                return body_blocks["en"]
            return next(iter(body_blocks.values()))

        show_history_label = updates_lang.get(
            "show_history", "Show changes from previous versions"
        )
        history_link = ("<br><a href='clipgen://history' "
                        f"style='color:#81B3F0;'>{show_history_label}</a>")

        def build_variant(code, expanded: bool) -> str:
            """Full dialog HTML for one language, optionally with history."""
            text = lang_block(raw_body, code)
            parts = [header]
            if text:
                parts.append(notes_to_html(text))
            if expanded:
                for past_version, past_body in history:
                    parts.append(
                        "<h2 style='color:#FFFFFF; font-size:15px; "
                        f"margin:16px 0 2px 0;'>ClipGen {past_version}</h2>"
                    )
                    parts.append(notes_to_html(lang_block(past_body, code)))
            elif history:
                parts.append(history_link)
            return "".join(parts)

        full_text = build_variant(default_code, False)

        # One pre-rendered HTML body per language for the dialog switcher.
        html_variants = None
        if len(blocks) > 1:
            html_variants = {
                code: build_variant(code, False) for code in blocks
            }

        # Create dialog. Release notes can be long, so render them in a
        # scrollable body — the action buttons must always stay on screen.
        dialog = CustomMessageBox(
            self,
            title,
            full_text,
            yes_text=updates_lang.get("download_button", "Go to website"),
            no_text=updates_lang.get("skip_button", "Skip this version"),
            scrollable=bool(notes),
            html_variants=html_variants,
            default_variant=default_code
        )

        # The expand link swaps the body for one that appends each skipped
        # release's notes (in the selected language). External links keep
        # opening in the browser.
        if dialog.message_area is not None:
            from PyQt5.QtGui import QDesktopServices

            dialog.message_area.setOpenLinks(False)

            def on_anchor_clicked(qurl) -> None:
                if qurl.toString() == "clipgen://history":
                    expanded = {
                        code: build_variant(code, True) for code in blocks
                    } if len(blocks) > 1 else None
                    if expanded:
                        dialog.update_html_variants(expanded)
                    else:
                        dialog.message_area.setHtml(
                            build_variant(default_code, True)
                        )
                else:
                    QDesktopServices.openUrl(qurl)

            dialog.message_area.anchorClicked.connect(on_anchor_clicked)

        # Override button styles: Download = green, Skip = red
        dialog.yes_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 10px 0;
            }
            QPushButton:hover {
                background-color: #28A745;
            }
        """)
        dialog.no_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 10px 0;
            }
            QPushButton:hover {
                background-color: #C82333;
            }
        """)

        result = dialog.exec_()

        # Reset tray icon
        self.tray.set_default()

        if result == QDialog.Accepted:
            webbrowser.open(url)
        else:
            # Skip this version
            self.config["skipped_version"] = version
            self.app.config.save()

    def _on_update_not_found(self) -> None:
        self.log_tab.append_log(
            self.lang.get("logs", {}).get("update_not_found", "You have the latest version."),
            "#28A745"
        )

    def _show_instructions(self) -> None:
        """Generate and display usage instructions using AI."""
        import threading

        instruction_lang = self.lang.get("instruction", {})
        fallback_lang = self.lang.get("instruction_fallback", {})

        # Check if we have basic_steps (structured instructions)
        basic_steps = instruction_lang.get("basic_steps", [])

        if basic_steps:
            # Use structured instructions from language file
            self.log_signal.emit("\n" + "─" * 40, "#888888")
            self.log_signal.emit(
                instruction_lang.get("title", "ClipGen Usage Instructions"),
                "#A3BFFA"
            )

            for step in basic_steps:
                self.log_signal.emit(step, "#FFFFFF")

            self.log_signal.emit("─" * 40 + "\n", "#888888")
            return

        # Otherwise, generate instructions using AI
        def generate():
            try:
                # Build prompt with hotkeys info
                base_prompt = instruction_lang.get(
                    "prompt",
                    "Write a brief guide on how to use the ClipGen application."
                )

                # Add current language context
                current_lang = self.config.get("language", "en")
                if current_lang == "ru":
                    lang_instruction = "IMPORTANT: Write the response in Russian language."
                else:
                    lang_instruction = f"IMPORTANT: Write the response in the language with code '{current_lang}'."

                # Add hotkeys information
                hotkeys_info = "\n\nAvailable hotkeys:\n"
                for hk in self.config.get("hotkeys", []):
                    hotkeys_info += f"- {hk.get('combination', '')}: {hk.get('name', '')}\n"

                full_prompt = f"{base_prompt}\n{hotkeys_info}\n{lang_instruction}"

                # Generate using active provider
                provider = self.config.get("provider", "gemini")

                if provider == "gemini":
                    result = self._generate_instructions_gemini(full_prompt)
                else:
                    result = self._generate_instructions_openai(full_prompt)

                if result:
                    # Format and display
                    self.log_signal.emit("\n" + "─" * 40, "#888888")
                    self.log_signal.emit(
                        instruction_lang.get("title", "ClipGen Usage Instructions"),
                        "#A3BFFA"
                    )
                    self.log_signal.emit(result, "#FFFFFF")
                    self.log_signal.emit("─" * 40 + "\n", "#888888")
                else:
                    raise Exception("Empty response")

            except Exception as e:
                # Use fallback instructions
                self.log_signal.emit("\n" + "─" * 40, "#888888")
                self.log_signal.emit(
                    fallback_lang.get("title", "How to use ClipGen:"),
                    "#A3BFFA"
                )
                self.log_signal.emit(fallback_lang.get("step1", "1. Copy text to clipboard"), "#FFFFFF")
                self.log_signal.emit(fallback_lang.get("step2", "2. Press hotkey"), "#FFFFFF")
                self.log_signal.emit(fallback_lang.get("step3", "3. Result replaces selection"), "#FFFFFF")
                self.log_signal.emit("─" * 40 + "\n", "#888888")

        threading.Thread(target=generate, daemon=True).start()

    def _generate_instructions_gemini(self, prompt: str) -> str:
        """Generate instructions using Gemini API."""
        import google.generativeai as genai
        from google.generativeai import GenerationConfig

        # Get active API key
        api_keys = self.config.get("api_keys", [])
        active_key = None
        for key_data in api_keys:
            if key_data.get("active"):
                active_key = key_data.get("key")
                break

        if not active_key and api_keys:
            active_key = api_keys[0].get("key")

        if not active_key:
            return None

        genai.configure(api_key=active_key)
        model = genai.GenerativeModel(self.config.get("active_model", "gemini-2.0-flash"))

        response = model.generate_content(
            prompt,
            generation_config=GenerationConfig(
                temperature=0.7,
                max_output_tokens=1024
            ),
            request_options={'timeout': 30}
        )

        return response.text.strip() if response.text else None

    def _generate_instructions_openai(self, prompt: str) -> str:
        """Generate instructions using OpenAI-compatible API."""
        from openai import OpenAI

        # Get active API key
        api_keys = self.config.get("openai_api_keys", [])
        active_key = None
        for key_data in api_keys:
            if key_data.get("active"):
                active_key = key_data.get("key")
                break

        if not active_key and api_keys:
            active_key = api_keys[0].get("key")

        if not active_key:
            return None

        base_url = self.config.get("openai_base_url", "https://api.openai.com/v1")
        model = self.config.get("openai_active_model", "gpt-3.5-turbo")

        client = OpenAI(base_url=base_url, api_key=active_key)

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1024,
            timeout=30
        )

        return response.choices[0].message.content.strip() if response.choices else None

    def _refresh_all(self) -> None:
        """Refresh all UI elements."""
        self.settings_tab.refresh_all()
        self._refresh_action_buttons()

    def _toggle_visibility(self) -> None:
        """Toggle window visibility."""
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.activateWindow()

    def _quit_application(self) -> None:
        """Quit the application."""
        self.app.shutdown()

    def _start_working(self) -> None:
        """Start working animation."""
        self.start_time = time.time()
        self._update_working_time()  # Show initial 0.0
        self.working_timer.start(100)  # Update every 100ms

    def _update_working_time(self) -> None:
        """Update working time display."""
        if self.start_time > 0:
            elapsed = time.time() - self.start_time
            self.tray.set_working(f"{elapsed:.1f}")  # Format: 0.1, 0.2, 0.3...

    def _on_success(self, duration: str) -> None:
        """Handle successful operation."""
        self.working_timer.stop()
        self.start_time = 0
        self.tray.set_success(duration)
        QTimer.singleShot(3000, self.tray.set_default)

    def _on_error(self) -> None:
        """Handle error."""
        self.working_timer.stop()
        self.start_time = 0
        self.tray.set_error()
        QTimer.singleShot(3000, self.tray.set_default)

    def _show_explanation(self, text: str, hotkey_color: str = "#FFFFFF") -> None:
        """Show explanation in toast notification and logs (learning mode)."""
        # Show toast notification
        self.toast.show_message(text, timeout_ms=5000)

        # Also add to logs with colored formatting
        self.log_tab.append_explanation_log(text, hotkey_color)

    def showEvent(self, event) -> None:
        """Apply dark titlebar on show."""
        super().showEvent(event)
        self._set_dark_titlebar()
        # Refresh buttons after window is visible (has correct width)
        QTimer.singleShot(100, self._refresh_action_buttons)
        # Arm transcription buttons only after the launch event queue has
        # fully drained — guards against stray Enter/click events from the
        # terminal that launched ClipGen activating the heavy "Load model"
        # button before the user actually interacts with the UI.
        QTimer.singleShot(1500, self.settings_tab.arm_transcription_buttons)

    def _set_dark_titlebar(self) -> None:
        """Set Windows 11 dark titlebar."""
        try:
            hwnd = int(self.winId())
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                byref(c_bool(True)), 4
            )
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        """Hide to tray on close."""
        event.ignore()
        self.hide()

    def resizeEvent(self, event) -> None:
        """Handle window resize to update button layout."""
        super().resizeEvent(event)
        if hasattr(self, 'button_resize_timer'):
            self.button_resize_timer.start(200)

    def _apply_global_styles(self) -> None:
        """Apply global styles to the application."""
        from PyQt5.QtWidgets import QApplication
        QApplication.instance().setStyleSheet(Styles.global_app_style())

    # ------------------------------------------------------------------ transcription settings handlers

    def _tr_cfg(self) -> dict:
        """Get the transcription config dict, creating it if needed."""
        if "transcription" not in self.config:
            self.config["transcription"] = {}
        return self.config["transcription"]

    def _whisper_cfg(self) -> dict:
        """Whisper engine sub-config (creates it on first access)."""
        tr = self._tr_cfg()
        sub = tr.get("whisper")
        if not isinstance(sub, dict):
            sub = {}
            tr["whisper"] = sub
        return sub

    def _parakeet_cfg(self) -> dict:
        """Parakeet engine sub-config (creates it on first access)."""
        tr = self._tr_cfg()
        sub = tr.get("parakeet")
        if not isinstance(sub, dict):
            sub = {}
            tr["parakeet"] = sub
        return sub

    def _on_tr_enable_toggled(self, enabled: bool) -> None:
        self._tr_cfg()["enabled"] = enabled
        self.app.config.save()
        if enabled:
            # Lazy initialize transcriber + model manager.
            self.app._maybe_init_transcription(force=True)

    def _on_tr_preload_toggled(self, enabled: bool) -> None:
        self._tr_cfg()["preload_on_start"] = enabled
        self.app.config.save()

    def _on_tr_load_clicked(self) -> None:
        if not self.app._maybe_init_transcription(force=True):
            return
        self.app.model_manager.load_async()

    def _on_tr_unload_clicked(self) -> None:
        if self.app.model_manager is not None:
            self.app.model_manager.unload()

    def _on_tr_install_clicked(self) -> None:
        """Install Python deps AND download the active engine's model.

        Flow:
          1. Run pip install for missing dependencies of the picked engine.
             Streams a humanized status line per package (no raw pip noise).
          2. After deps are ready, kick off the engine model download
             (skipped if it's already on disk).
          3. On finish, the load button automatically flips to "Загрузить
             модель" thanks to update_transcription_state().
        """
        from ..transcription.deps import install_dependencies

        if getattr(self.settings_tab, "_tr_install_busy", False):
            if self.app.model_manager is not None:
                self.app.model_manager.cancel_download()
            return

        engine = (self._tr_cfg().get("engine") or "whisper").lower()

        self.settings_tab.set_transcription_install_busy(True)
        # Reset pip progress tracker so previous install state doesn't leak.
        self._pip_progress = {
            "current_pkg": None,    # name from latest "Downloading X (Y MB)" line
            "total_bytes": 0,
            "last_pct": -1,         # last percentage we emitted
            "last_emit_ts": 0.0,    # last time we emitted any progress line
        }
        logs = self.lang.get("logs", {})
        # Prefer engine-specific copy so the log header isn't misleading
        # when the user picked Parakeet but sees "Whisper".
        install_msg = logs.get(
            f"transcription_install_started_{engine}",
            logs.get(
                "transcription_install_started",
                "Installing transcription dependencies..."
            ),
        )
        self.log_signal.emit(install_msg, "#A3BFFA")

        # Humanize raw pip output: only emit a clean line when pip
        # actually starts a meaningful step.
        def on_log(line: str) -> None:
            humanized = self._humanize_pip_line(line)
            if humanized is not None:
                color = "#888888"
                if humanized.startswith("ERROR") or "error" in humanized.lower():
                    color = "#FF5F57"
                self.log_signal.emit(humanized, color)
            else:
                # Drop verbose noise into debug log only.
                logger.debug("pip: %s", line)

        def on_deps_done(ok: bool, err: str = None) -> None:
            if not ok:
                self.settings_tab.set_transcription_install_busy(False)
                logs_lang = self.lang.get("logs", {})
                from ..transcription.deps import PYTHON_NOT_FOUND_ERROR
                if err == PYTHON_NOT_FOUND_ERROR:
                    # The most common first-run blocker on a clean machine:
                    # no system Python. Tell the user exactly what to do.
                    self.log_signal.emit(
                        logs_lang.get(
                            "transcription_python_missing",
                            "Python not found. Install Python 3.10+ from "
                            "python.org (tick \"Add python.exe to PATH\") "
                            "and click Install / Download again."
                        ),
                        "#FF5F57",
                    )
                    return
                try:
                    from ..transcription.diagnostics import write_diagnostics_report
                    report_path = write_diagnostics_report(self.config)
                    logger.info("Transcription diagnostics written to %s", report_path)
                except Exception:
                    logger.debug("Failed to write transcription diagnostics", exc_info=True)
                template = logs_lang.get(
                    "transcription_install_failed",
                    "Installation failed: {error}"
                )
                self.log_signal.emit(
                    template.format(error=err or "unknown"),
                    "#FF5F57",
                )
                return

            # Sanity check: pip reported success, but can THIS process see
            # the packages? On a clean machine the user-site dir is created
            # by the install itself (check_dependencies pulls it onto
            # sys.path); a version-mismatched system Python is the one case
            # that still needs user action.
            from ..transcription.deps import check_dependencies_for_engine
            still_missing = check_dependencies_for_engine(engine, include_cuda=False)
            if still_missing:
                self.settings_tab.set_transcription_install_busy(False)
                import sys as _sys
                version = f"{_sys.version_info.major}.{_sys.version_info.minor}"
                template = self.lang.get("logs", {}).get(
                    "transcription_deps_not_visible",
                    "Packages installed, but the app cannot see them. "
                    "Restart ClipGen. If that does not help, install "
                    "Python {version} from python.org."
                )
                try:
                    msg = template.format(version=version)
                except (KeyError, IndexError, ValueError):
                    msg = template
                self.log_signal.emit(msg, "#FF5F57")
                return

            self.log_signal.emit(
                self.lang.get("logs", {}).get(
                    "transcription_install_done",
                    "Dependencies installed successfully"
                ),
                "#28A745",
            )

            # Initialise transcriber (creates model_manager) and start the
            # model download phase.
            if not self.app._maybe_init_transcription(force=True):
                self.settings_tab.set_transcription_install_busy(False)
                return

            mm = self.app.model_manager
            if engine == "parakeet":
                from ..transcription.parakeet_manager import is_parakeet_downloaded
                already = is_parakeet_downloaded()
            else:
                from ..transcription.model_manager import is_model_downloaded
                already = is_model_downloaded(
                    self._whisper_cfg().get("model", "large-v3")
                )

            if already:
                # Nothing to download.
                self.settings_tab.set_transcription_install_busy(False)
                self.log_signal.emit(
                    self.lang.get("logs", {}).get(
                        "transcription_already_downloaded",
                        "Model already on disk — ready to load."
                    ),
                    "#28A745",
                )
                # Refresh the button label (now downloaded → "Загрузить").
                self.settings_tab.update_transcription_state("unloaded")
                return

            # Watch for download finish to flip the install button back.
            def watch_state(state: str) -> None:
                if state in ("unloaded", "error"):
                    self.settings_tab.set_transcription_install_busy(False)
                    self.settings_tab.update_transcription_state(state)
                    try:
                        mm.state_changed.disconnect(watch_state)
                    except Exception:
                        pass

            mm.state_changed.connect(watch_state)
            self.settings_tab.set_transcription_install_busy(True, cancellable=True)
            mm.download_async()

        install_dependencies(on_log=on_log, on_done=on_deps_done, engine=engine)

    def _humanize_pip_line(self, raw: str) -> Optional[str]:
        """Convert a raw pip stdout line into a friendly status line.

        Returns None if the line is verbose noise we want to suppress.
        Stateful: tracks the currently-downloading package so the
        ``Progress N of M`` lines pip emits with ``--progress-bar raw``
        can be turned into a humanised "65% (158/245 MB)" line.
        """
        line = raw.strip()
        if not line:
            return None

        if line.startswith("Running:"):
            return None  # we already announced the install starting
        if line.startswith("Collecting "):
            pkg = line[len("Collecting "):].split()[0]
            return self.lang.get("logs", {}).get(
                "pip_collecting",
                "  Downloading {package}...",
            ).format(package=pkg)
        if line.startswith("Downloading ") or line.startswith("Using cached "):
            # "Downloading onnxruntime_gpu-1.20.1-...whl (245.4 MB)"
            # "Using cached onnxruntime_gpu-1.20.1-...whl (245.4 MB)"  ← from pip's wheel cache
            # Both are user-visible — the size hint tells the user how long
            # to expect to wait, and "cached" actually means "no download
            # needed, instant install". Also stash filename + size so later
            # "Progress" lines (only for real downloads) can annotate.
            prefix = "Downloading " if line.startswith("Downloading ") else "Using cached "
            rest = line[len(prefix):].strip()
            filename = rest.split(" ")[0]
            # Filter out metadata-only entries — pip prints these when it
            # only needs to fetch the .metadata file, not the wheel itself.
            # They don't represent a real install step.
            if filename.endswith(".metadata"):
                return None
            size_mb = self._extract_size_mb(rest)
            state = getattr(self, "_pip_progress", None)
            if state is not None:
                state["current_pkg"] = filename
                state["total_bytes"] = int(size_mb * 1024 * 1024) if size_mb else 0
                state["last_pct"] = -1
                state["last_emit_ts"] = 0.0
            cached = prefix == "Using cached "
            tmpl_key = "pip_using_cached" if cached else "pip_downloading_size"
            template = self.lang.get("logs", {}).get(
                tmpl_key,
                "  Cached {filename}{size}" if cached else "  Downloading {filename}{size}...",
            )
            size_suffix = f" ({size_mb:.1f} MB)" if size_mb else ""
            return template.format(filename=filename, size=size_suffix)
        if line.startswith("Progress "):
            return self._format_pip_progress_line(line)
        if line.startswith("Requirement already satisfied:"):
            rest = line[len("Requirement already satisfied:"):].strip()
            pkg = rest.split()[0]
            return self.lang.get("logs", {}).get(
                "pip_already_installed",
                "  {package} is already installed",
            ).format(package=pkg)
        if line.startswith("Installing collected packages:"):
            return self.lang.get("logs", {}).get(
                "pip_installing_packages",
                "  Installing packages...",
            )
        if line.startswith("Successfully installed"):
            pkgs = line[len("Successfully installed"):].strip()
            return self.lang.get("logs", {}).get(
                "pip_installed",
                "  Installed: {packages}",
            ).format(packages=pkgs)
        if line.startswith("ERROR:") or line.startswith("error:"):
            return line  # surface real errors
        if line.startswith("WARNING:") or line.startswith("[notice]"):
            return None  # benign upgrade-pip notices etc.
        return None

    @staticmethod
    def _extract_size_mb(text: str) -> float:
        """Pull the size out of a pip ``Downloading X (245.4 MB)`` tail.

        Returns 0.0 when no size annotation is present (e.g. when pip is
        installing from a local cache and skips the size hint).
        """
        import re
        match = re.search(r"\(([0-9.]+)\s*(kB|MB|GB|B)\)", text)
        if not match:
            return 0.0
        value = float(match.group(1))
        unit = match.group(2)
        if unit == "GB":
            return value * 1024
        if unit == "kB":
            return value / 1024
        if unit == "B":
            return value / (1024 * 1024)
        return value  # MB

    def _format_pip_progress_line(self, line: str) -> Optional[str]:
        """Turn a single ``Progress N of M`` line into a throttled UI line.

        We emit at most one update per ~2 seconds AND only when the
        percentage advanced by ≥3% since the last emit, to avoid spamming
        the log with hundreds of lines for a 245 MB wheel.
        """
        import re
        import time as _time
        match = re.match(r"Progress\s+(\d+)\s+of\s+(\d+)", line)
        if not match:
            return None
        completed = int(match.group(1))
        total = int(match.group(2))
        if total <= 0:
            return None

        state = getattr(self, "_pip_progress", None)
        if state is None:
            return None

        # Pip resets ``completed`` to 0 on the next file in the same
        # install run; treat that as a new download starting.
        if completed < (state.get("last_completed") or 0):
            state["last_pct"] = -1
            state["last_emit_ts"] = 0.0
        state["last_completed"] = completed

        pct = int(completed * 100 / total)
        now = _time.time()

        # Throttle: at least 3% advance AND at least 1.5s since last emit,
        # OR a 100% completion (always show the final tick).
        if pct < 100:
            if pct - (state.get("last_pct") or -1) < 3:
                return None
            if now - (state.get("last_emit_ts") or 0.0) < 1.5:
                return None

        state["last_pct"] = pct
        state["last_emit_ts"] = now

        done_mb = completed / (1024 * 1024)
        total_mb = total / (1024 * 1024)
        template = self.lang.get("logs", {}).get(
            "pip_progress",
            "    {pct}% ({done:.1f}/{total:.1f} MB)",
        )
        return template.format(pct=pct, done=done_mb, total=total_mb)

    def _on_tr_model_changed(self, model: str) -> None:
        self._whisper_cfg()["model"] = model
        self.app.config.save()
        if model == "large-v3":
            self.log_signal.emit(
                self.lang.get("logs", {}).get(
                    "transcription_large_model_warning",
                    "  large-v3 needs more memory and may load slowly; medium/small is usually better for fast push-to-talk.",
                ),
                "#FFC107",
            )
        self._tr_unload_for_reload()

    def _on_tr_device_changed(self, device: str) -> None:
        self._whisper_cfg()["device"] = device
        self.app.config.save()
        self._tr_unload_for_reload()

    def _on_tr_compute_changed(self, compute: str) -> None:
        self._whisper_cfg()["compute_type"] = compute
        self.app.config.save()
        self._tr_unload_for_reload()

    def _tr_unload_for_reload(self) -> None:
        """Unload the model when a construction-time setting changes.

        ``model`` / ``device`` / ``compute_type`` are baked into the
        WhisperModel constructor and only take effect on the next load.

        We deliberately do NOT auto-reload — the user must explicitly
        press "Load model" again. This avoids surprise CUDA/VRAM activity
        from a misclick in the model dropdown (especially since there is
        no "cancel download" affordance for the heavy ``large-v3`` model).
        """
        if self.app.model_manager is None:
            return
        if not self.app.model_manager.is_loaded():
            # Even if not loaded, refresh install button label since the
            # selected model may not be downloaded yet.
            self.settings_tab.refresh_install_button_state()
            return

        self.log_signal.emit(
            self.lang.get("logs", {}).get(
                "transcription_settings_changed",
                "Transcription settings changed — model unloaded; "
                "press \"Load model\" to apply."
            ),
            "#FFC107",
        )
        self.app.model_manager.unload()
        self.settings_tab.refresh_install_button_state()

    def _on_tr_auto_unload_changed(self, minutes: int) -> None:
        self._tr_cfg()["auto_unload_minutes"] = int(minutes)
        self.app.config.save()
        # Apply immediately if model is loaded.
        if self.app.model_manager is not None:
            self.app.model_manager.reset_idle()

    def _on_tr_default_lang_changed(self, language: str) -> None:
        self._tr_cfg()["default_language"] = language
        self.app.config.save()

    def _on_tr_beam_changed(self, beam: int) -> None:
        self._whisper_cfg()["beam_size"] = int(beam)
        self.app.config.save()
        if int(beam) > 1:
            self.log_signal.emit(
                self.lang.get("logs", {}).get(
                    "transcription_beam_warning",
                    "  Beam size {beam} may improve quality, but increases transcription latency.",
                ).format(beam=int(beam)),
                "#FFC107",
            )

    def _on_tr_vad_toggled(self, enabled: bool) -> None:
        self._whisper_cfg()["vad_filter"] = enabled
        self.app.config.save()

    def _on_tr_engine_changed(self, engine: str) -> None:
        """User picked a different ASR engine — hot-switch."""
        engine = (engine or "whisper").lower()
        # _reinit_transcription writes config["transcription"]["engine"] = engine
        # and saves before returning. Doing this BEFORE the UI refresh is
        # essential — refresh_install_button_state() and update_transcription_state()
        # both call self._active_engine_name() which reads that key, and would
        # otherwise reflect the previous engine's state.
        self.app._reinit_transcription(engine)
        try:
            self.settings_tab.refresh_install_button_state()
            self.settings_tab.update_transcription_state("unloaded")
        except Exception:
            pass

    def _on_parakeet_provider_changed(self, provider: str) -> None:
        """Provider preference is the first item; CPU is always the tail
        fallback so onnxruntime can degrade gracefully if the GPU EP fails
        to initialise."""
        chain = [provider] if provider else ["CUDA"]
        if "CPU" not in chain:
            chain.append("CPU")
        self._parakeet_cfg()["providers"] = chain
        self.app.config.save()
        self._tr_unload_for_reload()

    def _on_parakeet_quantization_changed(self, quant: str) -> None:
        self._parakeet_cfg()["quantization"] = quant or ""
        self.app.config.save()
        self._tr_unload_for_reload()

    def _on_tr_hall_toggled(self, enabled: bool) -> None:
        self._tr_cfg()["filter_hallucinations"] = enabled
        self.app.config.save()

    def _on_tr_sounds_toggled(self, enabled: bool) -> None:
        self._tr_cfg()["feedback_sounds"] = enabled
        self.app.config.save()

    def _on_tr_input_device_changed(self, device) -> None:
        """Persist the chosen microphone (None = system default)."""
        cfg = self._tr_cfg()
        if "audio" not in cfg or not isinstance(cfg["audio"], dict):
            cfg["audio"] = {}
        cfg["audio"]["input_device"] = device
        self.app.config.save()

    # ------------------------------------------------------------------ transcription

    def _on_transcription_ui_state(self, state: str, message: str) -> None:
        """Route transcriber UI state changes to overlay + tray."""
        # Map transcriber states to overlay states.
        if state == "loading":
            self.transcription_overlay.set_state(STATE_LOADING)
            self.tray.set_loading_model()
        elif state == "recording":
            self.transcription_overlay.set_state(STATE_RECORDING)
            self.tray.set_recording()
        elif state == "transcribing":
            self.transcription_overlay.set_state(STATE_TRANSCRIBING)
            self.tray.set_transcribing("0.0")
        elif state == "done":
            self.transcription_overlay.set_state(OV_READY)
            self.tray.set_success("")
            QTimer.singleShot(2000, self.tray.set_default)
        elif state == "error":
            self.transcription_overlay.set_state(OV_ERROR)
            self.tray.set_error()
            QTimer.singleShot(3000, self.tray.set_default)
        else:  # "idle" or anything else
            self.transcription_overlay.set_state(STATE_HIDDEN)
            self.tray.set_default()

    def _on_transcription_model_state(self, state: str) -> None:
        """Forward Whisper model state changes to settings tab."""
        if hasattr(self, "settings_tab"):
            self.settings_tab.update_transcription_state(state)

    def _on_transcription_info(self, info: dict) -> None:
        """Forward Whisper runtime info (device, compute_type) to settings tab."""
        if hasattr(self, "settings_tab"):
            self.settings_tab.update_transcription_info(info)

    def _on_transcription_time(self, elapsed: str) -> None:
        """Update tray seconds counter while transcribing."""
        self.tray.set_transcribing(elapsed)
