"""Centralized UI styles for ClipGen."""


class Styles:
    """CSS styles for PyQt5 widgets."""

    # Colors
    BACKGROUND = "#1e1e1e"
    CARD_BG = "#252525"
    BUTTON_BG = "#333333"
    BUTTON_HOVER = "#404040"
    BUTTON_PRESSED = "#2a2a2a"
    BORDER = "#444444"
    TEXT = "#FFFFFF"
    ACCENT = "#A3BFFA"

    # Status colors
    SUCCESS = "#28A745"
    SUCCESS_HOVER = "#218838"
    ERROR = "#DC3545"
    ERROR_HOVER = "#C82333"
    WARNING = "#FFC107"
    WARNING_HOVER = "#E0A800"
    NOT_TESTED = "#6c757d"
    NOT_TESTED_HOVER = "#5a6268"

    # Action colors
    ADD_GREEN = "#3D8948"
    ADD_GREEN_HOVER = "#2A6C34"
    DELETE_RED = "#FF5F57"
    DELETE_RED_HOVER = "#FF3B30"
    TOGGLE_ON = "#3D8948"
    TOGGLE_OFF = "#676664"
    AUTO_SWITCH_BLUE = "#5085D0"

    @staticmethod
    def global_app_style() -> str:
        """Global application style (for QApplication)."""
        return """
            QToolTip {
                background-color: #2b2b2b;
                color: #ffffff;
                border: 1px solid #3c3c3c;
                border-radius: 5px;
                padding: 5px;
                font-size: 12px;
            }
        """

    @staticmethod
    def main_window() -> str:
        """Main window style."""
        return f"""
            QStackedWidget {{
                background-color: {Styles.BACKGROUND};
                border: none;
                border-radius: 10px;
            }}
            QWidget {{
                background-color: {Styles.BACKGROUND};
                color: {Styles.TEXT};
            }}
            QFrame {{
                background-color: {Styles.CARD_BG};
            }}
            QPushButton {{
                background-color: {Styles.BUTTON_BG};
                border-radius: 10px;
                padding: 8px;
                color: {Styles.TEXT};
            }}
            QPushButton:hover {{
                background-color: {Styles.BUTTON_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {Styles.BUTTON_PRESSED};
            }}
            QLineEdit, QTextEdit {{
                background-color: #2e2e2e;
                color: {Styles.TEXT};
                border: 1px solid {Styles.BORDER};
                border-radius: 10px;
                padding: 5px;
            }}
            QLineEdit:focus, QTextEdit:focus {{
                border: 1px solid {Styles.ACCENT};
            }}
            QLabel {{
                color: {Styles.TEXT};
                background-color: transparent;
            }}
            QScrollBar:vertical, QScrollBar:horizontal {{
                background: transparent;
                width: 8px;
                height: 8px;
                margin: 0px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
                background: #555555;
                min-height: 20px;
                min-width: 20px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
                background: #666666;
            }}
            QScrollBar::add-line, QScrollBar::sub-line {{
                background: none;
                height: 0px;
                width: 0px;
            }}
            QScrollBar::add-page, QScrollBar::sub-page {{
                background: none;
            }}
            QTextBrowser {{
                background-color: {Styles.CARD_BG};
                color: {Styles.TEXT};
                border: none;
                border-radius: 10px;
                padding: 10px;
                selection-background-color: {Styles.ACCENT};
                selection-color: {Styles.BACKGROUND};
            }}
            QScrollArea, QScrollArea * {{
                background-color: {Styles.BACKGROUND};
            }}
            QComboBox {{
                background-color: {Styles.BUTTON_BG};
                border-radius: 8px;
                padding: 5px 25px 5px 10px;
                color: white;
                border: 1px solid {Styles.BORDER};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 25px;
                border-left: 1px solid {Styles.BORDER};
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
                background-color: {Styles.BUTTON_BG};
            }}
            QComboBox::drop-down:hover {{
                background-color: {Styles.BUTTON_HOVER};
            }}
            QComboBox::down-arrow {{
                width: 12px;
                height: 12px;
                image: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: #2e2e2e;
                color: {Styles.TEXT};
                selection-background-color: {Styles.BUTTON_HOVER};
                border: 1px solid {Styles.BORDER};
            }}
        """

    @staticmethod
    def button() -> str:
        """Standard button style."""
        return f"""
            QPushButton {{
                background-color: {Styles.BUTTON_BG};
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {Styles.BUTTON_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {Styles.BUTTON_PRESSED};
            }}
        """

    @staticmethod
    def mini_button(color: str, hover_color: str) -> str:
        """18x18 circular mini button."""
        return f"""
            QPushButton {{
                background-color: {color};
                color: {Styles.TEXT};
                border-radius: 9px;
                font-weight: bold;
                font-size: 10px;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
        """

    @staticmethod
    def add_button() -> str:
        """Green add button."""
        return Styles.mini_button(Styles.ADD_GREEN, Styles.ADD_GREEN_HOVER)

    @staticmethod
    def delete_button() -> str:
        """Red delete button."""
        return Styles.mini_button(Styles.DELETE_RED, Styles.DELETE_RED_HOVER)

    @staticmethod
    def test_button(status: str) -> str:
        """Test button based on status."""
        colors = {
            "success": (Styles.SUCCESS, Styles.SUCCESS_HOVER),
            "error": (Styles.ERROR, Styles.ERROR_HOVER),
            "testing": (Styles.WARNING, Styles.WARNING_HOVER),
            "not_tested": (Styles.NOT_TESTED, Styles.NOT_TESTED_HOVER)
        }
        color, hover = colors.get(status, (Styles.NOT_TESTED, Styles.NOT_TESTED_HOVER))
        return Styles.mini_button(color, hover)

    @staticmethod
    def toggle_button(active: bool) -> str:
        """Toggle button on/off state."""
        if active:
            return Styles.mini_button(Styles.TOGGLE_ON, Styles.ADD_GREEN_HOVER)
        else:
            return f"""
                QPushButton {{
                    background-color: {Styles.TOGGLE_OFF};
                    color: {Styles.TEXT};
                    border-radius: 9px;
                    font-weight: bold;
                    font-size: 10px;
                }}
                QPushButton:hover {{
                    background-color: #DDDDDD;
                    color: #000000;
                }}
            """

    @staticmethod
    def auto_switch_button(active: bool) -> str:
        """Auto-switch toggle button."""
        color = Styles.AUTO_SWITCH_BLUE if active else Styles.TOGGLE_OFF
        return f"""
            QPushButton {{
                background-color: {color};
                color: {Styles.TEXT};
                border-radius: 9px;
                font-weight: bold;
                font-size: 10px;
            }}
            QPushButton:hover {{
                background-color: #DDDDDD;
                color: #000000;
            }}
        """

    @staticmethod
    def input_field() -> str:
        """Text input field."""
        return f"""
            QLineEdit {{
                background-color: #2e2e2e;
                border: 1px solid {Styles.BORDER};
                border-radius: 10px;
                padding: 5px;
                color: {Styles.TEXT};
            }}
            QLineEdit:focus {{
                border: 1px solid {Styles.ACCENT};
            }}
        """

    @staticmethod
    def text_edit() -> str:
        """Multi-line text edit."""
        return f"""
            QTextEdit {{
                background-color: #2e2e2e;
                border: 1px solid {Styles.BORDER};
                border-radius: 10px;
                padding: 5px;
                color: {Styles.TEXT};
            }}
            QTextEdit:focus {{
                border: 1px solid {Styles.ACCENT};
            }}
        """

    @staticmethod
    def card() -> str:
        """Card/frame container."""
        return f"""
            QFrame {{
                background-color: {Styles.CARD_BG};
                border-radius: 15px;
                padding: 10px;
            }}
        """

    @staticmethod
    def scroll_area() -> str:
        """Scroll area with hidden scrollbar."""
        return f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: {Styles.BACKGROUND};
                width: 4px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: #666666;
                border-radius: 2px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """

    @staticmethod
    def text_browser() -> str:
        """Read-only text browser."""
        return f"""
            QTextBrowser {{
                background-color: {Styles.CARD_BG};
                color: {Styles.TEXT};
                border: none;
                border-radius: 10px;
                padding: 15px;
            }}
        """

    @staticmethod
    def combo_box() -> str:
        """Combo box dropdown."""
        return f"""
            QComboBox {{
                background-color: #2e2e2e;
                border: 1px solid {Styles.BORDER};
                border-radius: 8px;
                padding: 5px;
                color: {Styles.TEXT};
            }}
            QComboBox:focus {{
                border: 1px solid {Styles.ACCENT};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: #2e2e2e;
                color: {Styles.TEXT};
                selection-background-color: {Styles.BUTTON_HOVER};
            }}
        """

    @staticmethod
    def radio_button() -> str:
        """Radio button."""
        return f"""
            QRadioButton::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 9px;
            }}
            QRadioButton::indicator:unchecked {{
                background-color: #353535;
            }}
            QRadioButton::indicator:unchecked:hover {{
                background-color: #4f4f4f;
            }}
            QRadioButton::indicator:checked {{
                background-color: qradialgradient(
                    spread:pad, cx:0.5, cy:0.5, radius:0.5,
                    fx:0.5, fy:0.5,
                    stop:0 #FFFFFF, stop:0.5 #FFFFFF, stop:0.51 {Styles.ADD_GREEN}, stop:1 {Styles.ADD_GREEN}
                );
            }}
        """

    @staticmethod
    def nav_button() -> str:
        """Navigation tab button - single stylesheet for all states.

        Use setProperty("active", True/False) with unpolish/polish to switch states.
        """
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {Styles.TEXT};
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 12px;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: {Styles.BUTTON_BG};
            }}
            QPushButton:pressed {{
                background-color: {Styles.BUTTON_PRESSED};
            }}
            QPushButton[active="true"] {{
                background-color: #4A4A4A;
            }}
        """

    @staticmethod
    def key_sequence_edit() -> str:
        """Key sequence input."""
        return f"""
            QKeySequenceEdit {{
                background-color: #2e2e2e;
                border: 1px solid {Styles.BORDER};
                border-radius: 8px;
                padding: 3px;
                color: {Styles.TEXT};
            }}
            QKeySequenceEdit:focus {{
                border: 1px solid {Styles.ACCENT};
            }}
        """

    @staticmethod
    def checkable_button(checked: bool) -> str:
        """Checkable toggle button."""
        if checked:
            return f"""
                QPushButton {{
                    background-color: {Styles.ADD_GREEN};
                    color: {Styles.TEXT};
                    border-radius: 8px;
                    padding: 5px 10px;
                }}
                QPushButton:hover {{
                    background-color: {Styles.ADD_GREEN_HOVER};
                }}
            """
        else:
            return Styles.button()
