"""Coordinates record -> transcribe -> paste flow for voice hotkeys.

Lifecycle of a single voice hotkey activation:
    on_press_event(hotkey)   — listener notifies us; we:
                                 1. ensure the model is loaded (sync);
                                 2. start AudioRecorder;
                                 3. flip overlay to RECORDING.
    on_release_event(hotkey) — listener notifies us; we:
                                 1. stop recorder, get numpy audio;
                                 2. flip overlay to TRANSCRIBING;
                                 3. transcribe, filter, paste;
                                 4. flip overlay back to ready.

Everything past step 1 in on_press happens in worker threads to keep the
UI responsive.
"""

import logging
import threading
import time
import winsound
from typing import Any, Callable, Dict, Optional

from PyQt5.QtCore import QObject, pyqtSignal

from .audio_recorder import AudioRecorder
from .base_asr_manager import BaseASRManager
from .filters import filter_segments_with_reasons, join_segments


logger = logging.getLogger('ClipGen')


# Custom UI-only state shown in overlay/tray; not part of model state machine.
UI_STATE_IDLE = "idle"
UI_STATE_LOADING = "loading"
UI_STATE_RECORDING = "recording"
UI_STATE_TRANSCRIBING = "transcribing"
UI_STATE_DONE = "done"
UI_STATE_ERROR = "error"


