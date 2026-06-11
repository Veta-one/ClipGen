"""Global hotkey listener using pynput."""

import logging
import threading
from queue import Queue
from typing import Dict, Any, List, Set, Optional

from pynput import keyboard as pkb

logger = logging.getLogger('ClipGen')


class HotkeyListener:
    """Listens for global hotkeys and dispatches events to queue.

    Two hotkey behaviors are supported, distinguished by the hotkey's
    `type` field:

    • ``text_action`` (default) — single event on press when modifiers + main
      key match. Identical to the original ClipGen behavior.

    • ``transcription`` — push-to-talk. Emits ``transcription_start`` on press,
      then ``transcription_stop`` as soon as any key in the combination is
      released. Used by the voice transcription pipeline.
    """

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

        # Currently held transcription hotkey (if any). Stored under lock so
        # release events know what to emit.
        self._active_transcription: Optional[Dict[str, Any]] = None
        self._transcription_lock = threading.Lock()

        # Push-to-talk spurious-release handling. A raw global KEYUP is not
        # trustworthy for a held key: Windows injects synthetic events for the
        # Ctrl+Space IME/layout chord and cheap keyboards chatter under a held
        # combo. We debounce the stop and verify the physical key state so a
        # transient blip cannot end recording while the user is still holding.
        self._pending_stop_timer: Optional[threading.Timer] = None
        self._pending_stop_vk: Optional[int] = None
        _tr_cfg = self.config.get("transcription", {}) or {}
        self._spurious_release_guard = bool(
            _tr_cfg.get("ptt_spurious_release_guard", True)
        )
        try:
            _debounce_ms = int(_tr_cfg.get("ptt_release_debounce_ms", 180))
        except (TypeError, ValueError):
            _debounce_ms = 180
        self._release_debounce_seconds = max(0.0, _debounce_ms / 1000.0)

        # Stop signal
        self.stop_event = threading.Event()
        self._listener_thread: threading.Thread = None

    def _get_key_name(self, key) -> Optional[str]:
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

    @staticmethod
    def _parse_combination(combination: str) -> tuple:
        """Return (main_key, set_of_modifiers) for a combination string."""
        combo_lower = combination.lower()
        parts = [p.strip() for p in combo_lower.split('+')]
        if not parts:
            return "", set()
        main_key = parts[-1]
        modifiers = set(parts[:-1])
        return main_key, modifiers

    def _is_part_of_active_transcription(self, key_name: str) -> bool:
        """Check if a released key belongs to the currently active transcription combo."""
        with self._transcription_lock:
            if self._active_transcription is None:
                return False
            main_key, modifiers = self._parse_combination(
                self._active_transcription.get("combination", "")
            )
            return key_name == main_key or key_name in modifiers

    def _dispatch_text_action(self, hotkey: Dict[str, Any]) -> None:
        logger.info(f"[{hotkey['combination']}: {hotkey['name']}] Activated")
        self.queue.put({
            "kind": "text_action",
            "action": hotkey.get("name", ""),
            "prompt": hotkey.get("prompt", ""),
            "hotkey": hotkey,
        })

    def _dispatch_transcription_start(self, hotkey: Dict[str, Any]) -> None:
        # Drop any stop that was still pending from a previous activation.
        self._cancel_pending_stop()
        with self._transcription_lock:
            if self._active_transcription is not None:
                # Already recording another hotkey; ignore.
                return
            self._active_transcription = hotkey
        logger.info(f"[{hotkey['combination']}: {hotkey['name']}] Transcription start")
        self.queue.put({
            "kind": "transcription_start",
            "action": hotkey.get("name", ""),
            "hotkey": hotkey,
        })

    def _dispatch_transcription_stop(self) -> None:
        with self._transcription_lock:
            hotkey = self._active_transcription
            self._active_transcription = None
        if hotkey is None:
            return
        logger.info(f"[{hotkey['combination']}: {hotkey['name']}] Transcription stop")
        self.queue.put({
            "kind": "transcription_stop",
            "action": hotkey.get("name", ""),
            "hotkey": hotkey,
        })

    # -------------------------------------------------- push-to-talk debounce

    def _cancel_pending_stop(self) -> None:
        """Cancel a scheduled push-to-talk stop (a combo key came back down)."""
        with self._transcription_lock:
            timer = self._pending_stop_timer
            self._pending_stop_timer = None
            self._pending_stop_vk = None
        if timer is not None:
            timer.cancel()

    def _schedule_transcription_stop(self, vk: Optional[int]) -> None:
        """Stop recording after a short debounce, not on the raw KEYUP.

        A held key can produce a spurious KEYUP: Windows injects synthetic
        events for the Ctrl+Space IME/layout chord, and cheap keyboards
        chatter under a held combo. Stopping immediately makes recording
        "drop" mid-hold. Instead we wait ``_release_debounce_seconds``; a
        re-press (auto-repeat tick or chatter bounce-back) cancels the stop
        via _cancel_pending_stop, and when the timer does fire we re-check
        the physical key state so a still-held key never ends recording.
        """
        if self._release_debounce_seconds <= 0:
            if self._spurious_release_guard and self._vk_physically_down(vk):
                return
            self._dispatch_transcription_stop()
            return
        with self._transcription_lock:
            if self._active_transcription is None:
                return
            self._pending_stop_vk = vk
            if self._pending_stop_timer is not None:
                return  # a stop is already pending; keep the existing timer
            timer = threading.Timer(
                self._release_debounce_seconds, self._fire_pending_stop
            )
            timer.daemon = True
            self._pending_stop_timer = timer
        timer.start()

    def _fire_pending_stop(self) -> None:
        """Debounce elapsed: stop unless the key is still physically held."""
        with self._transcription_lock:
            self._pending_stop_timer = None
            vk = self._pending_stop_vk
            self._pending_stop_vk = None
            has_active = self._active_transcription is not None
        if not has_active:
            return
        if self._spurious_release_guard and self._vk_physically_down(vk):
            # Still held — the KEYUP was spurious. Keep recording; the real
            # release will arrive as a fresh KEYUP and schedule a new stop.
            return
        self._dispatch_transcription_stop()

    @staticmethod
    def _vk_physically_down(vk: Optional[int]) -> bool:
        """Best-effort (Windows): is the virtual key currently held down?

        Uses GetAsyncKeyState. Returns False whenever we cannot tell, so the
        caller errs toward stopping rather than recording forever.
        """
        if vk is None:
            return False
        try:
            import ctypes
            state = ctypes.windll.user32.GetAsyncKeyState(int(vk))
        except Exception:
            return False
        return bool(state & 0x8000)

    def _on_press(self, key) -> None:
        """Handle key press."""
        with self.pasting_lock:
            if self.is_pasting:
                return

        key_name = self._get_key_name(key)
        if not key_name:
            return

        # Push-to-talk heartbeat: if a stop is pending for the active combo
        # and one of its keys is (re)pressed — an auto-repeat tick or a
        # chatter bounce-back — cancel the pending stop so a transient blip
        # doesn't end recording mid-hold.
        if self._is_part_of_active_transcription(key_name):
            self._cancel_pending_stop()

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
                    main_key, required_modifiers = self._parse_combination(
                        hotkey.get("combination", "")
                    )
                    if not main_key:
                        continue
                    if key_name == main_key and pressed_modifiers == required_modifiers:
                        kind = hotkey.get("type", "text_action")
                        if kind == "transcription":
                            self._dispatch_transcription_start(hotkey)
                        else:
                            self._dispatch_text_action(hotkey)
                        return

            except Exception as e:
                logger.error(f"Error in on_press: {e}")

    def _on_release(self, key) -> None:
        """Handle key release."""
        with self.pasting_lock:
            is_pasting = self.is_pasting

        key_name = self._get_key_name(key)
        if not key_name:
            return

        # If the released key belongs to an active transcription combo, stop
        # — but not on the first raw KEYUP. A held key can emit a spurious
        # release (Windows Ctrl+Space IME chord, keyboard chatter); see
        # _schedule_transcription_stop for the debounce + physical-state check.
        if not is_pasting and self._is_part_of_active_transcription(key_name):
            self._schedule_transcription_stop(getattr(key, "vk", None))

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
        if not is_pasting:
            with self.key_states_lock:
                for key_name in self.key_states:
                    self.key_states[key_name] = False
