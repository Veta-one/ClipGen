"""Custom dialog boxes with dark theme."""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextBrowser, QPushButton, QSizePolicy
)
from PyQt5.QtCore import Qt
from ctypes import windll, c_int, byref


def set_dark_titlebar(hwnd: int) -> None:
    """Apply dark titlebar to a window (Windows 10/11)."""
    try:
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
            byref(c_int(1)), c_int(4)
        )
    except Exception:
        pass


class CustomMessageBox(QDialog):
    """Custom confirmation dialog with dark theme.

    Styled like the original with:
    - Dark titlebar
    - Yes button turns RED on hover (destructive action)
    - No button turns GREEN on hover (safe/cancel action)

    With ``scrollable=True`` the body is rendered inside a scrollable
    text browser and the dialog gets a fixed comfortable size, so long
    content (e.g. release notes) can never push the buttons off-screen.

    ``html_variants`` (used with ``scrollable=True``) is an optional
    ``{code: html}`` mapping of body variants — e.g. release notes per
    language. When it holds more than one entry, a small switcher row is
    shown above the body; ``default_variant`` selects the initial one.
    """

    # Languages name themselves in the switcher — a native name is the
    # same for every viewer, so these are intentionally not translated.
    _VARIANT_NATIVE_NAMES = {"en": "English", "ru": "Русский"}

    def __init__(
        self,
        parent,
        title: str,
        text: str,
        yes_text: str = "Yes",
        no_text: str = "No",
        scrollable: bool = False,
        html_variants: dict = None,
        default_variant: str = None
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(350)

        # Apply dark titlebar
        set_dark_titlebar(int(self.winId()))

        # Main layout with equal margins
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 15, 20, 15)
        main_layout.setSpacing(15)

        self.message_label = None
        self.message_area = None
        self._html_variants = dict(html_variants or {})
        self._variant_buttons = {}
        self._current_variant = None
        if scrollable:
            from .styles import Styles
            if len(self._html_variants) > 1:
                main_layout.addLayout(self._build_variant_switcher())
            self.message_area = QTextBrowser()
            self.message_area.setHtml(text)
            self.message_area.setOpenExternalLinks(True)
            self.message_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.message_area.setStyleSheet(f"""
                QTextBrowser {{
                    background-color: #1F1F1F;
                    color: #FFFFFF;
                    border: 1px solid #383838;
                    border-radius: 8px;
                    padding: 8px;
                    font-size: 13px;
                }}
                QScrollBar:vertical {{
                    background-color: transparent;
                    width: 8px;
                    margin: 0;
                }}
                QScrollBar::handle:vertical {{
                    background-color: {Styles.BORDER};
                    border-radius: 4px;
                    min-height: 20px;
                }}
                QScrollBar::handle:vertical:hover {{
                    background-color: {Styles.BUTTON_HOVER};
                }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                    height: 0;
                }}
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                    background-color: transparent;
                }}
            """)
            main_layout.addWidget(self.message_area, 1)
            if self._html_variants:
                initial = (default_variant
                           if default_variant in self._html_variants
                           else next(iter(self._html_variants)))
                self._select_variant(initial)
        else:
            # Message label - simple QLabel with HTML support
            from PyQt5.QtWidgets import QLabel
            self.message_label = QLabel()
            self.message_label.setText(text)
            self.message_label.setTextFormat(Qt.RichText)
            self.message_label.setWordWrap(True)
            self.message_label.setOpenExternalLinks(True)
            self.message_label.setStyleSheet("color: #FFFFFF; font-size: 13px;")
            main_layout.addWidget(self.message_label)

        # Buttons layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # Yes button - RED on hover (destructive/confirm)
        self.yes_button = QPushButton(yes_text)
        self.yes_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.yes_button.clicked.connect(self.accept)
        self.yes_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 8px 0;
            }
            QPushButton:hover {
                background-color: #C82333;
            }
        """)
        button_layout.addWidget(self.yes_button)

        # No button - GREEN on hover (safe/cancel)
        self.no_button = QPushButton(no_text)
        self.no_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.no_button.clicked.connect(self.reject)
        self.no_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 8px 0;
            }
            QPushButton:hover {
                background-color: #28A745;
            }
        """)
        button_layout.addWidget(self.no_button)

        main_layout.addLayout(button_layout)

        # Dialog style
        self.setStyleSheet("""
            QDialog {
                background-color: #252525;
                border: 1px solid #444444;
            }
        """)

        # Adjust size to content
        if scrollable:
            self._apply_scrollable_size()
        else:
            self.adjustSize()

    def _build_variant_switcher(self) -> QHBoxLayout:
        """Small pill buttons that swap the body between content variants."""
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addStretch(1)
        for code in sorted(self._html_variants):
            button = QPushButton(
                self._VARIANT_NATIVE_NAMES.get(code, code.upper())
            )
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet("""
                QPushButton {
                    background-color: #2A2A2A;
                    color: #AAAAAA;
                    border: 1px solid #383838;
                    border-radius: 6px;
                    padding: 4px 14px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    color: #FFFFFF;
                }
                QPushButton:checked {
                    background-color: #3A3A3A;
                    color: #FFFFFF;
                    border-color: #555555;
                }
            """)
            button.clicked.connect(lambda _checked, c=code: self._select_variant(c))
            self._variant_buttons[code] = button
            row.addWidget(button)
        return row

    def _select_variant(self, code: str) -> None:
        """Show one content variant and sync the switcher button states."""
        if code not in self._html_variants or self.message_area is None:
            return
        self._current_variant = code
        for variant_code, button in self._variant_buttons.items():
            button.setChecked(variant_code == code)
        self.message_area.setHtml(self._html_variants[code])

    def update_html_variants(self, html_variants: dict) -> None:
        """Swap the variant contents in place (e.g. expanding a changelog).

        Keeps the current language selection when the new mapping still
        contains it. The variant KEYS must match the ones the dialog was
        built with — the switcher buttons are not rebuilt.
        """
        if self.message_area is None or not html_variants:
            return
        self._html_variants = dict(html_variants)
        code = (self._current_variant
                if self._current_variant in self._html_variants
                else next(iter(self._html_variants)))
        self._select_variant(code)

    def _apply_scrollable_size(self) -> None:
        """Fixed comfortable size, capped to the available screen area."""
        from PyQt5.QtWidgets import QApplication
        width, height = 560, 640
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            width = min(width, max(360, available.width() - 80))
            height = min(height, max(320, available.height() - 120))
        self.resize(width, height)

    def showEvent(self, event):
        """Ensure dark titlebar on show."""
        super().showEvent(event)
        set_dark_titlebar(int(self.winId()))


