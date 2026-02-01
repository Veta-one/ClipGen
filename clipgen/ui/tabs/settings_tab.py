"""Settings tab - API keys, models, provider selection, etc."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QScrollArea, QRadioButton, QButtonGroup
)
from PyQt5.QtCore import Qt, pyqtSignal

from ..styles import Styles
from ..widgets import StyledComboBox


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

    # Other signals
    autostart_toggled = pyqtSignal(bool)
    auto_switch_toggled = pyqtSignal()
    visibility_toggled = pyqtSignal(bool)
    proxy_enabled_changed = pyqtSignal(bool)
    proxy_type_changed = pyqtSignal(str)
    proxy_string_changed = pyqtSignal(str)

    def __init__(self, config: dict, lang: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.lang = lang
        self._test_statuses = {}

        # Store references to time labels for live updates
        self.gemini_model_time_labels = {}
        self.openai_model_time_labels = {}
        self.gemini_key_test_buttons = {}
        self.openai_key_test_buttons = {}
        self.gemini_model_test_buttons = {}
        self.openai_model_test_buttons = {}

        self._setup_ui()

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

        label = QLabel(lang.get("provider_label", "Provider:"))
        label.setStyleSheet("border: none; font-weight: bold; font-size: 14px;")
        frame_layout.addWidget(label)

        self.provider_combo = StyledComboBox()
        self.provider_combo.addItem(lang.get("provider_gemini", "Google Gemini"))
        self.provider_combo.addItem(lang.get("provider_openai", "OpenAI Compatible"))
        self.provider_combo.setMinimumWidth(250)
        self.provider_combo.setCurrentIndex(0 if self.config.get("provider") == "gemini" else 1)
        self.provider_combo.setToolTip(self.lang.get("tooltips", {}).get("provider_dropdown", ""))
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
        label = QLabel(lang.get("api_key_label", "API ключи:"))
        label.setStyleSheet("font-size: 16px;")
        header.addWidget(label)

        # Eye button (visibility toggle)
        self.gemini_eye_btn = self._create_mini_button("#676664", "#DDDDDD",
            self.lang.get("tooltips", {}).get("toggle_keys_visibility", "Toggle key visibility"))
        self.gemini_eye_btn.clicked.connect(self._toggle_visibility)
        header.addWidget(self.gemini_eye_btn)

        # Auto-switch button
        self.gemini_auto_switch_btn = self._create_mini_button("#676664", "#DDDDDD",
            self.lang.get("tooltips", {}).get("auto_switch_keys", "Auto-switch on quota error"))
        self.gemini_auto_switch_btn.clicked.connect(lambda: self.auto_switch_toggled.emit())
        header.addWidget(self.gemini_auto_switch_btn)

        # Add key button
        add_key_btn = self._create_mini_button("#3D8948", "#2A6C34",
            self.lang.get("tooltips", {}).get("add_api_key", "Add API key"))
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
        label = QLabel(lang.get("gemini_models_label", "Модели:"))
        label.setStyleSheet("font-size: 16px;")
        header.addWidget(label)

        add_model_btn = self._create_mini_button("#3D8948", "#2A6C34",
            self.lang.get("tooltips", {}).get("add_model", "Add model"))
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
        url_layout.addWidget(QLabel(lang.get("base_url_label", "Base URL:")))

        self.openai_base_url_input = QLineEdit(self.config.get("openai_base_url", ""))
        self.openai_base_url_input.setPlaceholderText(lang.get("base_url_placeholder", "https://openrouter.ai/api/v1"))
        self.openai_base_url_input.setStyleSheet("background-color: #2a2a2a; color: white; border: 1px solid #444; padding: 5px;")
        self.openai_base_url_input.setToolTip(self.lang.get("tooltips", {}).get("base_url_input", ""))
        self.openai_base_url_input.textChanged.connect(lambda t: self.openai_base_url_changed.emit(t))
        url_layout.addWidget(self.openai_base_url_input)
        layout.addWidget(url_frame)

        # API Keys Header
        keys_header_layout = QHBoxLayout()
        keys_header_layout.setContentsMargins(0, 10, 0, 0)
        label = QLabel(lang.get("openai_api_keys_label", "API ключи:"))
        label.setStyleSheet("font-size: 16px;")
        keys_header_layout.addWidget(label)

        # Eye button
        self.openai_eye_btn = self._create_mini_button("#676664", "#DDDDDD",
            self.lang.get("tooltips", {}).get("toggle_keys_visibility", "Toggle key visibility"))
        self.openai_eye_btn.clicked.connect(self._toggle_visibility)
        keys_header_layout.addWidget(self.openai_eye_btn)

        # Auto-switch
        self.openai_auto_switch_btn = self._create_mini_button("#676664", "#DDDDDD",
            self.lang.get("tooltips", {}).get("auto_switch_keys", "Auto-switch on quota error"))
        self.openai_auto_switch_btn.clicked.connect(lambda: self.auto_switch_toggled.emit())
        keys_header_layout.addWidget(self.openai_auto_switch_btn)

        # Add key
        add_key_btn = self._create_mini_button("#3D8948", "#2A6C34",
            self.lang.get("tooltips", {}).get("add_api_key", "Add API key"))
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
        label = QLabel(lang.get("openai_models_label", "Модели:"))
        label.setStyleSheet("font-size: 16px;")
        models_header.addWidget(label)

        add_model_btn = self._create_mini_button("#3D8948", "#2A6C34",
            self.lang.get("tooltips", {}).get("add_model", "Add model"))
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

        label = QLabel(lang.get("autostart_label", "Автозапуск с Windows"))
        label.setStyleSheet("border: none; font-size: 14px;")
        autostart_layout.addWidget(label)
        autostart_layout.addStretch()

        self.autostart_btn = QPushButton("•")
        self.autostart_btn.setFixedSize(18, 18)
        self.autostart_btn.setCheckable(True)
        self.autostart_btn.setToolTip(self.lang.get("tooltips", {}).get("autostart_toggle", ""))
        self.autostart_btn.toggled.connect(self._on_autostart_toggled)
        self._update_autostart_style(False)
        autostart_layout.addWidget(self.autostart_btn)

        layout.addWidget(autostart_group)

        # Proxy
        proxy_group = QFrame()
        proxy_group.setStyleSheet("background-color: #252525; border-radius: 10px; padding: 5px;")
        proxy_layout = QVBoxLayout(proxy_group)

        top_row = QHBoxLayout()
        proxy_label = QLabel(lang.get("proxy_title", "Proxy (Обход VPN)"))
        proxy_label.setStyleSheet("border: none;")
        top_row.addWidget(proxy_label)
        top_row.addStretch()

        enable_label = QLabel(lang.get("proxy_enable_label", "Включить:"))
        enable_label.setStyleSheet("color: #FFFFFF; border: none;")
        top_row.addWidget(enable_label)

        self.proxy_enable_btn = QPushButton("•")
        self.proxy_enable_btn.setFixedSize(18, 18)
        self.proxy_enable_btn.setCheckable(True)
        self.proxy_enable_btn.setChecked(self.config.get("proxy_enabled", False))
        self.proxy_enable_btn.setToolTip(self.lang.get("tooltips", {}).get("proxy_enable_toggle", ""))
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
        self.proxy_type_combo.setToolTip(self.lang.get("tooltips", {}).get("proxy_type_dropdown", ""))
        self.proxy_type_combo.currentTextChanged.connect(lambda t: self.proxy_type_changed.emit(t))
        input_row.addWidget(self.proxy_type_combo)

        self.proxy_input = QLineEdit(self.config.get("proxy_string", ""))
        self.proxy_input.setPlaceholderText("user:pass@ip:port")
        self.proxy_input.setToolTip(self.lang.get("tooltips", {}).get("proxy_input", ""))
        self.proxy_input.textChanged.connect(lambda t: self.proxy_string_changed.emit(t))
        input_row.addWidget(self.proxy_input)

        proxy_layout.addLayout(input_row)

        hint = QLabel(lang.get("proxy_hint", "Формат: логин:пароль@ip:порт"))
        hint.setStyleSheet("color: #666; font-size: 10px; border: none; margin-left: 2px;")
        proxy_layout.addWidget(hint)

        self._update_proxy_ui_state(self.config.get("proxy_enabled", False))
        layout.addWidget(proxy_group)

        # Language & Scale
        lang_group = QFrame()
        lang_group.setStyleSheet("background-color: transparent;")
        lang_layout = QHBoxLayout(lang_group)
        lang_layout.setContentsMargins(0, 0, 0, 0)

        # Language section (left)
        self.language_label = QLabel(lang.get("language_label", "Язык:"))
        lang_layout.addWidget(self.language_label)

        self.language_combo = StyledComboBox()
        self.language_combo.setMinimumWidth(100)
        self.language_combo.setToolTip(self.lang.get("tooltips", {}).get("language_selection", ""))
        self.language_combo.addItems(["en", "ru"])
        current_index = self.language_combo.findText(self.config.get("language", "en"))
        if current_index >= 0:
            self.language_combo.setCurrentIndex(current_index)
        self.language_combo.currentTextChanged.connect(lambda t: self.language_changed.emit(t))
        lang_layout.addWidget(self.language_combo)

        # Stretch to push scale to the right
        lang_layout.addStretch()

        # Scale section (right)
        self.zoom_label = QLabel(lang.get("zoom_label", "Zoom:"))
        lang_layout.addWidget(self.zoom_label)

        self.scale_down_btn = QPushButton("-")
        self.scale_down_btn.setFixedSize(24, 24)
        self.scale_down_btn.setStyleSheet("background-color: #444; border-radius: 4px;")
        self.scale_down_btn.setToolTip(self.lang.get("tooltips", {}).get("scale_down", ""))
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
        self.scale_up_btn.setToolTip(self.lang.get("tooltips", {}).get("scale_up", ""))
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
        name_input.setPlaceholderText("Имя...")
        name_input.setFixedWidth(80)
        name_input.setStyleSheet("border-radius: 8px; border: 1px solid #444444; padding: 5px; background-color: #2a2a2a; color: #FFFFFF;")
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

        Note: Due to complex UI structure, some elements require app restart
        to fully update. Main elements are updated immediately.
        """
        self.lang = lang
        settings_lang = lang.get("settings", {})

        # Update provider combo items
        current_provider_idx = self.provider_combo.currentIndex()
        self.provider_combo.blockSignals(True)
        self.provider_combo.clear()
        self.provider_combo.addItem(settings_lang.get("provider_gemini", "Google Gemini"))
        self.provider_combo.addItem(settings_lang.get("provider_openai", "OpenAI Compatible"))
        self.provider_combo.setCurrentIndex(current_provider_idx)
        self.provider_combo.blockSignals(False)

        # Update language label
        self.language_label.setText(settings_lang.get("language_label", "Language:"))

        # Update zoom label
        self.zoom_label.setText(settings_lang.get("zoom_label", "Zoom:"))
