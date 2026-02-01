"""System tray icon management."""

import os
import time

from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import Qt, QSize, QTimer

from ..core.constants import resource_path


class TrayIconManager:
    """Manages system tray icon with dynamic states."""

    # Icon colors (matching original)
    COLOR_DEFAULT = "#FFFFFF"
    COLOR_WORKING = "#FFBF08"  # Original yellow/orange
    COLOR_SUCCESS = "#28A745"
    COLOR_ERROR = "#F33100"    # Original red
    COLOR_UPDATE = "#007AFF"   # iOS blue
    COLOR_WARNING = "#F33100"

    def __init__(self, parent, lang: dict):
        """Initialize tray icon manager.

        Args:
            parent: Parent QWidget
            lang: Language strings dict
        """
        self.parent = parent
        self.lang = lang
        self.tray_icon = QSystemTrayIcon(parent)

        self._setup_icon()
        self._setup_menu()

        # Callbacks
        self.on_show_hide = None
        self.on_quit = None

    def _setup_icon(self) -> None:
        """Set up the default tray icon."""
        icon_path = resource_path("ClipGen.ico")
        if os.path.exists(icon_path):
            self.default_icon = QIcon(icon_path)
        else:
            # Fallback to dynamic icon
            self.default_icon = self._create_dynamic_icon("#4A90D9", "C")
        self.tray_icon.setIcon(self.default_icon)
        self.tray_icon.setToolTip("ClipGen")

    def _setup_menu(self) -> None:
        """Set up the tray context menu."""
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #2e2e2e;
                color: #FFFFFF;
                border: 1px solid #444444;
                padding: 5px;
            }
            QMenu::item:selected {
                background-color: #444444;
            }
        """)

        # Show/Hide action
        tray_lang = self.lang.get("tray", {})
        self.show_hide_action = QAction(
            tray_lang.get("show_hide", "Show/Hide"), self.parent
        )
        self.show_hide_action.triggered.connect(self._on_show_hide)
        menu.addAction(self.show_hide_action)

        menu.addSeparator()

        # Quit action
        self.quit_action = QAction(
            tray_lang.get("quit", "Quit"), self.parent
        )
        self.quit_action.triggered.connect(self._on_quit)
        menu.addAction(self.quit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_activated)

    def _on_show_hide(self) -> None:
        if self.on_show_hide:
            self.on_show_hide()

    def _on_quit(self) -> None:
        if self.on_quit:
            self.on_quit()

    def _on_activated(self, reason) -> None:
        """Handle tray icon click."""
        if reason == QSystemTrayIcon.Trigger:
            if self.on_show_hide:
                self.on_show_hide()

    def show(self) -> None:
        """Show tray icon."""
        self.tray_icon.show()

    def hide(self) -> None:
        """Hide tray icon."""
        self.tray_icon.hide()

    def _create_dynamic_icon(self, color: str, text: str = "", text_color: str = "#000000") -> QIcon:
        """Create a colored icon with optional text.

        Args:
            color: Background color (hex)
            text: Optional text to display
            text_color: Text color (hex)

        Returns:
            QIcon with the specified appearance
        """
        size = 64
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw rounded rectangle (like original)
        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, size, size, 12, 12)

        # Draw text if provided
        if text:
            painter.setPen(QColor(text_color))
            # Dynamic font size based on text length
            if len(str(text)) > 3:
                font_size = 20
            elif len(str(text)) > 2:
                font_size = 24
            else:
                font_size = 32
            font = QFont()
            font.setPointSize(font_size)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(pixmap.rect(), Qt.AlignCenter, str(text))

        painter.end()
        return QIcon(pixmap)

    def set_default(self) -> None:
        """Set default icon."""
        self.tray_icon.setIcon(self.default_icon)

    def set_working(self, time_str: str = "") -> None:
        """Set working (yellow) icon with optional time."""
        icon = self._create_dynamic_icon(self.COLOR_WORKING, time_str)
        self.tray_icon.setIcon(icon)

    def set_success(self, duration: str = "") -> None:
        """Set success (green) icon."""
        text = duration if duration else ""
        icon = self._create_dynamic_icon(self.COLOR_SUCCESS, text)
        self.tray_icon.setIcon(icon)

    def set_error(self) -> None:
        """Set error (red) icon."""
        icon = self._create_dynamic_icon(self.COLOR_ERROR, "!", "#FFFFFF")
        self.tray_icon.setIcon(icon)

    def set_update(self) -> None:
        """Set update available (blue) icon."""
        icon = self._create_dynamic_icon(self.COLOR_UPDATE, "")
        self.tray_icon.setIcon(icon)

    def flash_warning(self) -> None:
        """Flash warning - blink red twice then return to yellow with time."""
        # Get current time from parent window
        current_time_str = "..."
        if hasattr(self.parent, 'start_time') and self.parent.start_time > 0:
            elapsed = time.time() - self.parent.start_time
            current_time_str = f"{elapsed:.1f}"

        # 1. Red
        self.set_error()
        # 2. After 200ms - yellow with time
        QTimer.singleShot(200, lambda: self.set_working(current_time_str))
        # 3. After 400ms - red again
        QTimer.singleShot(400, self.set_error)
        # 4. After 600ms - yellow and continue
        QTimer.singleShot(600, lambda: self.set_working(current_time_str))

    def update_menu_text(self, lang: dict) -> None:
        """Update menu text with new language."""
        self.lang = lang
        tray_lang = lang.get("tray", {})
        self.show_hide_action.setText(tray_lang.get("show_hide", "Show/Hide"))
        self.quit_action.setText(tray_lang.get("quit", "Quit"))
