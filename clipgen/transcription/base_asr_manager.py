"""Abstract base for ASR engine managers.

Defines the contract every speech-to-text engine must implement so the
``Transcriber`` can stay engine-agnostic. Concrete engines:

• ``WhisperModelManager`` (faster-whisper, multilingual, default)
• ``ParakeetModelManager`` (NVIDIA Parakeet ONNX, 25 EU languages incl. Russian)

A new engine = subclass + entry in ``engine_factory.create_asr_manager``.

The ``raise NotImplementedError`` pattern is used instead of ``@abstractmethod``
because PyQt5's ``QObject`` metaclass conflicts with ``abc.ABCMeta`` and the
custom-metaclass workaround adds fragility for no real benefit here — every
subclass is exercised on app start, so missing implementations surface fast.
"""

import threading
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, pyqtSignal


# Shared state names — concrete engines must use these for the state machine
# so the UI can interpret status uniformly.
STATE_UNLOADED = "unloaded"
STATE_LOADING = "loading"
STATE_DOWNLOADING = "downloading"
STATE_READY = "ready"
STATE_TRANSCRIBING = "transcribing"
STATE_ERROR = "error"


class BaseASRManager(QObject):
    """Contract every ASR engine implements.

    Signals are defined here and inherited by subclasses (PyQt5 inherits
    pyqtSignal correctly across class hierarchies).
    """

    # Emitted on every state machine transition.
    state_changed = pyqtSignal(str)

    # Localised log line (message, hex color).
    log_signal = pyqtSignal(str, str)

    # Runtime metadata for the Settings status row.
    info_signal = pyqtSignal(dict)

    # Class-level identity. Subclasses MUST override.
    engine_name: str = "base"

    # Whether the engine can produce partial results during recording.
    # Used by ``Transcriber`` to decide whether to start a stream loop.
    supports_streaming: bool = False

    # ------------------------------------------------------------------ lifecycle

    def load_async(self) -> Optional[threading.Thread]:
        """Kick off model loading in a worker thread."""
        raise NotImplementedError

    def load_blocking(self) -> bool:
        """Load synchronously. Return True on success."""
        raise NotImplementedError

    def download_async(self) -> Optional[threading.Thread]:
        """Download weights without loading into VRAM."""
        raise NotImplementedError

    def cancel_download(self) -> None:
        """Cooperative cancellation of an in-flight download."""
        raise NotImplementedError

    def cancel_transcription(self) -> None:
        """Abort current inference (typically by killing the worker)."""
        raise NotImplementedError

    def unload(self, idle_triggered: bool = False) -> None:
        """Drop the model from memory and stop the idle timer."""
        raise NotImplementedError

    def shutdown(self, release_model: bool = False) -> None:
        """App-shutdown cleanup."""
        raise NotImplementedError

    # ------------------------------------------------------------------ state

    def get_state(self) -> str:
        """Return current state name (one of the STATE_* constants)."""
        raise NotImplementedError

    def is_loaded(self) -> bool:
        """True when ready to call transcribe()."""
        raise NotImplementedError

    def get_runtime_info(self) -> Dict[str, Any]:
        """Snapshot for the UI status row.

        Should include: ``state``, ``model``, ``device``, optionally
        ``compute_type``/``providers``, ``load_seconds``, ``engine``.
        """
        raise NotImplementedError

    def update_lang(self, lang: Dict[str, Any]) -> None:
        """Re-bind language strings after a runtime language switch."""
        raise NotImplementedError

    def reset_idle(self) -> None:
        """Restart the auto-unload countdown after a successful transcribe."""
        raise NotImplementedError

    # ------------------------------------------------------------------ inference

    def transcribe(
        self,
        audio,  # numpy float32, mono, 16 kHz
        language: Optional[str] = None,
        initial_prompt: Optional[str] = None,
        audio_duration: Optional[float] = None,
    ) -> Tuple[Optional[List[Any]], Optional[Dict[str, Any]]]:
        """Run inference on the captured audio.

        Returns ``(segments, info)`` or ``(None, None)`` on failure.
        Each segment must expose ``.text`` plus the four attributes
        ``filters.py`` reads via ``getattr(seg, attr, 0.0)``:
        ``avg_logprob``, ``no_speech_prob``, ``compression_ratio``.
        """
        raise NotImplementedError


