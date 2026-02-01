"""Prompts tab - hotkey configuration cards."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QFrame, QScrollArea, QKeySequenceEdit,
    QColorDialog
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QColor

from ..styles import Styles
from ..widgets import StyledComboBox


class FocusExpandingTextEdit(QTextEdit):
    """TextEdit that expands on focus and text change."""

    focusIn = pyqtSignal()

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        if text:
            self.setPlainText(text)

    def focusInEvent(self, event):
        self.focusIn.emit()
        super().focusInEvent(event)


class HotkeyCard(QFrame):
    """Card widget for a single hotkey configuration."""

    deleted = pyqtSignal(int)
    combination_changed = pyqtSignal(int, str)
    name_changed = pyqtSignal(int, str)
    prompt_changed = pyqtSignal(int, str)
    color_changed = pyqtSignal(int, str)
    use_custom_model_changed = pyqtSignal(int, bool)
    custom_provider_changed = pyqtSignal(int, str)
    custom_model_changed = pyqtSignal(int, str)
    learning_mode_changed = pyqtSignal(int, bool)
    learning_prompt_changed = pyqtSignal(int, str)

    def __init__(self, index: int, hotkey: dict, lang: dict, config: dict, parent=None):
        super().__init__(parent)
        self.index = index
        self.hotkey = hotkey
        self.lang = lang
        self.config = config
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the card UI."""
        self.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border-radius: 15px;
                padding: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)

        # Header: Hotkey + Color + Delete
        header = QHBoxLayout()
        header.setSpacing(10)

        # Key sequence
        self.hotkey_edit = QKeySequenceEdit(self.hotkey.get("combination", ""))
        self.hotkey_edit.setToolTip(self.lang.get("tooltips", {}).get("hotkey_input", ""))
        self.hotkey_edit.setStyleSheet("""
            QKeySequenceEdit {
                background-color: #333333;
                color: white;
                border-radius: 5px;
                padding: 5px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)
        self.hotkey_edit.keySequenceChanged.connect(self._on_combination_changed)
        header.addWidget(self.hotkey_edit)

        # Color section
        color_layout = QHBoxLayout()
        color_layout.setSpacing(5)

        color_label = QLabel(self.lang.get("settings", {}).get("log_color_label", "Log color:"))
        color_layout.addWidget(color_label)

        color = self.hotkey.get("log_color", "#FFFFFF")
        self.color_input = QLineEdit(color.replace("#", ""))
        self.color_input.setFixedWidth(70)
        self.color_input.setStyleSheet("""
            border-radius: 8px;
            border: 1px solid #444444;
            padding: 5px;
            background-color: #2a2a2a;
        """)
        self.color_input.textChanged.connect(self._on_color_text_changed)
        color_layout.addWidget(self.color_input)

        self.color_button = QPushButton()
        self.color_button.setFixedSize(20, 20)
        self.color_button.setToolTip(self.lang.get("tooltips", {}).get("color_picker", ""))
        self._update_color_button(color)
        self.color_button.clicked.connect(self._open_color_picker)
        color_layout.addWidget(self.color_button)

        header.addLayout(color_layout)

        # Delete button (18x18 circle)
        delete_btn = QPushButton("•")
        delete_btn.setToolTip(self.lang.get("tooltips", {}).get("delete_hotkey", ""))
        delete_btn.setFixedSize(18, 18)
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF5F57;
                color: white;
                border-radius: 9px;
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton:hover { background-color: #FF3B30; }
        """)
        delete_btn.clicked.connect(lambda: self.deleted.emit(self.index))
        header.addWidget(delete_btn)

        layout.addLayout(header)

        # Action name field with label
        name_layout = QHBoxLayout()
        name_label = QLabel(self.lang.get("settings", {}).get("action_name_label", "Action name:"))
        name_layout.addWidget(name_label)

        self.name_input = QLineEdit(self.hotkey.get("name", ""))
        self.name_input.setStyleSheet("""
            border-radius: 8px;
            border: 1px solid #444444;
            padding: 8px;
            background-color: #2a2a2a;
        """)
        self.name_input.setToolTip(self.lang.get("tooltips", {}).get("action_name_input", ""))
        self.name_input.textChanged.connect(
            lambda text: self.name_changed.emit(self.index, text)
        )
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        # Prompt field with label and auto-height
        prompt_label = QLabel(self.lang.get("settings", {}).get("prompt_label", "Prompt:"))
        layout.addWidget(prompt_label)

        self.prompt_input = FocusExpandingTextEdit(self.hotkey.get("prompt", ""))
        self.prompt_input.setStyleSheet("""
            border-radius: 8px;
            border: 1px solid #444444;
            padding: 8px;
            background-color: #2a2a2a;
        """)
        self.prompt_input.setToolTip(self.lang.get("tooltips", {}).get("prompt_input", ""))

        # Auto-height adjustment
        def adjust_height():
            doc_height = self.prompt_input.document().size().height()
            new_height = max(80, min(250, doc_height + 30))
            self.prompt_input.setMinimumHeight(int(new_height))
            self.prompt_input.setMaximumHeight(int(new_height))

        self.prompt_input.focusIn.connect(adjust_height)
        self.prompt_input.textChanged.connect(adjust_height)
        self.prompt_input.textChanged.connect(self._on_prompt_changed)

        # Initial height adjustment
        QTimer.singleShot(0, adjust_height)

        layout.addWidget(self.prompt_input)

        # Custom model section
        self._setup_custom_model_section(layout)

        # Learning mode section
        self._setup_learning_mode_section(layout)

    def _update_color_button(self, color: str) -> None:
        """Update color button appearance."""
        self.color_button.setStyleSheet(f"""
            background-color: {color};
            border-radius: 5px;
            border: none;
        """)

    def _on_combination_changed(self) -> None:
        """Handle combination change."""
        combo = self.hotkey_edit.keySequence().toString()
        self.combination_changed.emit(self.index, combo)

    def _on_color_text_changed(self, text: str) -> None:
        """Handle color text change."""
        color = f"#{text}" if not text.startswith("#") else text
        if len(color) == 7:
            self._update_color_button(color)
            self.color_changed.emit(self.index, color)

    def _on_prompt_changed(self) -> None:
        """Handle prompt text change."""
        self.prompt_changed.emit(self.index, self.prompt_input.toPlainText())

    def _open_color_picker(self) -> None:
        """Open color picker dialog."""
        current = QColor(f"#{self.color_input.text()}")
        color = QColorDialog.getColor(current, self)
        if color.isValid():
            hex_color = color.name()
            self.color_input.setText(hex_color.replace("#", ""))
            self._update_color_button(hex_color)
            self.color_changed.emit(self.index, hex_color)

    def _setup_custom_model_section(self, layout: QVBoxLayout) -> None:
        """Set up custom model selection UI."""
        custom_model_layout = QHBoxLayout()
        custom_model_layout.setSpacing(8)

        # Label
        label = QLabel(self.lang.get("settings", {}).get("custom_model_label", "Custom model:"))
        custom_model_layout.addWidget(label)

        # Toggle button (18x18)
        self.use_custom_model_btn = QPushButton("•")
        self.use_custom_model_btn.setFixedSize(18, 18)
        self.use_custom_model_btn.setCheckable(True)
        is_custom = self.hotkey.get("use_custom_model", False)
        self.use_custom_model_btn.setChecked(is_custom)
        self._update_custom_model_toggle_style(is_custom)
        self.use_custom_model_btn.toggled.connect(self._on_use_custom_model_toggled)
        custom_model_layout.addWidget(self.use_custom_model_btn)

        # Provider combo
        self.custom_provider_combo = StyledComboBox()
        self.custom_provider_combo.addItem(
            self.lang.get("settings", {}).get("provider_gemini", "Gemini"), "gemini"
        )
        self.custom_provider_combo.addItem(
            self.lang.get("settings", {}).get("provider_openai", "OpenAI Compatible"), "openai"
        )
        self.custom_provider_combo.setEnabled(is_custom)
        self.custom_provider_combo.setMinimumWidth(150)

        # Set current provider
        current_provider = self.hotkey.get("custom_provider")
        if current_provider == "openai":
            self.custom_provider_combo.setCurrentIndex(1)

        self.custom_provider_combo.currentIndexChanged.connect(self._on_custom_provider_changed)
        custom_model_layout.addWidget(self.custom_provider_combo)

        # Model combo
        self.custom_model_combo = StyledComboBox()
        self.custom_model_combo.setEnabled(is_custom)
        self.custom_model_combo.setMinimumWidth(200)
        self._populate_model_combo()
        self.custom_model_combo.currentTextChanged.connect(self._on_custom_model_changed)
        custom_model_layout.addWidget(self.custom_model_combo)

        custom_model_layout.addStretch()
        layout.addLayout(custom_model_layout)

    def _update_custom_model_toggle_style(self, checked: bool) -> None:
        """Update toggle button style based on state."""
        if checked:
            self.use_custom_model_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3D8948;
                    color: white;
                    border-radius: 9px;
                    font-weight: bold;
                    font-size: 10px;
                }
                QPushButton:hover { background-color: #2A6C34; }
            """)
        else:
            self.use_custom_model_btn.setStyleSheet("""
                QPushButton {
                    background-color: #676664;
                    color: white;
                    border-radius: 9px;
                    font-weight: bold;
                    font-size: 10px;
                }
                QPushButton:hover { background-color: #888888; }
            """)

    def _on_use_custom_model_toggled(self, checked: bool) -> None:
        """Handle custom model toggle."""
        self._update_custom_model_toggle_style(checked)
        self.custom_provider_combo.setEnabled(checked)
        self.custom_model_combo.setEnabled(checked)
        self.use_custom_model_changed.emit(self.index, checked)

    def _on_custom_provider_changed(self, index: int) -> None:
        """Handle provider change."""
        provider = self.custom_provider_combo.currentData()
        self._populate_model_combo()
        self.custom_provider_changed.emit(self.index, provider)

    def _on_custom_model_changed(self, text: str) -> None:
        """Handle model change."""
        if text:
            self.custom_model_changed.emit(self.index, text)

    def _populate_model_combo(self) -> None:
        """Populate model combo based on selected provider."""
        self.custom_model_combo.blockSignals(True)
        self.custom_model_combo.clear()

        provider = self.custom_provider_combo.currentData()
        if provider == "gemini":
            models = self.config.get("gemini_models", [])
        else:
            models = self.config.get("openai_models", [])

        for model in models:
            self.custom_model_combo.addItem(model.get("name", ""))

        # Set current model
        current_model = self.hotkey.get("custom_model")
        if current_model:
            idx = self.custom_model_combo.findText(current_model)
            if idx >= 0:
                self.custom_model_combo.setCurrentIndex(idx)

        self.custom_model_combo.blockSignals(False)

    def _setup_learning_mode_section(self, layout: QVBoxLayout) -> None:
        """Set up learning mode UI."""
        learning_layout = QHBoxLayout()
        learning_layout.setSpacing(8)

        # Label with brief explanation
        mode_text = self.lang.get("settings", {}).get("learning_mode_label", "Learning mode:")
        hint_text = self.lang.get("settings", {}).get(
            "learning_mode_hint", "(explains AI corrections in popup)"
        )
        label = QLabel(f"{mode_text} {hint_text}")
        label.setStyleSheet("color: #FFFFFF;")
        learning_layout.addWidget(label)

        # Toggle button (18x18)
        self.learning_mode_btn = QPushButton("•")
        self.learning_mode_btn.setFixedSize(18, 18)
        self.learning_mode_btn.setCheckable(True)
        is_learning = self.hotkey.get("learning_mode", False)
        self.learning_mode_btn.setChecked(is_learning)
        self._update_learning_mode_toggle_style(is_learning)
        self.learning_mode_btn.toggled.connect(self._on_learning_mode_toggled)
        self.learning_mode_btn.setToolTip(
            self.lang.get("tooltips", {}).get(
                "learning_mode_toggle",
                "Enable to see explanations of AI corrections"
            )
        )
        learning_layout.addWidget(self.learning_mode_btn)

        learning_layout.addStretch()
        layout.addLayout(learning_layout)

        # Learning prompt field (initially hidden if mode is off)
        self.learning_prompt_container = QWidget()
        self.learning_prompt_container.setStyleSheet("background-color: transparent;")
        prompt_layout = QVBoxLayout(self.learning_prompt_container)
        prompt_layout.setContentsMargins(0, 5, 0, 0)
        prompt_layout.setSpacing(0)

        # Show custom prompt or default from language file if empty
        custom_prompt = self.hotkey.get("learning_prompt", "")
        display_prompt = custom_prompt if custom_prompt else self.lang.get(
            "default_learning_prompt", ""
        )

        self.learning_prompt_input = FocusExpandingTextEdit(display_prompt)
        self.learning_prompt_input.setStyleSheet("""
            border-radius: 8px;
            border: 1px solid #444444;
            padding: 8px;
            background-color: #2a2a2a;
        """)
        self.learning_prompt_input.setToolTip(
            self.lang.get("tooltips", {}).get(
                "learning_prompt_input",
                "Custom prompt for generating explanations"
            )
        )

        # Start collapsed, expand on focus
        self.learning_prompt_input.setMinimumHeight(60)
        self.learning_prompt_input.setMaximumHeight(60)
        self._learning_expanded = False

        def expand_learning_prompt():
            if not self._learning_expanded:
                self._learning_expanded = True
            # Calculate height based on content
            doc_height = self.learning_prompt_input.document().size().height()
            new_height = max(80, min(250, doc_height + 30))
            self.learning_prompt_input.setMinimumHeight(int(new_height))
            self.learning_prompt_input.setMaximumHeight(int(new_height))

        self.learning_prompt_input.focusIn.connect(expand_learning_prompt)
        self.learning_prompt_input.textChanged.connect(
            lambda: expand_learning_prompt() if self._learning_expanded else None
        )
        self.learning_prompt_input.textChanged.connect(self._on_learning_prompt_changed)

        prompt_layout.addWidget(self.learning_prompt_input)

        self.learning_prompt_container.setVisible(is_learning)
        layout.addWidget(self.learning_prompt_container)

    def _update_learning_mode_toggle_style(self, checked: bool) -> None:
        """Update learning mode toggle button style."""
        if checked:
            self.learning_mode_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3D8948;
                    color: white;
                    border-radius: 9px;
                    font-weight: bold;
                    font-size: 10px;
                }
                QPushButton:hover { background-color: #2A6C34; }
            """)
        else:
            self.learning_mode_btn.setStyleSheet("""
                QPushButton {
                    background-color: #676664;
                    color: white;
                    border-radius: 9px;
                    font-weight: bold;
                    font-size: 10px;
                }
                QPushButton:hover { background-color: #888888; }
            """)

    def _on_learning_mode_toggled(self, checked: bool) -> None:
        """Handle learning mode toggle."""
        self._update_learning_mode_toggle_style(checked)
        self.learning_prompt_container.setVisible(checked)
        self.learning_mode_changed.emit(self.index, checked)

    def _on_learning_prompt_changed(self) -> None:
        """Handle learning prompt text change.

        If text matches default prompt, save empty string to use default.
        This allows future default prompt updates to take effect.
        """
        current_text = self.learning_prompt_input.toPlainText().strip()
        default_prompt = self.lang.get("default_learning_prompt", "").strip()

        # If text matches default, save empty string (meaning "use default")
        if current_text == default_prompt:
            self.learning_prompt_changed.emit(self.index, "")
        else:
            self.learning_prompt_changed.emit(self.index, current_text)


class PromptsTab(QWidget):
    """Tab for managing hotkey prompts.

    The entire tab scrolls together (header + cards) like the original.
    """

    hotkey_deleted = pyqtSignal(int)
    hotkey_added = pyqtSignal()
    combination_changed = pyqtSignal(int, str)
    name_changed = pyqtSignal(int, str)
    prompt_changed = pyqtSignal(int, str)
    color_changed = pyqtSignal(int, str)
    use_custom_model_changed = pyqtSignal(int, bool)
    custom_provider_changed = pyqtSignal(int, str)
    custom_model_changed = pyqtSignal(int, str)
    learning_mode_changed = pyqtSignal(int, bool)
    learning_prompt_changed = pyqtSignal(int, str)

    def __init__(self, config: dict, lang: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.lang = lang
        self.cards = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the tab UI - entire content scrolls together."""
        # Main layout for the tab
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Scrollable content widget
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background-color: #1e1e1e;")

        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setSpacing(15)
        self.content_layout.setContentsMargins(15, 15, 15, 15)

        # Header (scrolls with content)
        header_layout = QHBoxLayout()

        self.title_label = QLabel(
            self.lang.get("settings", {}).get("hotkeys_title", "Hotkey Settings")
        )
        self.title_label.setStyleSheet("font-size: 16px;")
        header_layout.addWidget(self.title_label)

        # Add button (18x18 circle)
        self.add_button = QPushButton("•")
        self.add_button.setFixedSize(18, 18)
        self.add_button.setToolTip(self.lang.get("tooltips", {}).get("add_hotkey", "Add hotkey"))
        self.add_button.setStyleSheet("""
            QPushButton {
                background-color: #3D8948;
                color: white;
                border-radius: 9px;
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton:hover { background-color: #2A6C34; }
        """)
        self.add_button.clicked.connect(lambda: self.hotkey_added.emit())
        header_layout.addWidget(self.add_button)

        header_layout.addStretch()
        self.content_layout.addLayout(header_layout)

        # Cards container (no separate scroll - cards added directly)
        self.cards_layout = QVBoxLayout()
        self.cards_layout.setSpacing(10)
        self.content_layout.addLayout(self.cards_layout)

        self.content_layout.addStretch()

        # Scroll area wrapping EVERYTHING
        scroll = QScrollArea()
        scroll.setWidget(self.content_widget)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { background-color: transparent; border: none; }
            QScrollBar:vertical { background: #1e1e1e; width: 4px; border-radius: 2px; }
            QScrollBar::handle:vertical { background: #666666; min-height: 20px; border-radius: 2px; }
            QWidget#qt_scrollarea_viewport { background-color: transparent; }
        """)
        self.scroll = scroll

        main_layout.addWidget(scroll)

        self.refresh()

    def refresh(self) -> None:
        """Refresh the hotkey cards."""
        # Clear existing cards
        for card in self.cards:
            card.deleteLater()
        self.cards.clear()

        # Remove all widgets from cards layout
        while self.cards_layout.count() > 0:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add cards for each hotkey
        for i, hotkey in enumerate(self.config.get("hotkeys", [])):
            card = HotkeyCard(i, hotkey, self.lang, self.config)
            card.deleted.connect(lambda idx: self.hotkey_deleted.emit(idx))
            card.combination_changed.connect(
                lambda idx, combo: self.combination_changed.emit(idx, combo)
            )
            card.name_changed.connect(
                lambda idx, name: self.name_changed.emit(idx, name)
            )
            card.prompt_changed.connect(
                lambda idx, prompt: self.prompt_changed.emit(idx, prompt)
            )
            card.color_changed.connect(
                lambda idx, color: self.color_changed.emit(idx, color)
            )
            card.use_custom_model_changed.connect(
                lambda idx, val: self.use_custom_model_changed.emit(idx, val)
            )
            card.custom_provider_changed.connect(
                lambda idx, val: self.custom_provider_changed.emit(idx, val)
            )
            card.custom_model_changed.connect(
                lambda idx, val: self.custom_model_changed.emit(idx, val)
            )
            card.learning_mode_changed.connect(
                lambda idx, val: self.learning_mode_changed.emit(idx, val)
            )
            card.learning_prompt_changed.connect(
                lambda idx, val: self.learning_prompt_changed.emit(idx, val)
            )
            self.cards_layout.addWidget(card)
            self.cards.append(card)

    def scroll_to_top(self) -> None:
        """Scroll to top of the list."""
        self.scroll.verticalScrollBar().setValue(0)

    def update_language(self, lang: dict) -> None:
        """Update UI text with new language."""
        self.lang = lang

        # Update title
        self.title_label.setText(
            lang.get("settings", {}).get("hotkeys_title", "Hotkey Settings")
        )

        # Update add button tooltip
        self.add_button.setToolTip(
            lang.get("tooltips", {}).get("add_hotkey", "Add hotkey")
        )

        # Refresh cards with new language
        self.refresh()
