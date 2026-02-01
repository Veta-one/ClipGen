"""Help tab - displays instructions and donation info."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser, QLineEdit,
    QPushButton, QLabel
)
from PyQt5.QtCore import Qt, QTimer
import pyperclip


class HelpTab(QWidget):
    """Tab for help/instructions and donation info."""

    DONATION_WALLET = "TYgsAvTkkrRqArgo3Q5BYMghbYn6DViVqQ"

    def __init__(self, lang: dict, parent=None):
        super().__init__(parent)
        self.lang = lang
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the tab UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # Help content browser
        self.help_browser = QTextBrowser()
        self.help_browser.setOpenExternalLinks(True)
        self.help_browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.help_browser.setStyleSheet("""
            QTextBrowser {
                background-color: #252525;
                border-radius: 10px;
                padding: 15px;
                border: none;
                color: #FFFFFF;
                font-size: 13px;
                line-height: 1.5;
            }
        """)
        self._update_help_content()
        layout.addWidget(self.help_browser, 1)

        # Donation section (footer, transparent background)
        donate_widget = QWidget()
        donate_widget.setStyleSheet("background-color: transparent;")
        donate_layout = QHBoxLayout(donate_widget)
        donate_layout.setContentsMargins(0, 0, 0, 0)
        donate_layout.setSpacing(10)

        # Label
        self.usdt_label = QLabel("USDT (TRC-20):")
        self.usdt_label.setStyleSheet("background-color: transparent;")
        donate_layout.addWidget(self.usdt_label)

        # Wallet input
        self.wallet_input = QLineEdit(self.DONATION_WALLET)
        self.wallet_input.setReadOnly(True)
        self.wallet_input.setStyleSheet("""
            QLineEdit {
                background-color: #2a2a2a;
                color: #FFFFFF;
                border: 1px solid #444444;
                border-radius: 8px;
                padding: 8px;
                font-family: 'Consolas', monospace;
            }
        """)
        donate_layout.addWidget(self.wallet_input)

        # Copy button (green)
        self.original_copy_style = """
            QPushButton {
                background-color: #3D8948;
                border-radius: 8px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #2A6C34;
            }
        """

        help_lang = self.lang.get("help", {})
        self.copy_button = QPushButton(help_lang.get("copy_button", "Copy"))
        self.copy_button.setToolTip(self.lang.get("tooltips", {}).get("copy_wallet", "Copy wallet address"))
        self.copy_button.setFixedWidth(110)
        self.copy_button.setStyleSheet(self.original_copy_style)
        self.copy_button.clicked.connect(self._copy_wallet)
        donate_layout.addWidget(self.copy_button)

        layout.addWidget(donate_widget)

    def _build_help_html(self) -> str:
        """Build help HTML from language file."""
        help_lang = self.lang.get("help", {})

        # Build list items
        def build_list(items):
            if not items:
                return ""
            html = "<ul style='margin-left: 20px;'>"
            for item in items:
                html += f"<li>{item}</li>"
            html += "</ul>"
            return html

        html = f"""
        <h2 style='color: #A3BFFA; font-size: 20px;'>{help_lang.get("welcome_title", "Welcome to ClipGen!")}</h2>
        <p>{help_lang.get("welcome_text", "This is your personal AI assistant.")}</p>

        <hr style='border: 1px solid #333;'>

        <h2 style='color: #A3BFFA; font-size: 16px;'>{help_lang.get("how_it_works_title", "How It Works")}</h2>

        <h3 style='color: #FFFFFF; font-size: 14px;'>{help_lang.get("step1_title", "Step 1: Get an API Key")}</h3>
        <p>{help_lang.get("step1_text", "")}</p>
        {build_list(help_lang.get("step1_list", []))}

        <h3 style='color: #FFFFFF; font-size: 14px;'>{help_lang.get("step2_title", "Step 2: Select and Press")}</h3>
        <p>{help_lang.get("step2_text", "")}</p>

        <h3 style='color: #FFFFFF; font-size: 14px;'>{help_lang.get("step3_title", "Step 3: Watch the Tray Icon")}</h3>
        <p>{help_lang.get("step3_text", "")}</p>

        <hr style='border: 1px solid #333;'>

        <h2 style='color: #A3BFFA; font-size: 16px;'>{help_lang.get("personalization_title", "Personalization")}</h2>
        <p>{help_lang.get("personalization_text", "")}</p>
        {build_list(help_lang.get("personalization_list", []))}

        <hr style='border: 1px solid #333;'>

        <h2 style='color: #A3BFFA; font-size: 16px;'>{help_lang.get("feedback_title", "Feedback")}</h2>
        <p>{help_lang.get("feedback_text", "")}</p>
        <p>{help_lang.get("website_text", "")}</p>

        <hr style='border: 1px solid #333;'>

        <h2 style='color: #FAF089; font-size: 16px;'>{help_lang.get("support_title", "Support the Project")}</h2>
        <p style='color: #FBD38D;'>{help_lang.get("support_text", "")}</p>
        """

        return html

    def _update_help_content(self) -> None:
        """Update help browser content."""
        self.help_browser.setHtml(self._build_help_html())

    def _copy_wallet(self) -> None:
        """Copy wallet address to clipboard with visual feedback."""
        pyperclip.copy(self.DONATION_WALLET)

        help_lang = self.lang.get("help", {})

        # Change button to "Copied" state
        self.copy_button.setText(help_lang.get("copied", "Copied!"))
        self.copy_button.setStyleSheet("""
            QPushButton {
                background-color: #28A745;
                border-radius: 8px;
                padding: 8px;
            }
        """)

        # Reset after 1 second
        QTimer.singleShot(1000, self._reset_copy_button)

    def _reset_copy_button(self) -> None:
        """Reset copy button to original state."""
        help_lang = self.lang.get("help", {})
        self.copy_button.setText(help_lang.get("copy_button", "Copy"))
        self.copy_button.setStyleSheet(self.original_copy_style)

    def update_language(self, lang: dict) -> None:
        """Update UI text with new language."""
        self.lang = lang
        self._update_help_content()

        help_lang = lang.get("help", {})
        self.copy_button.setText(help_lang.get("copy_button", "Copy"))