class DownloadProgressReporter:
    """Throttled per-file progress emitter shared by Whisper and Parakeet.

    Goals:
      • First poll → emit immediately so the user sees activity instantly
        ("started, not stuck"). Without this, files that finish in <2s
        are silent because the throttle blocks all intermediate emits.
      • Subsequent polls → throttle on percent advance AND elapsed time
        so a 2.4 GB file produces ~20 lines, not thousands.
      • Compute speed in MB/s between successive polls so the user can
        eyeball whether the download will finish in 10s or 10 min.
      • Always emit a final 100% line when the file completes — even when
        ``expected_size`` is unknown, fall back to "X MB downloaded".
    """

    # Throttle thresholds: emit only if ≥this many percent advanced AND
    # ≥this many seconds passed since last emit. Either condition alone
    # isn't sufficient — we want both to suppress noise but still get
    # regular updates on slow links.
    PCT_STEP = 5
    MIN_INTERVAL = 1.5

    def __init__(self, log_emitter, color: str = "#666666"):
        # log_emitter is a Qt signal's .emit method; we call it with
        # (text, color). Keeping it injected makes this class testable
        # without spinning up Qt.
        self._emit = log_emitter
        self._color = color
        self._last_pct = -1
        self._last_emit_ts = 0.0
        self._last_bytes = 0
        self._first_done = False
        self._final_emitted = False

    def __call__(self, bytes_done: int, expected: Optional[int]) -> None:
        """Receive a (bytes_done, expected_size) snapshot from the downloader."""
        import time as _time

        now = _time.time()
        pct = int(bytes_done * 100 / expected) if expected and expected > 0 else None
        is_complete = pct is not None and pct >= 100

        if is_complete and self._final_emitted:
            return  # avoid double 100% lines

        # First poll — always emit so the user sees the file actually started.
        if not self._first_done:
            self._first_done = True
            self._render(now, bytes_done, expected, pct, speed=None)
            return

        # Final state — always emit, regardless of throttle.
        if is_complete:
            self._final_emitted = True
            self._render(now, bytes_done, expected, pct, speed=self._speed(now, bytes_done))
            return

        # Intermediate: throttle by percent AND time. Both must be satisfied
        # before we add a new line. Without the AND, a slow trickle download
        # would still spam time-based emits, and a fast one would still spam
        # percent-based emits.
        if pct is not None and (pct - self._last_pct) < self.PCT_STEP:
            return
        if (now - self._last_emit_ts) < self.MIN_INTERVAL:
            return

        self._render(now, bytes_done, expected, pct, speed=self._speed(now, bytes_done))

    def _speed(self, now: float, bytes_done: int) -> Optional[float]:
        """Return MB/s between the previous emit and this one (None if too short)."""
        elapsed = now - self._last_emit_ts
        if elapsed < 0.2 or self._last_bytes <= 0:
            return None
        delta_mb = (bytes_done - self._last_bytes) / (1024 * 1024)
        if delta_mb <= 0:
            return None
        return delta_mb / elapsed

    def _render(self, now: float, bytes_done: int, expected: Optional[int],
                pct: Optional[int], speed: Optional[float]) -> None:
        done_mb = bytes_done / (1024 * 1024)
        if pct is not None and expected:
            total_mb = expected / (1024 * 1024)
            head = f"    {pct}% ({done_mb:.0f}/{total_mb:.0f} MB"
            tail = ")"
        else:
            # Expected size unknown — show running total. The trailing
            # newline (no closing paren) keeps the format unambiguous.
            head = f"    {done_mb:.1f} MB"
            tail = ""

        if speed is not None and speed >= 0.3:
            line = f"{head}, {speed:.1f} MB/s{tail}"
        else:
            line = head + tail

        self._last_pct = pct if pct is not None else self._last_pct
        self._last_emit_ts = now
        self._last_bytes = bytes_done
        self._emit(line, self._color)
