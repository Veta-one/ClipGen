"""Main application window."""

import time
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QStackedWidget, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon
from ctypes import windll, c_bool, c_int, byref
import os

from .styles import Styles
from .tray import TrayIconManager
from .tabs import LogTab, SettingsTab, PromptsTab, HelpTab
from .dialogs import InfoMessageBox, CustomMessageBox
from .notifications import ToastNotification
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
    update_found_signal = pyqtSignal(str, str, str)  # version, url, notes
    update_not_found_signal = pyqtSignal()

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

            btn = QPushButton(name)
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

            # Connect to trigger hotkey
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
            "action": hotkey.get("name", ""),
            "prompt": hotkey.get("prompt", "")
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

        # Auto-check for updates after 3 seconds
        QTimer.singleShot(3000, self._auto_check_updates)

    def _auto_check_updates(self) -> None:
        """Automatic update check on startup (silent, no log)."""
        from ..utils.updates import UpdateChecker
        from .. import __version__

        checker = UpdateChecker(
            __version__,
            self.config.get("skipped_version", ""),
            lambda v, u, n: self.update_found_signal.emit(v, u, n),
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
            if timer_key in self.model_test_qtimers:
                self.model_test_qtimers[timer_key].stop()
                del self.model_test_qtimers[timer_key]
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
            lambda v, u, n: self.update_found_signal.emit(v, u, n),
            lambda: self.update_not_found_signal.emit(),
            is_manual=True
        )
        checker.start()

    def _on_update_found(self, version: str, url: str, notes: str) -> None:
        """Show update dialog when new version found."""
        import re
        import webbrowser
        from PyQt5.QtWidgets import QDialog

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
            clean_notes = notes.replace("### ", "").replace("**", "").replace("* ", "• ")
            for line in clean_notes.strip().split("\n"):
                if line.strip():
                    self.log_tab.append_log(f"  {line.strip()}", "#AAAAAA")

        # Build dialog content
        title = updates_lang.get("title", "ClipGen Update Available")
        header = updates_lang.get("message", "A new version is available: <b>v{new_version}</b>").format(
            new_version=version
        )

        # Format release notes
        notes_html = ""
        if notes:
            formatted_notes = notes.replace("\r\n", "<br>").replace("\n", "<br>")
            # Bold text
            while "**" in formatted_notes:
                formatted_notes = formatted_notes.replace("**", "<b>", 1).replace("**", "</b>", 1)
            # Headers
            formatted_notes = re.sub(
                r'### (.*?)(<br>|$)',
                r'<h3 style="color: #A3BFFA; margin: 10px 0 5px 0;">\1</h3>',
                formatted_notes
            )
            # Bullet points
            formatted_notes = formatted_notes.replace("* ", "&nbsp;&nbsp;• ")
            notes_html = f"<hr style='border: 1px solid #444; margin: 10px 0;'><div style='font-family: sans-serif;'>{formatted_notes}</div>"

        full_text = f"{header}{notes_html}"

        # Create dialog
        dialog = CustomMessageBox(
            self,
            title,
            full_text,
            yes_text=updates_lang.get("download_button", "Go to website"),
            no_text=updates_lang.get("skip_button", "Skip this version")
        )

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