class InfoMessageBox(QDialog):
    """Information dialog with single OK button and dark theme."""

    def __init__(
        self,
        parent,
        title: str,
        text: str,
        button_text: str = "OK"
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setMinimumHeight(150)

        # Apply dark titlebar
        set_dark_titlebar(int(self.winId()))

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # Message area
        self.message_area = QTextBrowser()
        self.message_area.setHtml(text)
        self.message_area.setOpenExternalLinks(True)
        self.message_area.setStyleSheet("""
            background-color: transparent;
            color: #FFFFFF;
            border: none;
            font-size: 13px;
        """)
        self.message_area.setMaximumHeight(100)
        main_layout.addWidget(self.message_area)

        # Single OK button - GREEN on hover
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        self.ok_button = QPushButton(button_text)
        self.ok_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.ok_button.clicked.connect(self.accept)
        self.ok_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 8px 0;
            }
            QPushButton:hover {
                background-color: #28A745;
            }
        """)
        button_layout.addWidget(self.ok_button)

        main_layout.addLayout(button_layout)

        # Dialog style
        self.setStyleSheet("""
            QDialog {
                background-color: #252525;
                border: 1px solid #444444;
            }
        """)

    def showEvent(self, event):
        """Ensure dark titlebar on show."""
        super().showEvent(event)
        set_dark_titlebar(int(self.winId()))


class WarningMessageBox(QDialog):
    """Warning dialog with single OK button and dark theme."""

    def __init__(
        self,
        parent,
        title: str,
        text: str,
        button_text: str = "OK"
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setMinimumHeight(150)

        # Apply dark titlebar
        set_dark_titlebar(int(self.winId()))

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # Message area
        self.message_area = QTextBrowser()
        self.message_area.setHtml(text)
        self.message_area.setOpenExternalLinks(True)
        self.message_area.setStyleSheet("""
            background-color: transparent;
            color: #FFFFFF;
            border: none;
            font-size: 13px;
        """)
        self.message_area.setMaximumHeight(100)
        main_layout.addWidget(self.message_area)

        # Single OK button - ORANGE/YELLOW on hover for warning
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        self.ok_button = QPushButton(button_text)
        self.ok_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.ok_button.clicked.connect(self.accept)
        self.ok_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 8px 0;
            }
            QPushButton:hover {
                background-color: #E0A800;
            }
        """)
        button_layout.addWidget(self.ok_button)

        main_layout.addLayout(button_layout)

        # Dialog style
        self.setStyleSheet("""
            QDialog {
                background-color: #252525;
                border: 1px solid #444444;
            }
        """)

    def showEvent(self, event):
        """Ensure dark titlebar on show."""
        super().showEvent(event)
        set_dark_titlebar(int(self.winId()))
