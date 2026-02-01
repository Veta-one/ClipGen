"""Clipboard operations - copy, paste, image capture."""

import time
import base64
import io
import threading
from typing import Optional, Tuple, Union

import pyperclip
from PIL import ImageGrab
import win32api
import win32con


class ClipboardHandler:
    """Handles clipboard operations with keyboard simulation."""

    def __init__(self, on_pasting_change=None):
        """Initialize clipboard handler.

        Args:
            on_pasting_change: Callback function(is_pasting: bool) to notify
                               when pasting state changes (for hotkey listener sync)
        """
        self.pasting_lock = threading.Lock()
        self.is_pasting = False
        self._on_pasting_change = on_pasting_change

    def _set_pasting(self, value: bool) -> None:
        """Set pasting state and notify listener."""
        with self.pasting_lock:
            self.is_pasting = value
        if self._on_pasting_change:
            self._on_pasting_change(value)

    def simulate_copy(self) -> None:
        """Simulate Ctrl+C keypress."""
        self._set_pasting(True)

        try:
            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            win32api.keybd_event(ord('C'), 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(ord('C'), 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.1)
        finally:
            self._set_pasting(False)

    def simulate_paste(self) -> None:
        """Simulate Ctrl+V keypress."""
        self._set_pasting(True)

        try:
            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            win32api.keybd_event(ord('V'), 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(ord('V'), 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.1)
        finally:
            self._set_pasting(False)

    def get_text(self) -> str:
        """Get text from clipboard."""
        try:
            return pyperclip.paste()
        except Exception:
            return ""

    def set_text(self, text: str) -> None:
        """Set text to clipboard."""
        pyperclip.copy(text)

    def get_image_as_base64(self) -> Optional[str]:
        """Capture image from clipboard and return as base64."""
        try:
            img = ImageGrab.grabclipboard()
            if img is None:
                return None

            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
        except Exception:
            return None

    def has_image(self) -> bool:
        """Check if clipboard contains an image."""
        try:
            img = ImageGrab.grabclipboard()
            return img is not None
        except Exception:
            return False

    def get_content(self) -> Tuple[str, bool]:
        """Get clipboard content.

        Returns:
            Tuple of (content, is_image) where content is text or base64 image.
        """
        # Check for image first
        image_b64 = self.get_image_as_base64()
        if image_b64:
            return image_b64, True

        # Fall back to text
        text = self.get_text()
        return text, False