class Transcriber(QObject):
    """Glue between hotkey listener, recorder, model and clipboard."""

    # UI state changes for overlay + tray.
    ui_state_changed = pyqtSignal(str, str)   # state, optional message

    # Transcription log signals (forwarded to MainWindow.log_signal).
    log_signal = pyqtSignal(str, str)         # message, hex color

    # Time updates while transcribing (for tray seconds counter).
    transcribing_time_signal = pyqtSignal(str)

    # Partial text emitted by streaming-capable engines while still recording.
    # The signal exists so the overlay/UI can wire to it now; no emitter
    # writes to it yet (functional streaming arrives in a follow-up change).
    streaming_partial_signal = pyqtSignal(str)

    INFO_COLOR = "#A3BFFA"
    ERROR_COLOR = "#FF5F57"
    DEFAULT_HOTKEY_COLOR = "#FFFFFF"

    MIN_AUDIO_SECONDS = 0.3

    def __init__(
        self,
        config: Dict[str, Any],
        lang: Dict[str, Any],
        model_manager: BaseASRManager,
        clipboard,
        parent=None,
    ):
        super().__init__(parent)
        self.config = config
        self.lang = lang
        self.model_manager = model_manager
        self.clipboard = clipboard

        self._recorder: Optional[AudioRecorder] = None
        self._lock = threading.Lock()
        self._active = False
        self._active_hotkey: Optional[Dict[str, Any]] = None
        self._record_start: float = 0.0
        self._beep_paths = set()
        # Set when _press_worker finishes opening the input stream. Release
        # workers wait on this so they cannot tear down state while the
        # press worker is still mid-setup (a real race when the user taps
        # the hotkey during the blocking 80 ms start beep).
        self._press_ready = threading.Event()

        # Streaming-mode bookkeeping. Populated only when the active engine
        # has ``supports_streaming`` and the user enabled the toggle.
        self._stream_thread: Optional[threading.Thread] = None
        self._stream_stop_event: Optional[threading.Event] = None

    # ------------------------------------------------------------------ helpers

    def update_lang(self, lang: Dict[str, Any]) -> None:
        self.lang = lang

    def _tr_section(self) -> Dict[str, Any]:
        return self.config.get("transcription", {})

    def _logs_section(self) -> Dict[str, Any]:
        return self.lang.get("logs", {})

    @staticmethod
    def _strip_final_period(text: str) -> str:
        stripped = (text or "").rstrip()
        if not stripped or stripped.endswith(("...", "…", "!", "?", "！", "？")):
            return text
        if stripped.endswith((".", "。")):
            return stripped[:-1].rstrip()
        return text

    @staticmethod
    def _prompt_requests_no_final_period(prompt: Optional[str]) -> bool:
        text = (prompt or "").lower()
        markers = (
            "не ставь точк",
            "не ставить точк",
            "без точки в конце",
            "не добавляй точк",
            "don't add a final period",
            "do not add a final period",
            "no final period",
            "without a final period",
            "remove final period",
        )
        return any(marker in text for marker in markers)

    def _postprocess_transcript(
        self,
        text: str,
        hotkey: Optional[Dict[str, Any]],
        initial_prompt: Optional[str],
    ) -> str:
        strip_period = bool((hotkey or {}).get("transcription_strip_trailing_period", False))
        # Backward compatibility for existing hotkeys that used the Whisper-only
        # prompt field to request messenger-style punctuation.
        if not strip_period:
            strip_period = self._prompt_requests_no_final_period(initial_prompt)
        if strip_period:
            return self._strip_final_period(text)
        return text

    def _emit_log(self, key: str, color: str, **fmt) -> None:
        template = self._logs_section().get(key, key)
        try:
            msg = template.format(**fmt) if fmt else template
        except (KeyError, IndexError, ValueError):
            msg = template
        self.log_signal.emit(msg, color)

    def _ui(self, state: str, message: str = "") -> None:
        self.ui_state_changed.emit(state, message)

    def _beep(self, frequency: int, duration_ms: int = 80) -> None:
        """Short start-of-recording chime.

        We synthesise a sine-wave WAV in memory, persist it to a temp
        file, and hand it to ``winsound.PlaySound`` with SND_FILENAME +
        SND_ASYNC. This routes through the standard Windows audio mixer
        — the same path that YouTube, Spotify, system notifications use.
        It's the most reliable option after we discovered that PortAudio's
        MME backend silently fails on some Bluetooth headsets (Sony
        WH-1000XM4) and that ``winsound.Beep`` is muted on certain Win10/11
        configurations.

        We cache the temp file path between calls so successive beeps
        don't keep creating files on disk.
        """
        if not self._tr_section().get("feedback_sounds", True):
            return

        wav_path = self._beep_wav_path(frequency, duration_ms)
        if wav_path is not None:
            try:
                winsound.PlaySound(
                    wav_path,
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                )
                return
            except Exception:
                logger.debug("PlaySound failed", exc_info=True)

        # Last-ditch fallback if the WAV approach failed.
        try:
            winsound.Beep(frequency, duration_ms)
        except Exception:
            logger.debug("winsound.Beep also failed", exc_info=True)

    def _beep_wav_path(self, frequency: int, duration_ms: int) -> Optional[str]:
        """Return a path to a cached on-disk WAV containing the beep tone."""
        cache = getattr(self, "_beep_wav_cache", None)
        key = (frequency, duration_ms)
        if cache is not None and cache.get("key") == key:
            return cache.get("path")

        try:
            import math
            import os
            import struct
            import tempfile
            import wave

            sample_rate = 44100
            n_samples = int(sample_rate * duration_ms / 1000.0)
            fd, path = tempfile.mkstemp(suffix=".wav", prefix="clipgen_beep_")
            os.close(fd)
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                frames = bytearray()
                fade_frames = max(1, n_samples // 30)
                for i in range(n_samples):
                    t = i / sample_rate
                    fade = min(
                        1.0,
                        i / fade_frames,
                        (n_samples - i) / fade_frames,
                    )
                    sample = int(math.sin(2 * math.pi * frequency * t)
                                 * 32767 * 0.3 * fade)
                    frames += struct.pack("<h", sample)
                wf.writeframes(bytes(frames))
            self._beep_wav_cache = {"key": key, "path": path}
            self._beep_paths.add(path)
            return path
        except Exception:
            logger.exception("Failed to build beep WAV")
            return None

    # ------------------------------------------------------------------ entry

    def on_press(self, hotkey: Dict[str, Any]) -> None:
        """Hotkey pressed: kick off recording in a worker thread."""
        with self._lock:
            if self._active:
                return
            self._active = True
            self._active_hotkey = hotkey
            # Reset the readiness gate synchronously, BEFORE we spawn the
            # press worker thread. If we did this inside _press_worker,
            # a quickly-arriving release event would race past the cleared
            # gate (see ``_release_worker`` for the wait()). This way any
            # _release_worker spawned after this point will block until
            # press finishes setup.
            self._press_ready.clear()

        threading.Thread(
            target=self._press_worker,
            args=(hotkey,),
            daemon=True,
            name="TranscriberPress",
        ).start()

    def on_release(self, hotkey: Dict[str, Any]) -> None:
        """Hotkey released: stop recording and transcribe in worker thread."""
        with self._lock:
            if not self._active:
                return
            current = self._active_hotkey

        threading.Thread(
            target=self._release_worker,
            args=(current,),
            daemon=True,
            name="TranscriberRelease",
        ).start()

    # ------------------------------------------------------------------ workers

    def _press_worker(self, hotkey: Dict[str, Any]) -> None:
        # Note: _press_ready is cleared synchronously in on_press(); we
        # only signal it (set) here in the finally block.
        try:
            # Ensure model is ready before opening the audio stream.
            if not self.model_manager.is_loaded():
                # A hotkey press must not silently download gigabytes of
                # weights. Point the user to the Settings install button,
                # where the download shows progress and can be cancelled.
                requires_download = getattr(
                    self.model_manager, "requires_download", None
                )
                if callable(requires_download) and requires_download():
                    self._emit_log(
                        "transcription_model_not_downloaded_hotkey",
                        self.ERROR_COLOR,
                    )
                    self._ui(UI_STATE_ERROR)
                    self._fail_active()
                    self._press_ready.set()
                    return

                self._ui(UI_STATE_LOADING)
                ok = self.model_manager.load_blocking()
                if not ok:
                    self._emit_log("transcription_model_load_failed_short", self.ERROR_COLOR)
                    self._ui(UI_STATE_ERROR)
                    self._fail_active()
                    self._press_ready.set()
                    return
                # A long model load can outlast the release worker's wait
                # (the user tapped and let go minutes ago). In that case the
                # activation is already torn down — opening the microphone
                # now would leave it recording with nobody to stop it.
                with self._lock:
                    still_active = self._active
                if not still_active:
                    self._ui(UI_STATE_IDLE)
                    return

            tr = self._tr_section()
            audio_cfg = tr.get("audio", {})
            device_raw = audio_cfg.get("input_device", None)
            try:
                device = int(device_raw) if device_raw is not None else None
            except (TypeError, ValueError):
                device = None
            self._recorder = AudioRecorder(
                sample_rate=int(audio_cfg.get("sample_rate", 16000)),
                blocksize=int(audio_cfg.get("blocksize", 1024)),
                latency=audio_cfg.get("latency", "low"),
                device=device,
                max_record_seconds=int(audio_cfg.get("max_record_seconds", 120) or 120),
            )

            # Play start chime BEFORE opening the input stream — when the
            # mic is captured (especially under WASAPI/MME), the audio
            # device can block simultaneous winsound output, leaving the
            # beep silent. superwhisper0 does it in this order for the same
            # reason.
            self._beep(900)

            started = self._recorder.start()
            if not started:
                err = getattr(self._recorder, "last_error", "") or "unknown error"
                self._emit_log("transcription_microphone_open_failed", self.ERROR_COLOR, error=err)
                self._ui(UI_STATE_ERROR)
                self._fail_active()
                self._press_ready.set()
                return

            # The release worker may have given up (timeout) while we were
            # setting up. Close the stream immediately instead of leaving an
            # unstoppable recording behind.
            with self._lock:
                still_active = self._active
            if not still_active:
                recorder = self._recorder
                self._recorder = None
                try:
                    if recorder is not None:
                        recorder.stop()
                except Exception:
                    logger.debug("Stopping abandoned recorder failed", exc_info=True)
                self._ui(UI_STATE_IDLE)
                return

            self._record_start = time.time()
            # Header format: "<name> - <HH:MM:SS>". The action name already
            # tells the user which hotkey fired — combo prefix would either
            # be redundant (if name contains the combo) or noise. log_tab.py
            # treats any "<known_name> - HH:MM:SS" line as a section header.
            timestamp = time.strftime('%H:%M:%S')
            color = hotkey.get("log_color", self.DEFAULT_HOTKEY_COLOR)
            name = hotkey.get("name", "")
            self.log_signal.emit(f"{name} - {timestamp}", color)
            mic_name = getattr(self._recorder, "opened_device_name", None)
            if mic_name:
                self._emit_log("transcription_microphone_selected", "#888888", name=mic_name)
            self._ui(UI_STATE_RECORDING)
            self._start_recording_watchdog(
                int(audio_cfg.get("max_record_seconds", 120) or 120)
            )
            # Optional streaming preview — only fires when the active engine
            # opts in via ``supports_streaming`` and the user enabled the
            # toggle. Currently a no-op stub; the loop body will be filled
            # in by the streaming follow-up work.
            self._maybe_start_stream_loop()
        except Exception as exc:
            logger.exception("Transcriber.press_worker failed")
            self._emit_log(
                "transcription_recording_start_failed",
                self.ERROR_COLOR,
                error=f"{type(exc).__name__}: {exc}",
            )
            self._ui(UI_STATE_ERROR)
            self._fail_active()
        finally:
            # Always release the gate so a waiting release worker can
            # proceed (or learn that setup failed).
            self._press_ready.set()

    def _release_worker(self, hotkey: Optional[Dict[str, Any]]) -> None:
        # Wait for the press worker to either finish opening the input
        # stream or report a failure. Without this, a quick tap of the
        # hotkey races the 80 ms blocking start-beep and we'd tear down
        # ``self._recorder`` before press_worker even calls .start().
        self._press_ready.wait(timeout=5.0)

        with self._lock:
            recorder = self._recorder
            self._recorder = None

        # Tear down the streaming preview before pulling the audio out of
        # the recorder so the stream thread observes a fresh state.
        self._stop_stream_loop()

        try:
            if recorder is None:
                self._fail_active()
                return

            audio = recorder.stop()

            color = (hotkey or {}).get("log_color", self.DEFAULT_HOTKEY_COLOR)

            if audio is None:
                self._emit_log("transcription_too_short", self.INFO_COLOR)
                self._ui(UI_STATE_IDLE)
                self._fail_active()
                return

            duration = recorder.duration_seconds(audio)
            if duration < self.MIN_AUDIO_SECONDS:
                self._emit_log("transcription_too_short", self.INFO_COLOR)
                self._ui(UI_STATE_IDLE)
                self._fail_active()
                return

            if getattr(recorder, "limit_reached", False):
                self._emit_log("transcription_recording_limit_stopped", "#FFC107")
            statuses = getattr(recorder, "last_stream_statuses", []) or []
            if statuses:
                self._emit_log(
                    "transcription_audio_stream_status",
                    "#FFC107",
                    status="; ".join(statuses[:3]),
                )

            # Quick silence sanity check: if peak amplitude is essentially
            # zero, the captured stream is silent (wrong mic / muted
            # device). Warn the user — Whisper would otherwise return
            # "Речь не обнаружена" without explaining why.
            try:
                import numpy as _np
                peak = float(_np.max(_np.abs(audio))) if audio.size else 0.0
            except Exception:
                peak = 1.0  # avoid false-positive warnings
            if peak < 0.01:
                self._emit_log("transcription_silent_microphone_warning", "#FFC107")

            processed = self._preprocess_audio(audio)
            if processed is None:
                self._emit_log("transcription_empty", self.INFO_COLOR)
                self._ui(UI_STATE_IDLE)
                self._fail_active()
                return
            audio = processed

            self._ui(UI_STATE_TRANSCRIBING)

            # Watchdog to update tray seconds while transcribing.
            stop_evt = threading.Event()
            t_start = time.time()

            def tick():
                while not stop_evt.is_set():
                    elapsed = time.time() - t_start
                    self.transcribing_time_signal.emit(f"{elapsed:.1f}")
                    if stop_evt.wait(0.1):
                        break

            ticker = threading.Thread(target=tick, daemon=True)
            ticker.start()

            try:
                tr = self._tr_section()
                language = ((hotkey or {}).get("transcription_language")
                            or tr.get("default_language", "auto"))
                hotkey_prompt = (hotkey or {}).get("transcription_initial_prompt") or ""
                whisper_cfg = tr.get("whisper", {}) if isinstance(tr.get("whisper"), dict) else {}
                global_prompt = (
                    whisper_cfg.get("whisper_initial_prompt")
                    or tr.get("whisper_initial_prompt", "")
                    or ""
                )
                initial_prompt = "\n".join(
                    part.strip() for part in (global_prompt, hotkey_prompt) if part and part.strip()
                ) or None

                segments, _info = self.model_manager.transcribe(
                    audio,
                    language=language,
                    initial_prompt=initial_prompt,
                    audio_duration=duration,
                )
            finally:
                stop_evt.set()
                ticker.join(timeout=0.2)

            elapsed = time.time() - t_start

            if segments is None:
                self._ui(UI_STATE_ERROR)
                self._fail_active()
                return

            if not segments:
                self._emit_log("transcription_empty", self.INFO_COLOR)
                self._ui(UI_STATE_IDLE)
                self._fail_active()
                return

            tr = self._tr_section()
            if tr.get("filter_hallucinations", True):
                segments, dropped = filter_segments_with_reasons(
                    segments,
                    blacklist=tr.get("hallucination_blacklist", []),
                )
                for dropped_text, reason in dropped[:3]:
                    self._emit_log(
                        "transcription_filtered",
                        self.INFO_COLOR,
                        text=f"{dropped_text} ({reason})",
                    )

            text = join_segments(segments)
            text = self._postprocess_transcript(text, hotkey, initial_prompt)
            if not text:
                self._emit_log("transcription_empty", self.INFO_COLOR)
                self._ui(UI_STATE_IDLE)
                self._fail_active()
                return

            # Compact two-line summary: gray status with both durations,
            # then the transcribed text in the hotkey colour. log_tab.py
            # automatically indents non-header messages.
            self._emit_log(
                "transcription_summary",
                "#888888",
                audio=duration,
                time=elapsed,
            )
            self.log_signal.emit(text, color)

            try:
                self.clipboard.set_text(text)
                # Small sleep before paste so the OS clipboard settles.
                time.sleep(0.02)
                self.clipboard.simulate_paste()
            except Exception:
                logger.exception("Failed to paste transcription")

            self._ui(UI_STATE_DONE)
        except Exception as exc:
            logger.exception("Transcriber.release_worker failed")
            error = f"{type(exc).__name__}: {exc}" if str(exc) else repr(exc)
            self._emit_log("transcription_failed", self.ERROR_COLOR, error=error)
            self._ui(UI_STATE_ERROR)
        finally:
            with self._lock:
                self._active = False
                self._active_hotkey = None

    def _fail_active(self) -> None:
        with self._lock:
            self._active = False
            self._active_hotkey = None

    def _start_recording_watchdog(self, max_seconds: int) -> None:
        """Auto-release recording if the global key release event is lost."""
        max_seconds = max(1, int(max_seconds or 120))
        # Bind this watchdog to the recorder it was started for. A watchdog
        # from an earlier recording must never tear down a *later* one: with
        # the default 120 s limit an old timer could otherwise wake during a
        # fresh recording and stop it as if the key had been released.
        guarded_recorder = self._recorder

        def worker() -> None:
            time.sleep(max_seconds + 0.5)
            with self._lock:
                active = self._active
                hotkey = self._active_hotkey
            recorder = self._recorder
            if (
                active
                and recorder is not None
                and recorder is guarded_recorder
                and recorder.is_recording()
            ):
                self._emit_log("transcription_recording_limit_reached", "#FFC107")
                self.on_release(hotkey or {})

        threading.Thread(
            target=worker,
            daemon=True,
            name="TranscriberRecordWatchdog",
        ).start()

    def _maybe_start_stream_loop(self) -> None:
        """Start the streaming preview loop if engine + config opt in.

        Stub for now: only sets up the stop-event so ``_stop_stream_loop``
        is symmetric. The actual transcription loop body lands with the
        streaming feature; this hook reserves the seam without altering
        any current behaviour.
        """
        if not getattr(self.model_manager, "supports_streaming", False):
            return
        tr = self._tr_section()
        if not tr.get("streaming_enabled", False):
            return
        # Reserve the stop event so future loop body can exit cleanly.
        self._stream_stop_event = threading.Event()
        # Loop thread is intentionally not started yet — engine streaming
        # implementations will be wired in a follow-up.

    def _stop_stream_loop(self) -> None:
        """Signal the streaming loop (if any) to terminate and join it."""
        evt = self._stream_stop_event
        if evt is not None:
            evt.set()
        thread = self._stream_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        self._stream_thread = None
        self._stream_stop_event = None

    def _preprocess_audio(self, audio):
        """Lightweight cleanup before Whisper: DC removal and silence trim."""
        try:
            import numpy as np

            if audio is None or audio.size == 0:
                return None
            cleaned = audio.astype(np.float32, copy=True)
            cleaned -= float(np.mean(cleaned))

            rms = float(np.sqrt(np.mean(np.square(cleaned)))) if cleaned.size else 0.0
            peak = float(np.max(np.abs(cleaned))) if cleaned.size else 0.0
            if rms < 0.0015 and peak < 0.01:
                return None

            window = max(160, int(0.02 * 16000))
            if cleaned.size > window * 4:
                threshold = max(0.003, rms * 0.35)
                abs_audio = np.abs(cleaned)
                starts = np.where(abs_audio > threshold)[0]
                if starts.size:
                    start = max(0, int(starts[0]) - window)
                    end = min(cleaned.size, int(starts[-1]) + window)
                    cleaned = cleaned[start:end]
            return cleaned
        except Exception:
            logger.debug("Audio preprocessing failed; using raw audio", exc_info=True)
            return audio

    def shutdown(self) -> None:
        try:
            self._stop_stream_loop()
        except Exception:
            pass
        try:
            if self._recorder is not None:
                self._recorder.stop()
        except Exception:
            pass
        try:
            import os
            for path in list(self._beep_paths):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
            self._beep_paths.clear()
        except Exception:
            pass
