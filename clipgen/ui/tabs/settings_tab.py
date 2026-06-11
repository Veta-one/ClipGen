"""Settings tab - API keys, models, provider selection, etc."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QScrollArea, QRadioButton, QButtonGroup
)
from PyQt5.QtCore import Qt, pyqtSignal

from ..styles import Styles
from ..widgets import StyledComboBox, MouseOnlyPushButton


class SettingsTab(QWidget):
    """Tab for application settings."""

    # Signals
    provider_changed = pyqtSignal(int)  # 0=Gemini, 1=OpenAI
    language_changed = pyqtSignal(str)
    scale_changed = pyqtSignal(float)  # delta

    # Gemini signals
    gemini_key_added = pyqtSignal()
    gemini_key_deleted = pyqtSignal(int)
    gemini_key_activated = pyqtSignal(int)
    gemini_key_updated = pyqtSignal(int, str)
    gemini_key_name_updated = pyqtSignal(int, str)
    gemini_key_test = pyqtSignal(int)

    gemini_model_added = pyqtSignal()
    gemini_model_deleted = pyqtSignal(int)
    gemini_model_activated = pyqtSignal(int)
    gemini_model_updated = pyqtSignal(int, str)
    gemini_model_test = pyqtSignal(int)

    # OpenAI signals
    openai_base_url_changed = pyqtSignal(str)
    openai_key_added = pyqtSignal()
    openai_key_deleted = pyqtSignal(int)
    openai_key_activated = pyqtSignal(int)
    openai_key_updated = pyqtSignal(int, str)
    openai_key_name_updated = pyqtSignal(int, str)
    openai_key_test = pyqtSignal(int)

    openai_model_added = pyqtSignal()
    openai_model_deleted = pyqtSignal(int)
    openai_model_activated = pyqtSignal(int)
    openai_model_updated = pyqtSignal(int, str)
    openai_model_test = pyqtSignal(int)

    # Microphone selection signal
    transcription_input_device_changed = pyqtSignal(object)  # int or None

    # Other signals
    autostart_toggled = pyqtSignal(bool)
    auto_switch_toggled = pyqtSignal()
    visibility_toggled = pyqtSignal(bool)
    proxy_enabled_changed = pyqtSignal(bool)
    proxy_type_changed = pyqtSignal(str)
    proxy_string_changed = pyqtSignal(str)

    # Transcription signals — engine-agnostic
    transcription_enable_toggled = pyqtSignal(bool)
    transcription_engine_changed = pyqtSignal(str)
    transcription_preload_toggled = pyqtSignal(bool)
    transcription_load_clicked = pyqtSignal()
    transcription_unload_clicked = pyqtSignal()
    transcription_install_clicked = pyqtSignal()
    transcription_auto_unload_changed = pyqtSignal(int)
    transcription_default_language_changed = pyqtSignal(str)
    transcription_hallucinations_toggled = pyqtSignal(bool)
    transcription_feedback_sounds_toggled = pyqtSignal(bool)

    # Whisper-specific signals
    transcription_model_changed = pyqtSignal(str)
    transcription_device_changed = pyqtSignal(str)
    transcription_compute_changed = pyqtSignal(str)
    transcription_beam_size_changed = pyqtSignal(int)
    transcription_vad_toggled = pyqtSignal(bool)

    # Parakeet-specific signals
    parakeet_provider_changed = pyqtSignal(str)   # "CUDA" / "DirectML" / "CPU"
    parakeet_quantization_changed = pyqtSignal(str)  # "" or "int8"

    def __init__(self, config: dict, lang: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.lang = lang
        self._test_statuses = {}
        self._translatable_labels = []
        self._translatable_tooltips = []

        # Store references to time labels for live updates
        self.gemini_model_time_labels = {}
        self.openai_model_time_labels = {}
        self.gemini_key_test_buttons = {}
        self.openai_key_test_buttons = {}
        self.gemini_model_test_buttons = {}
        self.openai_model_test_buttons = {}

        # Hard guard against spurious "clicked" events fired during the very
        # first window paint. We've observed that on certain Windows + Qt
        # combinations a stray Enter keystroke from the terminal that
        # launched ClipGen propagates into the Qt event loop and activates
        # whichever button receives focus first — even with Qt.NoFocus and
        # AutoDefault=False. The transcription Load button must never run
        # without explicit user intent because it spawns a heavy CUDA load
        # that crashes the entire process if hardware/drivers mismatch.
        self._tr_buttons_armed = False

        # Refs to transcription combo/toggle rows so update_language() can
        # re-translate them when the user switches between RU/EN at runtime.
        self._tr_rows = {}

        self._setup_ui()

    def _register_label(self, label: QLabel, section: str, key: str, default: str) -> QLabel:
        """Remember a static label so runtime language switching stays complete."""
        self._translatable_labels.append((label, section, key, default))
        return label

    def _register_tooltip(self, widget: QWidget, key: str, default: str = "") -> QWidget:
        """Remember a static widget tooltip for runtime language switching."""
        self._translatable_tooltips.append((widget, key, default))
        return widget

    def _localized(self, section: str, key: str, default: str) -> str:
        return self.lang.get(section, {}).get(key, default)

    def _tooltip(self, key: str, default: str = "") -> str:
        return self.lang.get("tooltips", {}).get(key, default)

    def arm_transcription_buttons(self) -> None:
        """Allow the transcription load/unload/install buttons to fire.

        Called by the main window after the UI has been visible long enough
        that we can be confident no stray launch-time events will hit us.
        """
        self._tr_buttons_armed = True

    def _setup_ui(self) -> None:
        """Set up the tab UI."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { background-color: transparent; border: none; }
            QScrollBar:vertical { background: #1e1e1e; width: 4px; margin: 0px; border-radius: 2px; }
            QScrollBar::handle:vertical { background: #666666; min-height: 20px; border-radius: 2px; }
            QWidget#qt_scrollarea_viewport { background-color: transparent; }
        """)

        content = QWidget()
        content.setStyleSheet("background-color: #1e1e1e;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        settings_lang = self.lang.get("settings", {})

        # Provider selection
        self._add_provider_section(layout, settings_lang)

        # Gemini container
        self.gemini_container = QWidget()
        self._setup_gemini_container(settings_lang)
        layout.addWidget(self.gemini_container)

        # OpenAI container
        self.openai_container = QWidget()
        self._setup_openai_container(settings_lang)
        layout.addWidget(self.openai_container)

        # Other settings
        self._add_other_settings(layout, settings_lang)

        layout.addStretch()
        scroll.setWidget(content)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

        self._update_provider_visibility()

    def _add_provider_section(self, layout: QVBoxLayout, lang: dict) -> None:
        """Add provider selection section."""
        frame = QFrame()
        frame.setStyleSheet("background-color: #252525; border-radius: 10px; padding: 5px;")
        frame_layout = QHBoxLayout(frame)

        label = self._register_label(
            QLabel(lang.get("provider_label", "Provider:")),
            "settings",
            "provider_label",
            "Provider:",
        )
        label.setStyleSheet("border: none; font-weight: bold; font-size: 14px;")
        frame_layout.addWidget(label)
        self.provider_label = label

        self.provider_combo = StyledComboBox()
        self.provider_combo.addItem(lang.get("provider_gemini", "Google Gemini"))
        self.provider_combo.addItem(lang.get("provider_openai", "OpenAI Compatible"))
        self.provider_combo.setMinimumWidth(250)
        self.provider_combo.setCurrentIndex(0 if self.config.get("provider") == "gemini" else 1)
        self._register_tooltip(self.provider_combo, "provider_dropdown")
        self.provider_combo.setToolTip(self._tooltip("provider_dropdown"))
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        frame_layout.addWidget(self.provider_combo)

        layout.addWidget(frame)

    def _on_provider_changed(self, index: int) -> None:
        self.provider_changed.emit(index)
        self._update_provider_visibility()

    def _update_provider_visibility(self) -> None:
        is_gemini = self.provider_combo.currentIndex() == 0
        self.gemini_container.setVisible(is_gemini)
        self.openai_container.setVisible(not is_gemini)

    def _create_mini_button(self, color: str, hover_color: str, tooltip: str = "") -> QPushButton:
        """Create an 18x18 circular mini button."""
        btn = QPushButton("•")
        btn.setFixedSize(18, 18)
        btn.setToolTip(tooltip)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: #FFFFFF;
                border-radius: 9px;
                font-weight: bold;
                font-size: 10px;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
        """)
        return btn

    def _setup_gemini_container(self, lang: dict) -> None:
        """Set up Gemini settings container."""
        layout = QVBoxLayout(self.gemini_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)

        # API Keys Header
        keys_container = QFrame()
        keys_container.setStyleSheet("QFrame { background-color: transparent; border-radius: 10px; padding: 0px; }")
        keys_main_layout = QVBoxLayout(keys_container)
        keys_main_layout.setContentsMargins(0, 10, 0, 10)
        keys_main_layout.setSpacing(10)

        header = QHBoxLayout()
        label = self._register_label(
            QLabel(lang.get("api_key_label", "Gemini API Key:")),
            "settings",
            "api_key_label",
            "Gemini API Key:",
        )
        label.setStyleSheet("font-size: 16px;")
        header.addWidget(label)

        # Eye button (visibility toggle)
        self.gemini_eye_btn = self._create_mini_button(
            "#676664", "#DDDDDD", self._tooltip("toggle_keys_visibility", "Toggle key visibility")
        )
        self._register_tooltip(self.gemini_eye_btn, "toggle_keys_visibility", "Toggle key visibility")
        self.gemini_eye_btn.clicked.connect(self._toggle_visibility)
        header.addWidget(self.gemini_eye_btn)

        # Auto-switch button
        self.gemini_auto_switch_btn = self._create_mini_button(
            "#676664", "#DDDDDD", self._tooltip("auto_switch_keys", "Auto-switch on quota error")
        )
        self._register_tooltip(self.gemini_auto_switch_btn, "auto_switch_keys", "Auto-switch on quota error")
        self.gemini_auto_switch_btn.clicked.connect(lambda: self.auto_switch_toggled.emit())
        header.addWidget(self.gemini_auto_switch_btn)

        # Add key button
        add_key_btn = self._create_mini_button(
            "#3D8948", "#2A6C34", self._tooltip("add_api_key", "Add API key")
        )
        self._register_tooltip(add_key_btn, "add_api_key", "Add API key")
        add_key_btn.clicked.connect(lambda: self.gemini_key_added.emit())
        header.addWidget(add_key_btn)

        header.addStretch()
        keys_main_layout.addLayout(header)

        self.gemini_keys_layout = QVBoxLayout()
        self.gemini_keys_layout.setSpacing(5)
        self.gemini_key_radio_group = QButtonGroup(self)
        self.gemini_key_radio_group.buttonClicked[int].connect(
            lambda i: self.gemini_key_activated.emit(i))
        keys_main_layout.addLayout(self.gemini_keys_layout)

        layout.addWidget(keys_container)

        # Models section
        models_container = QFrame()
        models_container.setStyleSheet("background-color: transparent;")
        models_layout = QVBoxLayout(models_container)
        models_layout.setContentsMargins(0, 10, 0, 10)
        models_layout.setSpacing(10)

        header = QHBoxLayout()
        label = self._register_label(
            QLabel(lang.get("gemini_models_label", "Gemini Models:")),
            "settings",
            "gemini_models_label",
            "Gemini Models:",
        )
        label.setStyleSheet("font-size: 16px;")
        header.addWidget(label)

        add_model_btn = self._create_mini_button(
            "#3D8948", "#2A6C34", self._tooltip("add_model", "Add model")
        )
        self._register_tooltip(add_model_btn, "add_model", "Add model")
        add_model_btn.clicked.connect(lambda: self.gemini_model_added.emit())
        header.addWidget(add_model_btn)

        header.addStretch()
        models_layout.addLayout(header)

        self.gemini_models_layout = QVBoxLayout()
        self.gemini_models_layout.setSpacing(5)
        self.gemini_model_radio_group = QButtonGroup(self)
        self.gemini_model_radio_group.buttonClicked[int].connect(
            lambda i: self.gemini_model_activated.emit(i))
        models_layout.addLayout(self.gemini_models_layout)

        layout.addWidget(models_container)

    def _setup_openai_container(self, lang: dict) -> None:
        """Set up OpenAI settings container."""
        layout = QVBoxLayout(self.openai_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)

        # Base URL
        url_frame = QFrame()
        url_frame.setStyleSheet("background-color: #252525; border-radius: 10px; padding: 5px;")
        url_layout = QHBoxLayout(url_frame)
        self.openai_base_url_label = self._register_label(
            QLabel(lang.get("base_url_label", "Base URL:")),
            "settings",
            "base_url_label",
            "Base URL:",
        )
        url_layout.addWidget(self.openai_base_url_label)

        self.openai_base_url_input = QLineEdit(self.config.get("openai_base_url", ""))
        self.openai_base_url_input.setPlaceholderText(lang.get("base_url_placeholder", "https://openrouter.ai/api/v1"))
        self.openai_base_url_input.setStyleSheet("background-color: #2a2a2a; color: white; border: 1px solid #444; padding: 5px;")
        self._register_tooltip(self.openai_base_url_input, "base_url_input")
        self.openai_base_url_input.setToolTip(self._tooltip("base_url_input"))
        self.openai_base_url_input.textChanged.connect(lambda t: self.openai_base_url_changed.emit(t))
        url_layout.addWidget(self.openai_base_url_input)
        layout.addWidget(url_frame)

        # API Keys Header
        keys_header_layout = QHBoxLayout()
        keys_header_layout.setContentsMargins(0, 10, 0, 0)
        label = self._register_label(
            QLabel(lang.get("openai_api_keys_label", "API Keys:")),
            "settings",
            "openai_api_keys_label",
            "API Keys:",
        )
        label.setStyleSheet("font-size: 16px;")
        keys_header_layout.addWidget(label)

        # Eye button
        self.openai_eye_btn = self._create_mini_button(
            "#676664", "#DDDDDD", self._tooltip("toggle_keys_visibility", "Toggle key visibility")
        )
        self._register_tooltip(self.openai_eye_btn, "toggle_keys_visibility", "Toggle key visibility")
        self.openai_eye_btn.clicked.connect(self._toggle_visibility)
        keys_header_layout.addWidget(self.openai_eye_btn)

        # Auto-switch
        self.openai_auto_switch_btn = self._create_mini_button(
            "#676664", "#DDDDDD", self._tooltip("auto_switch_keys", "Auto-switch on quota error")
        )
        self._register_tooltip(self.openai_auto_switch_btn, "auto_switch_keys", "Auto-switch on quota error")
        self.openai_auto_switch_btn.clicked.connect(lambda: self.auto_switch_toggled.emit())
        keys_header_layout.addWidget(self.openai_auto_switch_btn)

        # Add key
        add_key_btn = self._create_mini_button(
            "#3D8948", "#2A6C34", self._tooltip("add_api_key", "Add API key")
        )
        self._register_tooltip(add_key_btn, "add_api_key", "Add API key")
        add_key_btn.clicked.connect(lambda: self.openai_key_added.emit())
        keys_header_layout.addWidget(add_key_btn)

        keys_header_layout.addStretch()
        layout.addLayout(keys_header_layout)

        self.openai_keys_layout = QVBoxLayout()
        self.openai_key_radio_group = QButtonGroup(self)
        self.openai_key_radio_group.buttonClicked[int].connect(
            lambda i: self.openai_key_activated.emit(i))
        layout.addLayout(self.openai_keys_layout)

        # Models Header
        models_header = QHBoxLayout()
        models_header.setContentsMargins(0, 10, 0, 0)
        label = self._register_label(
            QLabel(lang.get("openai_models_label", "Models List:")),
            "settings",
            "openai_models_label",
            "Models List:",
        )
        label.setStyleSheet("font-size: 16px;")
        models_header.addWidget(label)

        add_model_btn = self._create_mini_button(
            "#3D8948", "#2A6C34", self._tooltip("add_model", "Add model")
        )
        self._register_tooltip(add_model_btn, "add_model", "Add model")
        add_model_btn.clicked.connect(lambda: self.openai_model_added.emit())
        models_header.addWidget(add_model_btn)

        models_header.addStretch()
        layout.addLayout(models_header)

        self.openai_models_layout = QVBoxLayout()
        self.openai_model_radio_group = QButtonGroup(self)
        self.openai_model_radio_group.buttonClicked[int].connect(
            lambda i: self.openai_model_activated.emit(i))
        layout.addLayout(self.openai_models_layout)

    def _add_other_settings(self, layout: QVBoxLayout, lang: dict) -> None:
        """Add other settings (autostart, proxy, language, scale)."""
        # Autostart
        autostart_group = QFrame()
        autostart_group.setStyleSheet("background-color: #252525; border-radius: 10px; padding: 5px;")
        autostart_layout = QHBoxLayout(autostart_group)
        autostart_layout.setContentsMargins(10, 5, 10, 5)

        label = self._register_label(
            QLabel(lang.get("autostart_label", "Run at Windows startup")),
            "settings",
            "autostart_label",
            "Run at Windows startup",
        )
        label.setStyleSheet("border: none; font-size: 14px;")
        autostart_layout.addWidget(label)
        autostart_layout.addStretch()

        self.autostart_btn = QPushButton("•")
        self.autostart_btn.setFixedSize(18, 18)
        self.autostart_btn.setCheckable(True)
        self._register_tooltip(self.autostart_btn, "autostart_toggle")
        self.autostart_btn.setToolTip(self._tooltip("autostart_toggle"))
        self.autostart_btn.toggled.connect(self._on_autostart_toggled)
        self._update_autostart_style(False)
        autostart_layout.addWidget(self.autostart_btn)

        layout.addWidget(autostart_group)

        # Proxy
        proxy_group = QFrame()
        proxy_group.setStyleSheet("background-color: #252525; border-radius: 10px; padding: 5px;")
        proxy_layout = QVBoxLayout(proxy_group)

        top_row = QHBoxLayout()
        proxy_label = self._register_label(
            QLabel(lang.get("proxy_title", "Proxy (VPN bypass)")),
            "settings",
            "proxy_title",
            "Proxy (VPN bypass)",
        )
        proxy_label.setStyleSheet("border: none;")
        top_row.addWidget(proxy_label)
        top_row.addStretch()

        enable_label = self._register_label(
            QLabel(lang.get("proxy_enable_label", "Enable")),
            "settings",
            "proxy_enable_label",
            "Enable",
        )
        enable_label.setStyleSheet("color: #FFFFFF; border: none;")
        top_row.addWidget(enable_label)

        self.proxy_enable_btn = QPushButton("•")
        self.proxy_enable_btn.setFixedSize(18, 18)
        self.proxy_enable_btn.setCheckable(True)
        self.proxy_enable_btn.setChecked(self.config.get("proxy_enabled", False))
        self._register_tooltip(self.proxy_enable_btn, "proxy_enable_toggle")
        self.proxy_enable_btn.setToolTip(self._tooltip("proxy_enable_toggle"))
        self.proxy_enable_btn.toggled.connect(self._on_proxy_toggled)
        self._update_proxy_btn_style(self.proxy_enable_btn.isChecked())
        top_row.addWidget(self.proxy_enable_btn)

        proxy_layout.addLayout(top_row)

        input_row = QHBoxLayout()
        self.proxy_type_combo = StyledComboBox()
        self.proxy_type_combo.addItems(["HTTP", "SOCKS5"])
        idx = self.proxy_type_combo.findText(self.config.get("proxy_type", "HTTP"))
        if idx >= 0:
            self.proxy_type_combo.setCurrentIndex(idx)
        self.proxy_type_combo.setFixedWidth(100)
        self._register_tooltip(self.proxy_type_combo, "proxy_type_dropdown")
        self.proxy_type_combo.setToolTip(self._tooltip("proxy_type_dropdown"))
        self.proxy_type_combo.currentTextChanged.connect(lambda t: self.proxy_type_changed.emit(t))
        input_row.addWidget(self.proxy_type_combo)

        self.proxy_input = QLineEdit(self.config.get("proxy_string", ""))
        self.proxy_input.setPlaceholderText(
            lang.get("proxy_input_placeholder", "user:pass@ip:port")
        )
        self._register_tooltip(self.proxy_input, "proxy_input")
        self.proxy_input.setToolTip(self._tooltip("proxy_input"))
        self.proxy_input.textChanged.connect(lambda t: self.proxy_string_changed.emit(t))
        input_row.addWidget(self.proxy_input)

        proxy_layout.addLayout(input_row)

        hint = self._register_label(
            QLabel(lang.get("proxy_hint", "Format: login:password@ip:port (no http://)")),
            "settings",
            "proxy_hint",
            "Format: login:password@ip:port (no http://)",
        )
        hint.setStyleSheet("color: #666; font-size: 10px; border: none; margin-left: 2px;")
        proxy_layout.addWidget(hint)

        self._update_proxy_ui_state(self.config.get("proxy_enabled", False))
        layout.addWidget(proxy_group)

        # Voice transcription (Whisper) — placed between proxy and language.
        self._add_transcription_section(layout, lang)

        # Language & Scale
        lang_group = QFrame()
        lang_group.setStyleSheet("background-color: transparent;")
        lang_layout = QHBoxLayout(lang_group)
        lang_layout.setContentsMargins(0, 0, 0, 0)

        # Language section (left)
        self.language_label = self._register_label(
            QLabel(lang.get("language_label", "Language:")),
            "settings",
            "language_label",
            "Language:",
        )
        lang_layout.addWidget(self.language_label)

        self.language_combo = StyledComboBox()
        self.language_combo.setMinimumWidth(100)
        self._register_tooltip(self.language_combo, "language_selection")
        self.language_combo.setToolTip(self._tooltip("language_selection"))
        self.language_combo.addItems(["en", "ru"])
        current_index = self.language_combo.findText(self.config.get("language", "en"))
        if current_index >= 0:
            self.language_combo.setCurrentIndex(current_index)
        self.language_combo.currentTextChanged.connect(lambda t: self.language_changed.emit(t))
        lang_layout.addWidget(self.language_combo)

        # Stretch to push scale to the right
        lang_layout.addStretch()

        # Scale section (right)
        self.zoom_label = self._register_label(
            QLabel(lang.get("zoom_label", "Zoom:")),
            "settings",
            "zoom_label",
            "Zoom:",
        )
        lang_layout.addWidget(self.zoom_label)

        self.scale_down_btn = QPushButton("-")
        self.scale_down_btn.setFixedSize(24, 24)
        self.scale_down_btn.setStyleSheet("background-color: #444; border-radius: 4px;")
        self._register_tooltip(self.scale_down_btn, "scale_down")
        self.scale_down_btn.setToolTip(self._tooltip("scale_down"))
        self.scale_down_btn.clicked.connect(lambda: self.scale_changed.emit(-0.1))
        lang_layout.addWidget(self.scale_down_btn)

        current_scale = int(self.config.get("ui_scale", 1.0) * 100)
        self.scale_label = QLabel(f"{current_scale}%")
        self.scale_label.setFixedWidth(40)
        self.scale_label.setAlignment(Qt.AlignCenter)
        lang_layout.addWidget(self.scale_label)

        self.scale_up_btn = QPushButton("+")
        self.scale_up_btn.setFixedSize(24, 24)
        self.scale_up_btn.setStyleSheet("background-color: #444; border-radius: 4px;")
        self._register_tooltip(self.scale_up_btn, "scale_up")
        self.scale_up_btn.setToolTip(self._tooltip("scale_up"))
        self.scale_up_btn.clicked.connect(lambda: self.scale_changed.emit(0.1))
        lang_layout.addWidget(self.scale_up_btn)

        layout.addWidget(lang_group)

    def _toggle_visibility(self) -> None:
        """Toggle API key visibility."""
        visible = not self.config.get("api_keys_visible", False)
        self.visibility_toggled.emit(visible)

    def _on_autostart_toggled(self, checked: bool) -> None:
        self._update_autostart_style(checked)
        self.autostart_toggled.emit(checked)

    def _on_proxy_toggled(self, checked: bool) -> None:
        self._update_proxy_btn_style(checked)
        self._update_proxy_ui_state(checked)
        self.proxy_enabled_changed.emit(checked)

    def _update_autostart_style(self, checked: bool) -> None:
        if checked:
            self.autostart_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3D8948;
                    color: white;
                    border-radius: 9px;
                    font-weight: bold;
                    font-size: 5px;
                    margin: 0px;
                    border: none;
                }
                QPushButton:hover { background-color: #2A6C34; }
            """)
        else:
            self.autostart_btn.setStyleSheet("""
                QPushButton {
                    background-color: #676664;
                    color: #FFFFFF;
                    border-radius: 9px;
                    font-weight: bold;
                    font-size: 5px;
                    margin: 0px;
                    border: none;
                }
                QPushButton:hover { background-color: #DDDDDD; color: #000000; }
            """)

    def _update_proxy_btn_style(self, checked: bool) -> None:
        if checked:
            self.proxy_enable_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3D8948;
                    color: white;
                    border-radius: 9px;
                    font-weight: bold;
                    font-size: 5px;
                    margin: 0px;
                    border: none;
                }
                QPushButton:hover { background-color: #2A6C34; }
            """)
        else:
            self.proxy_enable_btn.setStyleSheet("""
                QPushButton {
                    background-color: #676664;
                    color: #FFFFFF;
                    border-radius: 9px;
                    font-weight: bold;
                    font-size: 5px;
                    margin: 0px;
                    border: none;
                }
                QPushButton:hover { background-color: #DDDDDD; color: #000000; }
            """)

    def _update_proxy_ui_state(self, enabled: bool) -> None:
        self.proxy_type_combo.setEnabled(enabled)
        self.proxy_input.setEnabled(enabled)

    def _update_auto_switch_style(self) -> None:
        """Update auto-switch buttons style."""
        active = self.config.get("auto_switch_api_keys", False)
        color = "#5085D0" if active else "#676664"
        style = f"""
            QPushButton {{
                background-color: {color};
                color: #FFFFFF;
                border-radius: 9px;
                font-weight: bold;
                font-size: 10px;
            }}
            QPushButton:hover {{ background-color: #DDDDDD; color: #000000; }}
        """
        if hasattr(self, 'gemini_auto_switch_btn'):
            self.gemini_auto_switch_btn.setStyleSheet(style)
        if hasattr(self, 'openai_auto_switch_btn'):
            self.openai_auto_switch_btn.setStyleSheet(style)

    def set_autostart_checked(self, checked: bool) -> None:
        self.autostart_btn.setChecked(checked)
        self._update_autostart_style(checked)

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def refresh_gemini_keys(self) -> None:
        """Refresh Gemini API keys list."""
        self._clear_layout(self.gemini_keys_layout)

        for btn in self.gemini_key_radio_group.buttons():
            self.gemini_key_radio_group.removeButton(btn)

        # Clear button references
        self.gemini_key_test_buttons.clear()

        visible = self.config.get("api_keys_visible", False)
        keys = self.config.get("api_keys", [])

        for i, key_data in enumerate(keys):
            row = self._create_key_row(i, key_data, visible, "gemini")
            self.gemini_keys_layout.addWidget(row)

    def refresh_openai_keys(self) -> None:
        """Refresh OpenAI API keys list."""
        self._clear_layout(self.openai_keys_layout)

        for btn in self.openai_key_radio_group.buttons():
            self.openai_key_radio_group.removeButton(btn)

        # Clear button references
        self.openai_key_test_buttons.clear()

        visible = self.config.get("api_keys_visible", False)
        keys = self.config.get("openai_api_keys", [])

        for i, key_data in enumerate(keys):
            row = self._create_key_row(i, key_data, visible, "openai")
            self.openai_keys_layout.addWidget(row)

    def _create_key_row(self, index: int, key_data: dict, visible: bool, provider: str) -> QWidget:
        """Create a key row widget."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Radio button
        radio = QRadioButton()
        radio.setChecked(key_data.get("active", False))
        radio.setFixedSize(18, 18)
        radio.setStyleSheet("""
            QRadioButton { spacing: 0; }
            QRadioButton::indicator { width: 18px; height: 18px; border-radius: 9px; }
            QRadioButton::indicator:unchecked { background-color: #353535; }
            QRadioButton::indicator:unchecked:hover { background-color: #4f4f4f; }
            QRadioButton::indicator:checked {
                background-color: qradialgradient(
                    cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                    stop:0 #FFFFFF, stop:0.1 #FFFFFF, stop:0.21 #5085D0, stop:1 #5085D0
                );
            }
        """)

        if provider == "gemini":
            self.gemini_key_radio_group.addButton(radio, index)
        else:
            self.openai_key_radio_group.addButton(radio, index)

        layout.addWidget(radio)

        # Key input
        key_input = QLineEdit(key_data.get("key", ""))
        key_input.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
        key_input.setStyleSheet("border-radius: 8px; border: 1px solid #444444; padding: 5px; background-color: #2a2a2a; color: #FFFFFF;")
        key_input.textChanged.connect(
            lambda t, i=index: (self.gemini_key_updated if provider == "gemini" else self.openai_key_updated).emit(i, t))
        layout.addWidget(key_input, 1)

        # Name input
        name_input = QLineEdit(key_data.get("name", ""))
        name_input.setPlaceholderText(
            self.lang.get("settings", {}).get("key_name_placeholder", "Name...")
        )
        name_input.setFixedWidth(80)
        name_input.setStyleSheet("border-radius: 8px; border: 1px solid #444444; padding: 5px; background-color: #2a2a2a; color: #FFFFFF;")
        name_input.textChanged.connect(
            lambda t, i=index: (
                self.gemini_key_name_updated if provider == "gemini" else self.openai_key_name_updated
            ).emit(i, t)
        )
        layout.addWidget(name_input)

        # Test button
        status = key_data.get("test_status", "not_tested")
        test_btn = self._create_test_button(status)
        test_btn.clicked.connect(
            lambda _, i=index: (self.gemini_key_test if provider == "gemini" else self.openai_key_test).emit(i))
        layout.addWidget(test_btn)

        # Store reference to test button for status updates
        if provider == "gemini":
            self.gemini_key_test_buttons[index] = test_btn
        else:
            self.openai_key_test_buttons[index] = test_btn

        # Delete button
        del_btn = self._create_mini_button("#FF5F57", "#FF3B30",
            self.lang.get("tooltips", {}).get("delete_api_key", "Delete key"))
        del_btn.clicked.connect(
            lambda _, i=index: (self.gemini_key_deleted if provider == "gemini" else self.openai_key_deleted).emit(i))
        layout.addWidget(del_btn)

        return row

    def refresh_gemini_models(self) -> None:
        """Refresh Gemini models list."""
        self._clear_layout(self.gemini_models_layout)

        for btn in self.gemini_model_radio_group.buttons():
            self.gemini_model_radio_group.removeButton(btn)

        # Clear label and button references
        self.gemini_model_time_labels.clear()
        self.gemini_model_test_buttons.clear()

        models = self.config.get("gemini_models", [])
        active_model = self.config.get("active_model", "")

        for i, model_data in enumerate(models):
            row = self._create_model_row(i, model_data, active_model, "gemini")
            self.gemini_models_layout.addWidget(row)

    def refresh_openai_models(self) -> None:
        """Refresh OpenAI models list."""
        self._clear_layout(self.openai_models_layout)

        for btn in self.openai_model_radio_group.buttons():
            self.openai_model_radio_group.removeButton(btn)

        # Clear label and button references
        self.openai_model_time_labels.clear()
        self.openai_model_test_buttons.clear()

        models = self.config.get("openai_models", [])
        active_model = self.config.get("openai_active_model", "")

        for i, model_data in enumerate(models):
            row = self._create_model_row(i, model_data, active_model, "openai")
            self.openai_models_layout.addWidget(row)

    def _create_model_row(self, index: int, model_data: dict, active_model: str, provider: str) -> QWidget:
        """Create a model row widget."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        model_name = model_data.get("name", "")

        # Radio button
        radio = QRadioButton()
        radio.setChecked(model_name == active_model)
        radio.setFixedSize(18, 18)
        radio.setStyleSheet("""
            QRadioButton::indicator { width: 18px; height: 18px; border-radius: 9px; }
            QRadioButton::indicator:unchecked { background-color: #353535; }
            QRadioButton::indicator:unchecked:hover { background-color: #4f4f4f; }
            QRadioButton::indicator:checked {
                background-color: qradialgradient(
                    cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                    stop:0 #FFFFFF, stop:0.1 #FFFFFF, stop:0.21 #5085D0, stop:1 #5085D0
                );
            }
        """)

        if provider == "gemini":
            self.gemini_model_radio_group.addButton(radio, index)
        else:
            self.openai_model_radio_group.addButton(radio, index)

        layout.addWidget(radio)

        # Name input
        name_input = QLineEdit(model_name)
        name_input.setStyleSheet("border-radius: 8px; border: 1px solid #444444; padding: 5px; background-color: #2a2a2a; color: #FFFFFF;")
        name_input.textChanged.connect(
            lambda t, i=index: (self.gemini_model_updated if provider == "gemini" else self.openai_model_updated).emit(i, t))
        layout.addWidget(name_input, 1)

        # Test time label
        test_time = model_data.get("test_duration", 0.0)
        status = model_data.get("test_status", "not_tested")
        time_text = f"{test_time:.1f}s" if test_time > 0 else "0.0s"
        if status == "error":
            time_text = "err"

        time_label = QLabel(time_text)
        time_label.setStyleSheet("color: #888888; font-size: 12px;")
        time_label.setFixedWidth(50)
        time_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(time_label)

        # Store reference to time label for live updates
        if provider == "gemini":
            self.gemini_model_time_labels[index] = time_label
        else:
            self.openai_model_time_labels[index] = time_label

        # Test button
        test_btn = self._create_test_button(status)
        test_btn.setToolTip(self.lang.get("tooltips", {}).get("test_model", "Test model"))
        test_btn.clicked.connect(
            lambda _, i=index: (self.gemini_model_test if provider == "gemini" else self.openai_model_test).emit(i))
        layout.addWidget(test_btn)

        # Store reference to test button for status updates
        if provider == "gemini":
            self.gemini_model_test_buttons[index] = test_btn
        else:
            self.openai_model_test_buttons[index] = test_btn

        # Delete button
        del_btn = self._create_mini_button("#FF5F57", "#FF3B30",
            self.lang.get("tooltips", {}).get("delete_model", "Delete model"))
        del_btn.clicked.connect(
            lambda _, i=index: (self.gemini_model_deleted if provider == "gemini" else self.openai_model_deleted).emit(i))
        layout.addWidget(del_btn)

        return row

    def _create_test_button(self, status: str) -> QPushButton:
        """Create a test status button."""
        btn = QPushButton("•")
        btn.setFixedSize(18, 18)

        colors = {
            "success": ("#28A745", "#218838"),
            "error": ("#DC3545", "#C82333"),
            "testing": ("#FFC107", "#E0A800"),
            "not_tested": ("#6c757d", "#5a6268")
        }
        color, hover = colors.get(status, ("#6c757d", "#5a6268"))

        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border-radius: 9px;
            }}
            QPushButton:hover {{ background-color: {hover}; }}
        """)
        return btn

    def refresh_all(self) -> None:
        """Refresh all lists."""
        self.refresh_gemini_keys()
        self.refresh_gemini_models()
        self.refresh_openai_keys()
        self.refresh_openai_models()
        self._update_auto_switch_style()

    def set_test_status(self, provider: str, item_type: str, index: int, status: str) -> None:
        """Set test status for a key or model."""
        key = f"{provider}_{item_type}_{index}"
        self._test_statuses[key] = status

    def update_model_time_label(self, provider: str, index: int, text: str) -> None:
        """Update the time label for a model (for live timer).

        Args:
            provider: "gemini" or "openai"
            index: Model index
            text: Text to display (e.g., "0.3s")
        """
        labels = self.gemini_model_time_labels if provider == "gemini" else self.openai_model_time_labels
        if index in labels:
            labels[index].setText(text)

    def update_test_button_status(self, provider: str, item_type: str, index: int, status: str) -> None:
        """Update the test button style for a key or model.

        Args:
            provider: "gemini" or "openai"
            item_type: "key" or "model"
            index: Item index
            status: "not_tested", "testing", "success", "error"
        """
        if item_type == "key":
            buttons = self.gemini_key_test_buttons if provider == "gemini" else self.openai_key_test_buttons
        else:
            buttons = self.gemini_model_test_buttons if provider == "gemini" else self.openai_model_test_buttons

        if index in buttons:
            btn = buttons[index]
            colors = {
                "success": ("#28A745", "#218838"),
                "error": ("#DC3545", "#C82333"),
                "testing": ("#FFC107", "#E0A800"),
                "not_tested": ("#6c757d", "#5a6268")
            }
            color, hover = colors.get(status, ("#6c757d", "#5a6268"))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    color: white;
                    border-radius: 9px;
                }}
                QPushButton:hover {{ background-color: {hover}; }}
            """)

    def update_language(self, lang: dict) -> None:
        """Update UI text with new language.

        Static widgets are registered when the tab is built; dynamic rows are
        rebuilt from config so their placeholders/tooltips use the new locale.
        """
        self.lang = lang
        settings_lang = lang.get("settings", {})
        tooltips = lang.get("tooltips", {})

        for label, section, key, default in self._translatable_labels:
            label.setText(lang.get(section, {}).get(key, default))

        for widget, key, default in self._translatable_tooltips:
            widget.setToolTip(tooltips.get(key, default))

        # Update provider combo items
        current_provider_idx = self.provider_combo.currentIndex()
        self.provider_combo.blockSignals(True)
        self.provider_combo.clear()
        self.provider_combo.addItem(settings_lang.get("provider_gemini", "Google Gemini"))
        self.provider_combo.addItem(settings_lang.get("provider_openai", "OpenAI Compatible"))
        self.provider_combo.setCurrentIndex(current_provider_idx)
        self.provider_combo.blockSignals(False)

        self.openai_base_url_input.setPlaceholderText(
            settings_lang.get("base_url_placeholder", "e.g. https://openrouter.ai/api/v1")
        )
        self.proxy_input.setPlaceholderText(
            settings_lang.get("proxy_input_placeholder", "user:pass@ip:port")
        )

        # Rebuild dynamic rows so placeholders and test/delete tooltips use
        # the selected language. User values are already stored in config.
        self.refresh_gemini_keys()
        self.refresh_openai_keys()
        self.refresh_gemini_models()
        self.refresh_openai_models()

        # Update transcription section text (header, buttons, hints, rows).
        self._update_transcription_language(lang)

    def _update_transcription_language(self, lang: dict) -> None:
        """Re-translate the transcription card after a language switch."""
        if not hasattr(self, "tr_title_label"):
            return  # section was never built

        tr_lang = lang.get("transcription", {})
        tooltips = lang.get("tooltips", {})

        self.tr_title_label.setText(tr_lang.get("section_title", "Voice transcription"))
        self.tr_enable_label.setText(tr_lang.get("enable_master", "Enable"))
        self.tr_enable_btn.setToolTip(tooltips.get("transcription_enable_master", ""))
        self.tr_hint_label.setText(tr_lang.get("enable_hint", ""))

        self.tr_status_caption.setText(tr_lang.get("model_status", "Model status:"))

        # Install button text is recomputed from install/download state by
        # refresh_install_button_state(); just refresh the tooltip here.
        self.tr_install_btn.setToolTip(tooltips.get("transcription_install", ""))
        # Load button text depends on whether the model is downloaded; this
        # is recomputed by update_transcription_state(). Just set tooltip.
        self.tr_load_btn.setToolTip(tooltips.get("transcription_load_model", ""))
        self.tr_unload_btn.setText(tr_lang.get("btn_unload", "Unload model"))
        self.tr_unload_btn.setToolTip(tooltips.get("transcription_unload_model", ""))

        self.tr_preload_label.setText(
            tr_lang.get("preload_on_start", "Load model on app start")
        )
        self.tr_preload_btn.setToolTip(tooltips.get("transcription_preload_on_start", ""))

        # Combo / toggle rows registered in _tr_rows.
        label_keys = {
            "model": "model_label",
            "device": "device_label",
            "compute": "compute_type_label",
            "unload": "auto_unload_label",
            "language": "default_language_label",
            "beam": "beam_size_label",
            "vad": "vad_filter",
            "hall": "hallucination_filter",
            "sounds": "feedback_sounds",
            "engine": "engine_label",
            "pk_provider": "parakeet_provider_label",
            "pk_quant": "parakeet_quant_label",
        }
        for key, lang_key in label_keys.items():
            row = self._tr_rows.get(key)
            if not row:
                continue
            row["label"].setText(tr_lang.get(row.get("label_key", lang_key), lang_key))

        if hasattr(self, "tr_mic_label"):
            self.tr_mic_label.setText(tr_lang.get("input_device_label", "Microphone:"))
        if hasattr(self, "tr_mic_combo"):
            current_data = self.tr_mic_combo.currentData()
            self.tr_mic_combo.blockSignals(True)
            if self.tr_mic_combo.count() > 0:
                self.tr_mic_combo.setItemText(
                    0,
                    tr_lang.get("input_device_auto", "Auto (system default)"),
                )
            for i in range(self.tr_mic_combo.count()):
                if self.tr_mic_combo.itemData(i) == current_data:
                    self.tr_mic_combo.setCurrentIndex(i)
                    break
            self.tr_mic_combo.blockSignals(False)

        # Re-translate combo item display strings while preserving selection.
        for key in ("model", "device", "compute", "unload", "language", "beam",
                    "engine", "pk_provider", "pk_quant"):
            row = self._tr_rows.get(key)
            if not row or "combo" not in row:
                continue
            combo = row["combo"]
            options = row.get("options", [])
            current_data = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for value, opt_lang_key in options:
                combo.addItem(tr_lang.get(opt_lang_key, str(value)), value)
            for i in range(combo.count()):
                if combo.itemData(i) == current_data:
                    combo.setCurrentIndex(i)
                    break
            combo.blockSignals(False)

        if hasattr(self, "tr_download_hint"):
            self.tr_download_hint.setText(
                tr_lang.get(
                    "info_model_download_hint",
                    "First load will download the selected model from HuggingFace."
                )
            )

        # Re-translate the status value using the last known state.
        last_state = getattr(self, "_tr_last_state", "unloaded")
        self.update_transcription_state(last_state)

    # ====================================================================
    # Voice transcription section
    # ====================================================================

    TRANSCRIPTION_LANGUAGES = [
        ("auto", "language_auto"),
        ("ru", "language_ru"),
        ("en", "language_en"),
        ("de", "language_de"),
        ("es", "language_es"),
        ("fr", "language_fr"),
        ("it", "language_it"),
        ("pt", "language_pt"),
        ("pl", "language_pl"),
        ("uk", "language_uk"),
    ]

    TRANSCRIPTION_MODELS = [
        ("large-v3", "model_large_v3"),
        ("large-v3-turbo", "model_large_v3_turbo"),
        ("medium", "model_medium"),
        ("small", "model_small"),
        ("base", "model_base"),
        ("tiny", "model_tiny"),
    ]

    TRANSCRIPTION_DEVICES = [
        ("auto", "device_auto"),
        ("cuda", "device_cuda"),
        ("cpu", "device_cpu"),
    ]

    TRANSCRIPTION_COMPUTE_TYPES = [
        ("float16", "float16"),
        ("int8_float16", "int8_float16"),
        ("float32", "float32"),
        ("int8", "int8"),
    ]

    TRANSCRIPTION_AUTO_UNLOAD = [
        (0, "auto_unload_never"),
        (5, "auto_unload_5min"),
        (10, "auto_unload_10min"),
        (30, "auto_unload_30min"),
    ]

    TRANSCRIPTION_BEAM_SIZES = [
        (1, "beam_size_1"),
        (5, "beam_size_5"),
    ]

    # ASR engine selector — first option is default. Each entry is
    # (config_value, lang_key). Lang keys live under transcription.*.
    TRANSCRIPTION_ENGINES = [
        ("whisper", "engine_whisper"),
        ("parakeet", "engine_parakeet"),
    ]

    # Parakeet ONNX execution providers, in fallback chain order.
    PARAKEET_PROVIDERS = [
        ("CUDA", "parakeet_provider_cuda"),
        ("DirectML", "parakeet_provider_directml"),
        ("CPU", "parakeet_provider_cpu"),
    ]

    # Parakeet weight quantization variants.
    PARAKEET_QUANTIZATIONS = [
        ("", "parakeet_quant_none"),
        ("int8", "parakeet_quant_int8"),
    ]

    def _add_transcription_section(self, layout: QVBoxLayout, lang: dict) -> None:
        """Build the Whisper voice transcription settings card."""
        tr_lang = self.lang.get("transcription", {})
        tooltips = self.lang.get("tooltips", {})
        tr_cfg = self.config.get("transcription", {}) or {}

        group = QFrame()
        group.setStyleSheet("background-color: #252525; border-radius: 10px; padding: 5px;")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(10, 10, 10, 10)
        group_layout.setSpacing(8)

        # Header: title + master toggle
        header_row = QHBoxLayout()
        self.tr_title_label = QLabel(tr_lang.get("section_title", "Voice transcription"))
        self.tr_title_label.setStyleSheet("border: none; font-size: 14px; font-weight: bold;")
        header_row.addWidget(self.tr_title_label)
        header_row.addStretch()

        self.tr_enable_label = QLabel(tr_lang.get("enable_master", "Enable"))
        self.tr_enable_label.setStyleSheet("border: none;")
        header_row.addWidget(self.tr_enable_label)

        self.tr_enable_btn = QPushButton("•")
        self.tr_enable_btn.setFixedSize(18, 18)
        self.tr_enable_btn.setCheckable(True)
        self.tr_enable_btn.setChecked(bool(tr_cfg.get("enabled", False)))
        self.tr_enable_btn.setToolTip(tooltips.get("transcription_enable_master", ""))
        self.tr_enable_btn.setAutoDefault(False)
        self.tr_enable_btn.setDefault(False)
        self.tr_enable_btn.setFocusPolicy(Qt.ClickFocus)
        self._update_toggle_style(self.tr_enable_btn, self.tr_enable_btn.isChecked())
        self.tr_enable_btn.toggled.connect(self._on_tr_enable_toggled)
        header_row.addWidget(self.tr_enable_btn)
        group_layout.addLayout(header_row)

        # Hint text
        self.tr_hint_label = QLabel(tr_lang.get("enable_hint", ""))
        self.tr_hint_label.setStyleSheet("color: #888; font-size: 10px; border: none;")
        self.tr_hint_label.setWordWrap(True)
        group_layout.addWidget(self.tr_hint_label)

        # Container that hides when feature is disabled
        self.tr_body = QWidget()
        self.tr_body.setStyleSheet("background-color: transparent;")
        body_layout = QVBoxLayout(self.tr_body)
        body_layout.setContentsMargins(0, 5, 0, 0)
        body_layout.setSpacing(8)

        # Status row
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.tr_status_caption = QLabel(tr_lang.get("model_status", "Model status:"))
        self.tr_status_caption.setStyleSheet("border: none;")
        status_row.addWidget(self.tr_status_caption)

        self.tr_status_value = QLabel(tr_lang.get("state_unloaded", "Unloaded"))
        self.tr_status_value.setStyleSheet(
            "border: none; color: #888888; font-weight: bold;"
        )
        status_row.addWidget(self.tr_status_value)
        status_row.addStretch()
        body_layout.addLayout(status_row)

        # Buttons row: install / load / unload
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(8)

        self.tr_install_btn = MouseOnlyPushButton(tr_lang.get("btn_install", "Install / Download"))
        self.tr_install_btn.setStyleSheet(self._tr_action_button_style())
        self.tr_install_btn.setToolTip(tooltips.get("transcription_install", ""))
        self.tr_install_btn.setAutoDefault(False)
        self.tr_install_btn.setDefault(False)
        self.tr_install_btn.setFocusPolicy(Qt.NoFocus)
        self.tr_install_btn.clicked.connect(self._on_tr_install_btn_clicked)
        buttons_row.addWidget(self.tr_install_btn)

        self.tr_load_btn = MouseOnlyPushButton(tr_lang.get("btn_load", "Load model"))
        self.tr_load_btn.setStyleSheet(self._tr_action_button_style(accent="#3D8948"))
        self.tr_load_btn.setToolTip(tooltips.get("transcription_load_model", ""))
        self.tr_load_btn.setAutoDefault(False)
        self.tr_load_btn.setDefault(False)
        self.tr_load_btn.setFocusPolicy(Qt.NoFocus)
        self.tr_load_btn.clicked.connect(self._on_tr_load_btn_clicked)
        buttons_row.addWidget(self.tr_load_btn)

        self.tr_unload_btn = MouseOnlyPushButton(tr_lang.get("btn_unload", "Unload model"))
        self.tr_unload_btn.setStyleSheet(self._tr_action_button_style(accent="#FF5F57"))
        self.tr_unload_btn.setToolTip(tooltips.get("transcription_unload_model", ""))
        self.tr_unload_btn.setAutoDefault(False)
        self.tr_unload_btn.setDefault(False)
        self.tr_unload_btn.setFocusPolicy(Qt.NoFocus)
        self.tr_unload_btn.clicked.connect(self._on_tr_unload_btn_clicked)
        buttons_row.addWidget(self.tr_unload_btn)

        body_layout.addLayout(buttons_row)

        # Preload checkbox row
        preload_row = QHBoxLayout()
        self.tr_preload_label = QLabel(tr_lang.get("preload_on_start", "Load model on app start"))
        self.tr_preload_label.setStyleSheet("border: none;")
        preload_row.addWidget(self.tr_preload_label)
        preload_row.addStretch()

        self.tr_preload_btn = QPushButton("•")
        self.tr_preload_btn.setFixedSize(18, 18)
        self.tr_preload_btn.setCheckable(True)
        self.tr_preload_btn.setChecked(bool(tr_cfg.get("preload_on_start", False)))
        self.tr_preload_btn.setToolTip(tooltips.get("transcription_preload_on_start", ""))
        self.tr_preload_btn.setAutoDefault(False)
        self.tr_preload_btn.setDefault(False)
        self.tr_preload_btn.setFocusPolicy(Qt.ClickFocus)
        self._update_toggle_style(self.tr_preload_btn, self.tr_preload_btn.isChecked())
        self.tr_preload_btn.toggled.connect(self._on_tr_preload_toggled)
        preload_row.addWidget(self.tr_preload_btn)
        body_layout.addLayout(preload_row)

        # ASR engine selector (shared) — drives which sub-container shows.
        whisper_cfg = tr_cfg.get("whisper", {}) or {}
        parakeet_cfg = tr_cfg.get("parakeet", {}) or {}
        current_engine = (tr_cfg.get("engine") or "whisper").lower()

        self.tr_engine_combo = self._add_tr_combo_row(
            body_layout,
            label_text=tr_lang.get("engine_label", "Engine:"),
            options=self.TRANSCRIPTION_ENGINES,
            current_value=current_engine,
            tooltip=tooltips.get("transcription_engine", ""),
            on_change=self._on_engine_combo_changed,
            row_key=("engine", "engine_label"),
        )

        # Whisper-specific settings container.
        self.tr_whisper_container = QWidget()
        self.tr_whisper_container.setStyleSheet("background-color: transparent;")
        whisper_layout = QVBoxLayout(self.tr_whisper_container)
        whisper_layout.setContentsMargins(0, 0, 0, 0)
        whisper_layout.setSpacing(8)
        body_layout.addWidget(self.tr_whisper_container)

        self.tr_model_combo = self._add_tr_combo_row(
            whisper_layout,
            label_text=tr_lang.get("model_label", "Model:"),
            options=self.TRANSCRIPTION_MODELS,
            current_value=whisper_cfg.get("model", "large-v3"),
            tooltip=tooltips.get("transcription_model_select", ""),
            on_change=lambda v: self.transcription_model_changed.emit(v),
            row_key=("model", "model_label"),
        )
        self.tr_device_combo = self._add_tr_combo_row(
            whisper_layout,
            label_text=tr_lang.get("device_label", "Device:"),
            options=self.TRANSCRIPTION_DEVICES,
            current_value=whisper_cfg.get("device", "auto"),
            tooltip=tooltips.get("transcription_device_select", ""),
            on_change=lambda v: self.transcription_device_changed.emit(v),
            row_key=("device", "device_label"),
        )
        self.tr_compute_combo = self._add_tr_combo_row(
            whisper_layout,
            label_text=tr_lang.get("compute_type_label", "Compute type:"),
            options=self.TRANSCRIPTION_COMPUTE_TYPES,
            current_value=whisper_cfg.get("compute_type", "float16"),
            tooltip="",
            on_change=lambda v: self.transcription_compute_changed.emit(v),
            row_key=("compute", "compute_type_label"),
        )
        self.tr_beam_combo = self._add_tr_combo_row(
            whisper_layout,
            label_text=tr_lang.get("beam_size_label", "Beam size:"),
            options=self.TRANSCRIPTION_BEAM_SIZES,
            current_value=int(whisper_cfg.get("beam_size", 1) or 1),
            tooltip=tooltips.get("transcription_beam_size", ""),
            on_change=lambda v: self.transcription_beam_size_changed.emit(int(v)),
            row_key=("beam", "beam_size_label"),
        )
        self.tr_vad_btn = self._add_tr_toggle_row(
            whisper_layout,
            label_text=tr_lang.get("vad_filter", "VAD filter"),
            current_value=bool(whisper_cfg.get("vad_filter", True)),
            tooltip=tooltips.get("transcription_vad", ""),
            on_change=lambda v: self.transcription_vad_toggled.emit(bool(v)),
            row_key=("vad", "vad_filter"),
        )

        # Parakeet-specific settings container.
        self.tr_parakeet_container = QWidget()
        self.tr_parakeet_container.setStyleSheet("background-color: transparent;")
        parakeet_layout = QVBoxLayout(self.tr_parakeet_container)
        parakeet_layout.setContentsMargins(0, 0, 0, 0)
        parakeet_layout.setSpacing(8)
        body_layout.addWidget(self.tr_parakeet_container)

        # Provider preference. Stored as the FIRST item of the providers list;
        # CPU fallback is always appended in ParakeetModelManager.
        providers_list = parakeet_cfg.get("providers") or ["CUDA", "CPU"]
        if isinstance(providers_list, str):
            providers_list = [providers_list]
        primary_provider = providers_list[0] if providers_list else "CUDA"
        self.tr_parakeet_provider_combo = self._add_tr_combo_row(
            parakeet_layout,
            label_text=tr_lang.get("parakeet_provider_label", "Provider:"),
            options=self.PARAKEET_PROVIDERS,
            current_value=primary_provider,
            tooltip=tooltips.get("parakeet_provider", ""),
            on_change=lambda v: self.parakeet_provider_changed.emit(v),
            row_key=("pk_provider", "parakeet_provider_label"),
        )
        self.tr_parakeet_quant_combo = self._add_tr_combo_row(
            parakeet_layout,
            label_text=tr_lang.get("parakeet_quant_label", "Quantization:"),
            options=self.PARAKEET_QUANTIZATIONS,
            current_value=parakeet_cfg.get("quantization", "") or "",
            tooltip=tooltips.get("parakeet_quantization", ""),
            on_change=lambda v: self.parakeet_quantization_changed.emit(v),
            row_key=("pk_quant", "parakeet_quant_label"),
        )

        # Apply initial visibility — only the active engine's container shows.
        self._update_engine_container_visibility(current_engine)

        # Shared settings below the engine-specific block.
        self.tr_unload_combo = self._add_tr_combo_row(
            body_layout,
            label_text=tr_lang.get("auto_unload_label", "Auto-unload after:"),
            options=self.TRANSCRIPTION_AUTO_UNLOAD,
            current_value=int(tr_cfg.get("auto_unload_minutes", 5) or 0),
            tooltip=tooltips.get("transcription_auto_unload", ""),
            on_change=lambda v: self.transcription_auto_unload_changed.emit(int(v)),
            row_key=("unload", "auto_unload_label"),
        )
        self.tr_language_combo = self._add_tr_combo_row(
            body_layout,
            label_text=tr_lang.get("default_language_label", "Default language:"),
            options=self.TRANSCRIPTION_LANGUAGES,
            current_value=tr_cfg.get("default_language", "auto"),
            tooltip=tooltips.get("transcription_language_select", ""),
            on_change=lambda v: self.transcription_default_language_changed.emit(v),
            row_key=("language", "default_language_label"),
        )

        # Microphone (input device) select
        self._build_mic_row(body_layout, tr_cfg)

        # Shared toggles: hallucination filter and feedback sounds.
        self.tr_hall_btn = self._add_tr_toggle_row(
            body_layout,
            label_text=tr_lang.get("hallucination_filter", "Hallucination filter"),
            current_value=bool(tr_cfg.get("filter_hallucinations", True)),
            tooltip=tooltips.get("transcription_hallucinations", ""),
            on_change=lambda v: self.transcription_hallucinations_toggled.emit(bool(v)),
            row_key=("hall", "hallucination_filter"),
        )
        self.tr_sounds_btn = self._add_tr_toggle_row(
            body_layout,
            label_text=tr_lang.get("feedback_sounds", "Sound signals"),
            current_value=bool(tr_cfg.get("feedback_sounds", True)),
            tooltip=tooltips.get("transcription_feedback_sounds", ""),
            on_change=lambda v: self.transcription_feedback_sounds_toggled.emit(bool(v)),
            row_key=("sounds", "feedback_sounds"),
        )

        # Info hint about model download
        self.tr_download_hint = QLabel(
            tr_lang.get("info_model_download_hint",
                        "First load will download the selected model from HuggingFace.")
        )
        self.tr_download_hint.setStyleSheet("color: #666; font-size: 10px; border: none;")
        self.tr_download_hint.setWordWrap(True)
        body_layout.addWidget(self.tr_download_hint)

        group_layout.addWidget(self.tr_body)
        layout.addWidget(group)

        # Apply initial enabled state visibility
        self._update_transcription_body_visibility()
        # Apply initial state so the load button shows "Скачать"/"Загрузить"
        # based on whether weights are already on disk.
        self.update_transcription_state("unloaded")
        # Set install button to "Скачано" if everything is in place already.
        self.refresh_install_button_state()

    def _build_mic_row(self, layout, tr_cfg: dict) -> None:
        """Microphone selector. Lists input devices via sounddevice."""
        tr_lang = self.lang.get("transcription", {})
        tooltips = self.lang.get("tooltips", {})

        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel(tr_lang.get("input_device_label", "Microphone:"))
        label.setStyleSheet("border: none;")
        label.setMinimumWidth(150)
        row.addWidget(label)

        combo = StyledComboBox()
        combo.setMinimumWidth(220)
        combo.setToolTip(tooltips.get("transcription_input_device", ""))

        # Always offer "Auto" first; selecting it stores None in config.
        combo.addItem(tr_lang.get("input_device_auto", "Auto (system default)"), None)

        try:
            from ...transcription.audio_recorder import list_input_devices
            for idx, label_text in list_input_devices():
                combo.addItem(label_text, idx)
        except Exception:
            pass

        # Restore current selection
        current_value = tr_cfg.get("audio", {}).get("input_device", None)
        try:
            current_value = int(current_value) if current_value is not None else None
        except (TypeError, ValueError):
            current_value = None
        for i in range(combo.count()):
            if combo.itemData(i) == current_value:
                combo.setCurrentIndex(i)
                break

        def on_change(_idx):
            data = combo.currentData()
            self.transcription_input_device_changed.emit(data)

        combo.currentIndexChanged.connect(on_change)
        row.addWidget(combo, 1)
        layout.addLayout(row)

        self.tr_mic_combo = combo
        self.tr_mic_label = label

    def _tr_action_button_style(self, accent: str = "#444444") -> str:
        return f"""
            QPushButton {{
                background-color: #333333;
                color: #FFFFFF;
                border: 1px solid {accent};
                border-radius: 8px;
                padding: 5px 10px;
            }}
            QPushButton:hover {{
                background-color: {accent};
                color: #FFFFFF;
            }}
            QPushButton:disabled {{
                color: #666666;
                border: 1px solid #333333;
            }}
        """

    def _update_toggle_style(self, btn: QPushButton, active: bool) -> None:
        if active:
            btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #3D8948;
                    color: white;
                    border-radius: 9px;
                    font-weight: bold;
                    font-size: 5px;
                    margin: 0px;
                    border: none;
                }
                QPushButton:hover { background-color: #2A6C34; }
                """
            )
        else:
            btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #676664;
                    color: #FFFFFF;
                    border-radius: 9px;
                    font-weight: bold;
                    font-size: 5px;
                    margin: 0px;
                    border: none;
                }
                QPushButton:hover { background-color: #DDDDDD; color: #000000; }
                """
            )

    def _add_tr_combo_row(self, layout, label_text, options, current_value, tooltip, on_change,
                          row_key=None):
        """Add a labeled combo box row. Returns the combo for later updates.

        ``row_key`` lets update_language() find the label and option list for
        re-translation when the user switches between RU/EN at runtime.
        """
        tr_lang = self.lang.get("transcription", {})

        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel(label_text)
        label.setStyleSheet("border: none;")
        label.setMinimumWidth(150)
        row.addWidget(label)

        combo = StyledComboBox()
        combo.setMinimumWidth(220)
        for value, lang_key in options:
            display = tr_lang.get(lang_key, str(value))
            combo.addItem(display, value)

        # Set current selection by data
        for i in range(combo.count()):
            if combo.itemData(i) == current_value:
                combo.setCurrentIndex(i)
                break

        combo.setToolTip(tooltip or "")
        combo.currentIndexChanged.connect(
            lambda _i: on_change(combo.currentData())
        )
        row.addWidget(combo, 1)
        layout.addLayout(row)

        if row_key:
            registry_key, label_key = (
                row_key if isinstance(row_key, tuple) else (row_key, None)
            )
            self._tr_rows[registry_key] = {
                "label": label,
                "combo": combo,
                "options": options,
                "label_key": label_key,
            }
        return combo

    def _add_tr_toggle_row(self, layout, label_text, current_value, tooltip, on_change,
                           row_key=None):
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel(label_text)
        label.setStyleSheet("border: none;")
        row.addWidget(label)
        row.addStretch()

        btn = QPushButton("•")
        btn.setFixedSize(18, 18)
        btn.setCheckable(True)
        btn.setChecked(bool(current_value))
        btn.setToolTip(tooltip or "")
        self._update_toggle_style(btn, btn.isChecked())

        def handle(checked):
            self._update_toggle_style(btn, checked)
            on_change(checked)

        btn.toggled.connect(handle)
        row.addWidget(btn)
        layout.addLayout(row)

        if row_key:
            registry_key, label_key = (
                row_key if isinstance(row_key, tuple) else (row_key, None)
            )
            self._tr_rows[registry_key] = {
                "label": label,
                "btn": btn,
                "label_key": label_key,
            }
        return btn

    def _on_tr_load_btn_clicked(self) -> None:
        if not self._tr_buttons_armed:
            return
        self.transcription_load_clicked.emit()

    def _on_tr_unload_btn_clicked(self) -> None:
        if not self._tr_buttons_armed:
            return
        self.transcription_unload_clicked.emit()

    def _on_tr_install_btn_clicked(self) -> None:
        if not self._tr_buttons_armed:
            return
        self.transcription_install_clicked.emit()

    def _on_tr_enable_toggled(self, checked: bool) -> None:
        self._update_toggle_style(self.tr_enable_btn, checked)
        self._update_transcription_body_visibility()
        self.transcription_enable_toggled.emit(checked)

    def _on_tr_preload_toggled(self, checked: bool) -> None:
        self._update_toggle_style(self.tr_preload_btn, checked)
        self.transcription_preload_toggled.emit(checked)

    def _update_transcription_body_visibility(self) -> None:
        if hasattr(self, "tr_body"):
            self.tr_body.setVisible(self.tr_enable_btn.isChecked())

    def _on_engine_combo_changed(self, engine: str) -> None:
        """User picked a different ASR engine in the dropdown."""
        engine = (engine or "whisper").lower()
        self._update_engine_container_visibility(engine)
        self.transcription_engine_changed.emit(engine)

    def _update_engine_container_visibility(self, engine: str) -> None:
        """Show only the active engine's settings sub-block."""
        if hasattr(self, "tr_whisper_container"):
            self.tr_whisper_container.setVisible(engine == "whisper")
        if hasattr(self, "tr_parakeet_container"):
            self.tr_parakeet_container.setVisible(engine == "parakeet")

    def _active_engine_name(self) -> str:
        """Engine selected in config (whisper by default)."""
        return (self.config.get("transcription", {}).get("engine") or "whisper").lower()

    def _is_active_model_downloaded(self) -> bool:
        """True when the active engine's weights are on disk.

        On any unexpected failure we return False so the user can still see
        the "Install / Download" button — returning True would silently
        disable it and trap the user in a state they can't fix from the UI.
        """
        engine = self._active_engine_name()
        try:
            if engine == "parakeet":
                from ...transcription.parakeet_manager import is_parakeet_downloaded
                return is_parakeet_downloaded()
            from ...transcription.model_manager import is_model_downloaded
            whisper = self.config.get("transcription", {}).get("whisper", {}) or {}
            return is_model_downloaded(whisper.get("model", "large-v3"))
        except Exception:
            import logging
            logging.getLogger("ClipGen").warning(
                "Failed to check model presence for engine=%s", engine, exc_info=True
            )
            return False

    def update_transcription_state(self, state: str) -> None:
        """Reflect the current ASR model state in the status label and buttons."""
        if not hasattr(self, "tr_status_value"):
            return
        tr_lang = self.lang.get("transcription", {})
        mapping = {
            "unloaded": ("state_unloaded", "#888888"),
            "loading": ("state_loading", "#5085D0"),
            "downloading": ("state_downloading", "#5085D0"),
            "ready": ("state_ready", "#28A745"),
            "transcribing": ("state_transcribing", "#FFC107"),
            "error": ("state_error", "#DC3545"),
        }
        key, color = mapping.get(state, ("state_unloaded", "#888888"))

        # If model isn't on disk yet, show "Not downloaded" instead of
        # "Unloaded" so the load button label "Скачать модель" makes sense.
        if state == "unloaded" and not self._is_active_model_downloaded():
            key, color = ("state_not_downloaded", "#888888")

        # If the model is ready and we have runtime info, append it for context
        # — e.g. "Готова (cuda, float16, 6.0с)". For other states the bare
        # status label is enough.
        text = tr_lang.get(key, state)
        if state == "ready":
            info = getattr(self, "_tr_last_info", {}) or {}
            device = info.get("device")
            compute = info.get("compute_type")
            secs = info.get("load_seconds")
            extras = []
            if device:
                extras.append(str(device))
            if compute:
                extras.append(str(compute))
            if isinstance(secs, (int, float)):
                unit = tr_lang.get("seconds_short", "s")
                extras.append(f"{secs:.1f}{unit}")
            if extras:
                text = f"{text} ({', '.join(extras)})"

        self.tr_status_value.setText(text)
        self.tr_status_value.setStyleSheet(
            f"border: none; color: {color}; font-weight: bold;"
        )

        # Remember last state so update_language() can re-translate it.
        self._tr_last_state = state

        # Load button is only for in-memory load — it requires the model
        # to already be on disk. If the model is missing, disable the load
        # button and direct the user to "Установить / Скачать".
        downloaded = self._is_active_model_downloaded()
        self.tr_load_btn.setText(tr_lang.get("btn_load", "Load model"))

        # Enable / disable buttons based on state.
        load_enabled = downloaded and state in ("unloaded", "error")
        self.tr_load_btn.setEnabled(load_enabled)
        self.tr_unload_btn.setEnabled(state in ("ready",))

        # Install button label depends on what's actually missing right now.
        self.refresh_install_button_state()

    def update_transcription_info(self, info: dict) -> None:
        """Cache the latest runtime info and refresh the status label."""
        self._tr_last_info = dict(info or {})
        # Re-render the status if a state has been set already so the
        # device/compute_type/load_seconds suffix appears immediately.
        if hasattr(self, "_tr_last_state"):
            self.update_transcription_state(self._tr_last_state)

    def refresh_install_button_state(self) -> None:
        """Update install button label/enabled based on what's missing.

        States:
          • busy (during install/download) → "Установка...", disabled
          • everything ready (deps + model on disk) → "Скачано", disabled
          • something missing                       → "Установить / Скачать", enabled
        """
        if not hasattr(self, "tr_install_btn"):
            return
        if getattr(self, "_tr_install_busy", False):
            return  # busy state takes priority

        tr_lang = self.lang.get("transcription", {})

        # Deps check (lightweight: just import probe). Engine-aware so the
        # button reflects what the user picked, not just Whisper.
        try:
            from ...transcription.deps import check_dependencies_for_engine
            deps_missing = check_dependencies_for_engine(
                self._active_engine_name(), include_cuda=False
            )
        except Exception:
            deps_missing = []

        # Model presence check (engine-aware).
        model_present = self._is_active_model_downloaded()

        if not deps_missing and model_present:
            self.tr_install_btn.setText(tr_lang.get("btn_installed", "Downloaded"))
            self.tr_install_btn.setEnabled(False)
        else:
            self.tr_install_btn.setText(
                tr_lang.get("btn_install", "Install / Download")
            )
            self.tr_install_btn.setEnabled(True)

    def set_transcription_install_busy(self, busy: bool, cancellable: bool = False) -> None:
        """Toggle the install button label/enabled state during installation."""
        if not hasattr(self, "tr_install_btn"):
            return
        self._tr_install_busy = busy
        self._tr_install_cancellable = cancellable
        tr_lang = self.lang.get("transcription", {})
        if busy:
            self.tr_install_btn.setEnabled(bool(cancellable))
            self.tr_install_btn.setText(
                tr_lang.get("btn_cancel_download" if cancellable else "btn_installing",
                            "Cancel" if cancellable else "Installing...")
            )
        else:
            self._tr_install_cancellable = False
            # When the install/download finishes, fall through to the
            # state-aware refresher so the button can show "Скачано" if
            # everything is now in place.
            self.refresh_install_button_state()
