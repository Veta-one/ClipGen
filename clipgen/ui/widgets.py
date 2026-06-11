"""Reusable UI widgets."""

from PyQt5.QtWidgets import QComboBox, QPushButton
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter


class MouseOnlyPushButton(QPushButton):
    """A QPushButton that activates ONLY on real mouse interaction.

    Why: certain heavy actions (like loading the Whisper model into VRAM)
    must never run from a stray keyboard event. We have observed that on
    some Windows + Qt 5.15 combinations, an Enter keystroke from the
    terminal that launched the application can travel through the focus
    chain and activate a button even with Qt.NoFocus and AutoDefault=False.
    Subclassing here is the only reliable way to suppress all keyboard
    activation.
    """

    def keyPressEvent(self, event):
        event.ignore()

    def keyReleaseEvent(self, event):
        event.ignore()


class StyledComboBox(QComboBox):
    """ComboBox with visible dropdown indicator (bullet)."""

    DEFAULT_STYLE = """
        QComboBox {
            padding-left: 10px;
            padding-right: 22px;
            background-color: #2a2a2a;
            color: white;
            border: 1px solid #444444;
            border-radius: 8px;
            padding-top: 5px;
            padding-bottom: 5px;
        }
        QComboBox:hover {
            border: 1px solid #555555;
        }
        QComboBox:disabled {
            background-color: #1a1a1a;
            color: #666666;
            border: 1px solid #333333;
        }
        QComboBox::drop-down {
            border: none;
            background: transparent;
        }
        QComboBox::down-arrow {
            image: none;
        }
        QComboBox QAbstractItemView {
            background-color: #2a2a2a;
            color: white;
            selection-background-color: #444444;
            border: 1px solid #444444;
            padding: 5px;
        }
        QComboBox QAbstractItemView::item {
            padding: 5px 10px;
            min-height: 20px;
        }
        QComboBox QAbstractItemView::item:hover {
            background-color: #444444;
        }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(self.DEFAULT_STYLE)

    def wheelEvent(self, event):
        """Do not change the selected value from page scrolling.

        Qt's default QComboBox behavior changes the current item when the
        mouse wheel is used over a closed combo box. In settings screens this
        causes accidental config changes while the user is just scrolling the
        page. Ignore the wheel here so the parent scroll area can handle it.
        """
        if not self.view().isVisible():
            event.ignore()
            return
        super().wheelEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        # Draw bullet indicator centered in the right area
        painter = QPainter(self)
        painter.setPen(self.palette().text().color())
        rect = self.rect()
        # Draw "•" centered in a 20px wide area on the right
        indicator_width = 20
        painter.drawText(
            rect.right() - indicator_width,
            rect.top(),
            indicator_width,
            rect.height(),
            Qt.AlignHCenter | Qt.AlignVCenter,
            "•"
        )
