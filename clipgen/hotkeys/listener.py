"""Global hotkey listener using pynput."""

import logging
import threading
from queue import Queue
from typing import Dict, Any, List, Set

from pynput import keyboard as pkb

logger = logging.getLogger('ClipGen')


class HotkeyListener:
    """Listens for global hotkeys and dispatches events to queue."""

    def __init__(self, config: Dict[str, Any], event_queue: Queue):
        """Initialize listener.

        Args:
            config: Application config with hotkeys
            event_queue: Queue to put hotkey events
        """
        self.config = config
        self.queue = event_queue

        # Key state tracking
        self.key_states: Dict[str, bool] = {
            "ctrl": False,
            "alt": False,
            "shift": False,
            "meta": False
        }
        self.key_states_lock = threading.Lock()

        # Pasting flag (to ignore hotkeys during paste)
        self.is_pasting = False
        self.pasting_lock = threading.Lock()

        # Stop signal
        self.stop_event = threading.Event()
        self._listener_thread: threading.Thread = None

    def _get_key_name(self, key) -> str:
        """Convert pynput key to standardized string."""
        if isinstance(key, pkb.KeyCode):
            return key.char.lower() if key.char else None
        elif isinstance(key, pkb.Key):
            name = key.name.lower()
            # Normalize: 'ctrl_l' -> 'ctrl', 'win_r' -> 'meta'
            if name.endswith(('_l', '_r')):
                name = name[:-2]
            if name == 'alt_gr':
                name = 'alt'
            if name in ['cmd', 'win']:
                name = 'meta'
            return name
        return None

    def _on_press(self, key) -> None:
        """Handle key press."""
        with self.pasting_lock:
            if self.is_pasting:
                return

        key_name = self._get_key_name(key)
        if not key_name:
            return

        with self.key_states_lock:
            # Modifier key - update state and exit
            if key_name in self.key_states:
                self.key_states[key_name] = True
                return

            # Regular key - check for hotkey match
            try:
                pressed_modifiers: Set[str] = {
                    mod for mod, pressed in self.key_states.items() if pressed
                }

                for hotkey in self.config.get("hotkeys", []):
                    combo_lower = hotkey["combination"].lower()
                    parts = [p.strip() for p in combo_lower.split('+')]

                    main_key = parts[-1]
                    required_modifiers = set(parts[:-1])

                    if key_name == main_key and pressed_modifiers == required_modifiers:
                        logger.info(f"[{hotkey['combination']}: {hotkey['name']}] Activated")
                        self.queue.put({
                            "action": hotkey["name"],
                            "prompt": hotkey.get("prompt", "")
                        })
                        return

            except Exception as e:
                logger.error(f"Error in on_press: {e}")

    def _on_release(self, key) -> None:
        """Handle key release."""
        with self.pasting_lock:
            if self.is_pasting:
                return

        key_name = self._get_key_name(key)
        with self.key_states_lock:
            if key_name in self.key_states:
                self.key_states[key_name] = False

    def start(self) -> None:
        """Start the listener in a background thread."""
        if self._listener_thread and self._listener_thread.is_alive():
            return

        self.stop_event.clear()
        self._listener_thread = threading.Thread(
            target=self._run
        )
        self._listener_thread.start()

    def _run(self) -> None:
        """Run the pynput listener."""
        listener = pkb.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        listener.start()
        self.stop_event.wait()
        listener.stop()

    def stop(self) -> None:
        """Stop the listener."""
        self.stop_event.set()
        if self._listener_thread:
            self._listener_thread.join(timeout=1.0)

    def set_pasting(self, is_pasting: bool) -> None:
        """Set pasting flag (to ignore hotkeys during paste)."""
        with self.pasting_lock:
            self.is_pasting = is_pasting
