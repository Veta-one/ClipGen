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
    """

    def __init__(
        self,
        parent,
        title: str,
        text: str,
        yes_text: str = "Yes",
        no_text: str = "No"
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
        self.adjustSize()

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
