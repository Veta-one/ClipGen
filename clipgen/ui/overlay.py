"""Top-right status overlay for voice transcription.

Mirrors the SuperWhisper "● RECORDING" widget. The overlay is small,
frameless, click-through-able (close to it) and stays on top while the
user is recording or the model is loading.
"""

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QDesktopWidget,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QWidget,
)


STATE_HIDDEN = "hidden"
STATE_LOADING = "loading"
STATE_RECORDING = "recording"
STATE_TRANSCRIBING = "transcribing"
STATE_READY = "ready"
STATE_ERROR = "error"


COLORS = {
    STATE_LOADING: ("#5085D0", "#FFFFFF"),       # blue, white text
    STATE_RECORDING: ("#DC3545", "#FFFFFF"),     # red, white text
    STATE_TRANSCRIBING: ("#FFC107", "#1e1e1e"),  # yellow, dark text
    STATE_READY: ("#28A745", "#FFFFFF"),         # green, white text
    STATE_ERROR: ("#FF5F57", "#FFFFFF"),         # red, white
}


class TranscriptionOverlay(QWidget):
    """Frameless top-right always-on-top status pill."""

    def __init__(self, lang: dict, parent=None):
        super().__init__(
            parent,
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.lang = lang
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._state = STATE_HIDDEN
        self._setup_ui()

        # Timer for auto-hide on terminal states (ready/error).
        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self.hide)

        # Timer driving the recording elapsed counter.
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(100)
        self._tick_timer.timeout.connect(self._on_tick)
        self._tick_started_at = None

    # ------------------------------------------------------------------ UI

    def _setup_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._pill = QWidget(self)
        self._pill_layout = QHBoxLayout(self._pill)
        self._pill_layout.setContentsMargins(14, 8, 14, 8)
        self._pill_layout.setSpacing(8)

        self._dot = QLabel("●")
        self._dot.setStyleSheet("font-size: 12px; color: #FFFFFF;")
        self._pill_layout.addWidget(self._dot)

        self._label = QLabel("")
        self._label.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #FFFFFF;"
        )
        self._pill_layout.addWidget(self._label)

        self._timer_label = QLabel("")
        self._timer_label.setStyleSheet(
            "font-size: 11px; color: #FFFFFF;"
        )
        self._pill_layout.addWidget(self._timer_label)

        outer.addWidget(self._pill)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 4)
        self._pill.setGraphicsEffect(shadow)

        self.adjustSize()

    # ------------------------------------------------------------------ helpers

    def update_lang(self, lang: dict) -> None:
        self.lang = lang
        # Refresh visible label text if state is active.
        if self._state != STATE_HIDDEN:
            self.set_state(self._state)

    def _overlay_text(self, state: str) -> str:
        section = self.lang.get("overlay", {})
        mapping = {
            STATE_LOADING: section.get("loading_model", "Loading model..."),
            STATE_RECORDING: section.get("recording", "RECORDING"),
            STATE_TRANSCRIBING: section.get("transcribing", "TRANSCRIBING"),
            STATE_READY: section.get("ready", "Ready"),
            STATE_ERROR: section.get("error", "Error"),
        }
        return mapping.get(state, "")

    def _apply_pill_style(self, bg: str, fg: str) -> None:
        self._pill.setStyleSheet(
            f"""
            QWidget {{
                background-color: {bg};
                border-radius: 14px;
            }}
            """
        )
        self._dot.setStyleSheet(f"font-size: 12px; color: {fg};")
        self._label.setStyleSheet(
            f"font-size: 12px; font-weight: bold; color: {fg};"
        )
        self._timer_label.setStyleSheet(f"font-size: 11px; color: {fg};")

    def _position_top_right(self) -> None:
        desktop = QDesktopWidget()
        screen = desktop.availableGeometry(desktop.primaryScreen())
        margin = 16
        self.adjustSize()
        x = screen.right() - self.width() - margin
        y = screen.top() + margin
        self.move(x, y)

    def _on_tick(self) -> None:
        if self._tick_started_at is None:
            return
        from time import time as now
        elapsed = now() - self._tick_started_at
        self._timer_label.setText(f"{elapsed:.1f}s")

    # ------------------------------------------------------------------ public API

    def set_state(self, state: str) -> None:
        """Apply state to the overlay and show/hide as needed."""
        self._auto_hide_timer.stop()
        self._tick_timer.stop()
        self._tick_started_at = None
        self._timer_label.setText("")

        if state == STATE_HIDDEN:
            self._state = STATE_HIDDEN
            self.hide()
            return

        bg, fg = COLORS.get(state, ("#333333", "#FFFFFF"))
        self._apply_pill_style(bg, fg)
        self._label.setText(self._overlay_text(state))
        self._state = state

        # Reset and start tick where it makes sense.
        if state in (STATE_RECORDING, STATE_TRANSCRIBING):
            from time import time as now
            self._tick_started_at = now()
            self._on_tick()
            self._tick_timer.start()

        # Auto-hide for terminal/quick states.
        if state == STATE_READY:
            self._auto_hide_timer.start(1500)
        elif state == STATE_ERROR:
            self._auto_hide_timer.start(3000)

        self._position_top_right()
        self.show()
        self.raise_()
