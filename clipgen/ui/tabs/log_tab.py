"""Log tab - displays application logs."""

import re
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser, QPushButton,
    QScrollArea
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QTextCursor

from ..styles import Styles


class LogTab(QWidget):
    """Tab for displaying application logs."""

    def __init__(self, lang: dict, parent=None):
        super().__init__(parent)
        self.lang = lang
        self.config = None  # Will be set by main window
        self._setup_ui()

    def set_config(self, config: dict) -> None:
        """Set config reference for hotkey detection."""
        self.config = config

    def _setup_ui(self) -> None:
        """Set up the tab UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Log area
        self.log_area = QTextBrowser()
        self.log_area.setStyleSheet("""
            QTextBrowser {
                background-color: #252525;
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                padding: 15px;
                line-height: 1.5;
                font-family: 'Consolas', 'Courier New', monospace;
                selection-background-color: #A3BFFA;
                selection-color: #1e1e1e;
            }
        """)
        self.log_area.setOpenExternalLinks(True)
        self.log_area.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard | Qt.LinksAccessibleByMouse
        )
        self.log_area.setCursorWidth(2)
        layout.addWidget(self.log_area, 1)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        logs_lang = self.lang.get("logs", {})

        # Clear logs button
        self.clear_button = QPushButton(logs_lang.get("clear_logs", "Clear logs"))
        self.clear_button.setToolTip(self.lang.get("tooltips", {}).get("clear_logs", "Clear all logs"))
        self.clear_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 12px;
                max-width: 150px;
            }
            QPushButton:hover {
                background-color: #444444;
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
            }
        """)
        self.clear_button.setMaximumWidth(150)
        self.clear_button.clicked.connect(self.clear_logs)
        button_layout.addWidget(self.clear_button)

        # Check updates button
        self.check_updates_button = QPushButton(
            logs_lang.get("check_updates", "Check for updates")
        )
        self.check_updates_button.setToolTip(
            self.lang.get("tooltips", {}).get("check_updates", "Check for new versions on GitHub")
        )
        self.check_updates_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 12px;
                max-width: 180px;
            }
            QPushButton:hover {
                background-color: #444444;
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
            }
        """)
        self.check_updates_button.setMaximumWidth(180)
        button_layout.addWidget(self.check_updates_button)

        # Stop button (gray by default, red on hover like original)
        self.stop_button = QPushButton(logs_lang.get("stop_task", "Stop"))
        self.stop_button.setToolTip(self.lang.get("tooltips", {}).get("stop_task", "Stop current task"))
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 12px;
                max-width: 150px;
            }
            QPushButton:hover {
                background-color: #c82333;
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: #a01c29;
            }
        """)
        self.stop_button.setMaximumWidth(150)
        button_layout.addWidget(self.stop_button)

        # Instructions button
        self.instructions_button = QPushButton(
            logs_lang.get("instructions", "Instructions")
        )
        self.instructions_button.setToolTip(self.lang.get("tooltips", {}).get("instructions", "Show instructions"))
        self.instructions_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 12px;
                max-width: 150px;
            }
            QPushButton:hover {
                background-color: #444444;
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
            }
        """)
        self.instructions_button.setMaximumWidth(150)
        button_layout.addWidget(self.instructions_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

    def clear_logs(self) -> None:
        """Clear the log area."""
        self.log_area.clear()

    def append_log(self, message: str, color: str = "#FFFFFF") -> None:
        """Append a log message with smart formatting.

        Args:
            message: Log message
            color: Text color (hex)
        """
        self.log_area.moveCursor(QTextCursor.End)

        logs_lang = self.lang.get("logs", {})
        errors_lang = self.lang.get("errors", {})

        execution_time_key = logs_lang.get("execution_time", "Executed in").split()[0]
        app_started_msg = logs_lang.get("app_started", "ClipGen started")
        empty_clipboard_msg = errors_lang.get("empty_clipboard", "Clipboard is empty")

        # Check if this is an action header (combination: name - timestamp)
        is_action_header = False
        if self.config:
            for hotkey in self.config.get("hotkeys", []):
                combo = hotkey.get("combination", "")
                name = hotkey.get("name", "")
                if f"{combo}: {name}" in message:
                    is_action_header = True
                    break

        # Determine log type for formatting
        if execution_time_key in message:
            # Execution time message - gray with indent
            self.log_area.setTextColor(QColor("#888888"))
            self.log_area.append(f"    {message}")

        elif is_action_header:
            # Action header - add separator before
            self.log_area.setTextColor(QColor(color))

            cursor = self.log_area.textCursor()
            if not cursor.atStart():
                self.log_area.setTextColor(QColor("#888888"))
                self.log_area.append("\n" + "─" * 40 + "\n")

            self.log_area.setTextColor(QColor(color))
            self.log_area.append(message)

        elif "Error:" in message or "Ошибка:" in message:
            # Error message - red with indent
            self.log_area.setTextColor(QColor("#FF5555"))
            self.log_area.append(f"\n    ✗ {message}")

        elif empty_clipboard_msg in message:
            # Warning - yellow
            self.log_area.setTextColor(QColor("#FFDD55"))
            self.log_area.append(f"⚠️ {message}")

        elif app_started_msg in message:
            # App started - just show the message
            self.log_area.setTextColor(QColor(color))
            self.log_area.append(message)

        else:
            # Processing result or other message
            self.log_area.setTextColor(QColor(color))

            # If it looks like AI response, add indentation
            if color != "#A3BFFA" and color != "#00FF00":  # Not welcome/system message
                self.log_area.append(f"    {message}")
            else:
                self.log_area.append(message)

        # Scroll to bottom
        self.log_area.ensureCursorVisible()

    def update_language(self, lang: dict) -> None:
        """Update UI text with new language."""
        self.lang = lang
        logs_lang = lang.get("logs", {})

        self.clear_button.setText(logs_lang.get("clear_logs", "Clear logs"))
        self.check_updates_button.setText(
            logs_lang.get("check_updates", "Check for updates")
        )
        self.stop_button.setText(logs_lang.get("stop_task", "Stop"))
        self.instructions_button.setText(
            logs_lang.get("instructions", "Instructions")
        )

    def append_explanation_log(self, text: str, hotkey_color: str = "#FFFFFF") -> None:
        """Append learning mode explanation with colored formatting.

        Args:
            text: Explanation text from AI
            hotkey_color: Color of the hotkey for base text
        """
        if not text or not text.strip():
            return

        self.log_area.moveCursor(QTextCursor.End)

        # Add empty line before explanation block
        self.log_area.append("")

        # Add separator before explanation
        self.log_area.setTextColor(QColor("#888888"))
        self.log_area.append("    ┌─ " + self.lang.get("logs", {}).get(
            "learning_explanation", "Explanation:"
        ))

        # Process text line by line
        lines = text.strip().split('\n')

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Check for error -> correct pattern
            # **error** -> **correct** or "error" -> "correct"
            pattern_bold = re.search(
                r'\*\*([^*]+)\*\*\s*(?:->|→|=>|–>|—>)\s*\*\*([^*]+)\*\*',
                stripped
            )
            pattern_quotes = re.search(
                r'["\']([^"\']+)["\']\s*(?:->|→|=>|–>|—>)\s*["\']([^"\']+)["\']',
                stripped
            )
            pattern_plain = re.search(
                r'^([а-яА-Яa-zA-Z]+(?:\s+[а-яА-Яa-zA-Z]+)*)\s*(?:->|→|=>|–>|—>)\s*([а-яА-Яa-zA-Z]+(?:\s+[а-яА-Яa-zA-Z]+)*)$',
                stripped
            )

            if pattern_bold or pattern_quotes or pattern_plain:
                pattern = pattern_bold or pattern_quotes or pattern_plain
                error_word = pattern.group(1)
                correct_word = pattern.group(2)

                # Build HTML for this line
                # Replace the matched pattern with colored version
                html_line = stripped
                if pattern_bold:
                    html_line = re.sub(
                        r'\*\*([^*]+)\*\*\s*(?:->|→|=>|–>|—>)\s*\*\*([^*]+)\*\*',
                        f'<span style="color: {Styles.DELETE_RED}; font-weight: bold;">\\1</span>'
                        f' → <span style="color: {Styles.SUCCESS}; font-weight: bold;">\\2</span>',
                        html_line
                    )
                elif pattern_quotes:
                    html_line = re.sub(
                        r'["\']([^"\']+)["\']\s*(?:->|→|=>|–>|—>)\s*["\']([^"\']+)["\']',
                        f'<span style="color: {Styles.DELETE_RED}; font-weight: bold;">\\1</span>'
                        f' → <span style="color: {Styles.SUCCESS}; font-weight: bold;">\\2</span>',
                        html_line
                    )
                elif pattern_plain:
                    html_line = re.sub(
                        r'^([а-яА-Яa-zA-Z]+(?:\s+[а-яА-Яa-zA-Z]+)*)\s*(?:->|→|=>|–>|—>)\s*([а-яА-Яa-zA-Z]+(?:\s+[а-яА-Яa-zA-Z]+)*)$',
                        f'<span style="color: {Styles.DELETE_RED}; font-weight: bold;">\\1</span>'
                        f' → <span style="color: {Styles.SUCCESS}; font-weight: bold;">\\2</span>',
                        html_line
                    )

                # Remove remaining markdown bold
                html_line = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', html_line)
                # Convert *text* to italic
                html_line = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', html_line)

                cursor = self.log_area.textCursor()
                cursor.movePosition(QTextCursor.End)
                cursor.insertHtml(
                    f'<div style="color: {hotkey_color}; margin-left: 20px;">    │ {html_line}</div>'
                )
                self.log_area.append("")  # New line

            elif stripped.startswith('*') and not stripped.startswith('**'):
                # Italic rule explanation: *Rule: ...*
                text_content = stripped.strip('*')
                self.log_area.setTextColor(QColor("#AAAAAA"))
                self.log_area.append(f"    │   {text_content}")

            else:
                # Regular text in hotkey color
                # Remove markdown formatting
                clean_line = re.sub(r'\*\*([^*]+)\*\*', r'\1', stripped)
                clean_line = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'\1', clean_line)
                self.log_area.setTextColor(QColor(hotkey_color))
                self.log_area.append(f"    │ {clean_line}")

        # End separator
        self.log_area.setTextColor(QColor("#888888"))
        self.log_area.append("    └─────")

        # Scroll to bottom
        self.log_area.ensureCursorVisible()
