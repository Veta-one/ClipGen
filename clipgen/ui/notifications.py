"""Toast notifications for ClipGen."""

import re
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTextBrowser, QScrollArea,
    QDesktopWidget, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QColor

from .styles import Styles


class ToastNotification(QWidget):
    """Toast notification widget for displaying explanations.

    Features:
    - Positioned at bottom-left of screen
    - Auto-closes after timeout
    - Stays open while mouse is hovering
    - Supports Markdown rendering
    - Scrollable for long content
    """

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._is_hovered = False
        self._should_close = False
        self._animation = None

        self._setup_ui()
        self._setup_timers()

    def _setup_ui(self) -> None:
        """Set up the notification UI."""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Container with background
        self.container = QWidget(self)
        self.container.setStyleSheet(f"""
            QWidget {{
                background-color: {Styles.CARD_BG};
                border-radius: 12px;
                border: 1px solid {Styles.BORDER};
            }}
        """)
        main_layout.addWidget(self.container)

        # Container layout
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(15, 12, 15, 12)
        container_layout.setSpacing(0)

        # Scroll area for content
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
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
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Text browser for Markdown content
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: transparent;
                color: {Styles.TEXT};
                border: none;
                font-size: 13px;
                font-family: 'Segoe UI', sans-serif;
            }}
        """)

        self.scroll_area.setWidget(self.text_browser)
        container_layout.addWidget(self.scroll_area)

        # Shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 5)
        self.container.setGraphicsEffect(shadow)

        # Fixed width
        self.setFixedWidth(420)

    def _setup_timers(self) -> None:
        """Set up auto-close timer."""
        self.close_timer = QTimer(self)
        self.close_timer.setSingleShot(True)
        self.close_timer.timeout.connect(self._on_close_timer)

    def show_message(
        self,
        markdown_text: str,
        timeout_ms: int = 5000
    ) -> None:
        """Display a message in the toast.

        Args:
            markdown_text: Markdown-formatted text to display
            timeout_ms: Auto-close timeout in milliseconds
        """
        if not markdown_text or not markdown_text.strip():
            return

        # Convert Markdown to HTML
        html = self._markdown_to_html(markdown_text)
        self.text_browser.setHtml(html)

        # Calculate content height dynamically
        self.text_browser.document().adjustSize()
        doc_height = self.text_browser.document().size().height()

        # Content area: min 30px, max 280px
        content_height = min(280, max(30, int(doc_height + 5)))
        self.scroll_area.setFixedHeight(content_height)

        # Total widget height = content + container padding (12+12) + some margin
        total_height = content_height + 24 + 10
        self.setFixedHeight(total_height)

        # Position at bottom-right
        self._position_on_screen()

        # Show with animation
        self.show()
        self._animate_in()

        # Start close timer
        self._should_close = False
        self.close_timer.start(timeout_ms)

    def _markdown_to_html(self, text: str) -> str:
        """Convert basic Markdown to HTML."""
        html = text

        # Error -> Correct pattern: **error** -> **correct** (red -> green)
        # Support both ASCII arrow (->) and Unicode arrow (→)
        # Use [^*]+ instead of .+? to avoid issues with greedy matching
        html = re.sub(
            r'\*\*([^*]+)\*\*\s*(?:->|→|=>|–>|—>)\s*\*\*([^*]+)\*\*',
            rf'<b style="color: {Styles.DELETE_RED};">\1</b> → '
            rf'<b style="color: {Styles.SUCCESS};">\2</b>',
            html
        )

        # Also support pattern without bold: "error" -> "correct" or 'error' -> 'correct'
        html = re.sub(
            r'"([^"]+)"\s*(?:->|→|=>|–>|—>)\s*"([^"]+)"',
            rf'<b style="color: {Styles.DELETE_RED};">\1</b> → '
            rf'<b style="color: {Styles.SUCCESS};">\2</b>',
            html
        )
        html = re.sub(
            r"'([^']+)'\s*(?:->|→|=>|–>|—>)\s*'([^']+)'",
            rf'<b style="color: {Styles.DELETE_RED};">\1</b> → '
            rf'<b style="color: {Styles.SUCCESS};">\2</b>',
            html
        )

        # Support pattern: error → correct (no bold/quotes, but with arrow)
        # Matches single words or phrases with spaces (e.g., "что бы -> чтобы")
        html = re.sub(
            r'(?<![*"\'])([а-яА-Яa-zA-Z]+(?:\s+[а-яА-Яa-zA-Z]+)*)\s*(?:->|→|=>|–>|—>)\s*([а-яА-Яa-zA-Z]+(?:\s+[а-яА-Яa-zA-Z]+)*)(?![*"\'])',
            rf'<b style="color: {Styles.DELETE_RED};">\1</b> → '
            rf'<b style="color: {Styles.SUCCESS};">\2</b>',
            html
        )

        # Regular Bold: **text** (for remaining bold that wasn't error->correct)
        html = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', html)

        # Italic: *text*
        html = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'<i>\1</i>', html)

        # Code: `text`
        html = re.sub(
            r'`(.+?)`',
            r'<code style="background-color: #333; padding: 2px 5px; '
            r'border-radius: 3px; font-family: Consolas, monospace;">\1</code>',
            html
        )

        # Headers: ### text
        html = re.sub(
            r'^### (.+)$',
            rf'<h4 style="color: {Styles.ACCENT}; margin: 8px 0 4px 0; '
            rf'font-size: 13px;">\1</h4>',
            html,
            flags=re.MULTILINE
        )
        html = re.sub(
            r'^## (.+)$',
            rf'<h3 style="color: {Styles.ACCENT}; margin: 10px 0 5px 0; '
            rf'font-size: 14px;">\1</h3>',
            html,
            flags=re.MULTILINE
        )

        # Bullet points: - text or * text (at start of line)
        html = re.sub(
            r'^[\-\*] (.+)$',
            r'<div style="margin-left: 10px; margin-bottom: 3px;">'
            r'<span style="color: #888;">•</span> \1</div>',
            html,
            flags=re.MULTILINE
        )

        # Numbered lists: 1. text
        html = re.sub(
            r'^(\d+)\. (.+)$',
            r'<div style="margin-left: 10px; margin-bottom: 3px;">'
            r'<span style="color: #888;">\1.</span> \2</div>',
            html,
            flags=re.MULTILINE
        )

        # Line breaks (but not after block elements)
        html = re.sub(r'(?<!>)\n(?!<)', '<br>', html)

        return (
            f'<div style="font-family: Segoe UI, sans-serif; '
            f'color: {Styles.TEXT}; line-height: 1.5;">{html}</div>'
        )

    def _position_on_screen(self) -> None:
        """Position toast at bottom-right of screen."""
        desktop = QDesktopWidget()
        screen_rect = desktop.availableGeometry(desktop.primaryScreen())

        margin = 15
        x = screen_rect.right() - self.width() - margin
        y = screen_rect.bottom() - self.height() - margin

        self.move(x, y)

    def _animate_in(self) -> None:
        """Animate toast appearing."""
        self.setWindowOpacity(0)

        self._animation = QPropertyAnimation(self, b"windowOpacity")
        self._animation.setDuration(200)
        self._animation.setStartValue(0)
        self._animation.setEndValue(1)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.start()

    def _animate_out(self) -> None:
        """Animate toast disappearing."""
        self._animation = QPropertyAnimation(self, b"windowOpacity")
        self._animation.setDuration(200)
        self._animation.setStartValue(1)
        self._animation.setEndValue(0)
        self._animation.setEasingCurve(QEasingCurve.InCubic)
        self._animation.finished.connect(self.hide)
        self._animation.start()

    def _on_close_timer(self) -> None:
        """Handle close timer timeout."""
        if self._is_hovered:
            self._should_close = True
        else:
            self._animate_out()

    def enterEvent(self, event) -> None:
        """Mouse entered widget."""
        self._is_hovered = True
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        """Mouse left widget."""
        self._is_hovered = False
        if self._should_close:
            self._animate_out()
        super().leaveEvent(event)
