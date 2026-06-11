"""Microphone capture for push-to-talk transcription.

Uses sounddevice.InputStream to capture mono 16-bit PCM at 16 kHz (Whisper's
expected input format). Samples are accumulated in memory and converted to
the float32 numpy array Whisper expects, with no disk I/O.
"""

import logging
import threading
from typing import List, Optional, Set, Tuple

logger = logging.getLogger('ClipGen')


def list_input_devices() -> List[Tuple[int, str]]:
    """Enumerate microphone-capable devices.

    Only WASAPI and DirectSound entries are returned: MME silently fails
    on many Bluetooth headsets, and WDM-KS uses exclusive-mode kernel
    streaming that locks the device, breaking Windows audio routing for
    other apps. WASAPI/DirectSound use shared mode and Just Work on Win10/11.
    """
    try:
        import sounddevice as sd
    except ImportError:
        return []
    out: List[Tuple[int, str]] = []
    allowed_hosts = ("wasapi", "directsound")
    try:
        host_apis = sd.query_hostapis()
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) <= 0:
                continue
            host_idx = dev.get("hostapi", -1)
            host_name = ""
            if 0 <= host_idx < len(host_apis):
                host_name = host_apis[host_idx].get("name", "")
            host_lower = host_name.lower()
            if not any(allowed in host_lower for allowed in allowed_hosts):
                continue
            label = dev.get("name", f"Device {idx}")
            if host_name:
                label = f"{label}  ({host_name})"
            out.append((idx, label))
    except Exception:
        logger.exception("Failed to enumerate input devices")
    return out


class AudioRecorder:
    """Captures mono audio while a hotkey is held.

    Lifecycle: start() -> ... -> stop() returns float32 numpy array.
    Multiple start/stop cycles are supported.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        blocksize: int = 1024,
        latency: str = "low",
        device: Optional[int] = None,
        max_record_seconds: int = 120,
    ):
        self.sample_rate = sample_rate
        self.blocksize = blocksize
        self.latency = latency
        self.max_record_seconds = max(1, int(max_record_seconds or 120))
        # ``device`` is a sounddevice device index. None means "OS default".
        self.device = device

        self._stream = None
        self._chunks: List = []
        self._lock = threading.Lock()
        self._recording = False
        # Reason of last start() failure — bubbled up so the UI can log it.
        self.last_error: Optional[str] = None
        # Friendly name of the device that was actually opened (set by start).
        self.opened_device_name: Optional[str] = None
        self.limit_reached = False
        self.last_stream_statuses: List[str] = []
        self._active_sample_rate = self.sample_rate

    def is_recording(self) -> bool:
        return self._recording

    def start(self) -> bool:
        """Open the input stream and start capturing.

        Returns True if started, False if already recording or error.
        """
        self.last_error = None
        if self._recording:
            self.last_error = "already recording"
            return False

        try:
            import sounddevice as sd
            import numpy as np  # noqa: F401  (used in stop())
        except ImportError as exc:
            self.last_error = (
                f"sounddevice/numpy not installed: {exc}"
            )
            logger.error(self.last_error)
            return False

        with self._lock:
            self._chunks = []
            self._stream_status_seen: List[str] = []
            self._captured_frames = 0
            self.limit_reached = False
            self.last_stream_statuses = []

        def callback(indata, frames, time_info, status):
            if status:
                # Track non-OK status frames so the caller can surface them
                # to the user instead of silently producing empty audio.
                logger.debug("AudioRecorder status: %s", status)
                with self._lock:
                    self._stream_status_seen.append(str(status))
            with self._lock:
                max_frames = self._active_sample_rate * self.max_record_seconds
                if self._captured_frames >= max_frames:
                    self.limit_reached = True
                    return
                # indata is a numpy view; copy because the buffer is reused.
                remaining = max_frames - self._captured_frames
                if frames > remaining:
                    self._chunks.append(indata[:remaining].copy())
                    self._captured_frames += remaining
                    self.limit_reached = True
                else:
                    self._chunks.append(indata.copy())
                    self._captured_frames += frames

        # Try a sequence of device options. PortAudio's MME backend (Windows
        # default) frequently fails on certain mics with "Unanticipated
        # host error MME -1". WASAPI is almost always available and robust.
        # We attempt: explicit device > default device > any WASAPI input.
        attempts = self._build_attempt_chain(sd)
        last_exc: Optional[Exception] = None
        for label, kwargs in attempts:
            try:
                stream_kwargs = dict(kwargs)
                sample_rate = int(stream_kwargs.pop("samplerate", self.sample_rate))
                self._active_sample_rate = sample_rate
                self._stream = sd.InputStream(
                    samplerate=sample_rate,
                    channels=1,
                    dtype="int16",
                    blocksize=self.blocksize,
                    latency=self.latency,
                    callback=callback,
                    **stream_kwargs,
                )
                self._stream.start()
                self._recording = True
                logger.info("AudioRecorder opened via %s at %s Hz", label, sample_rate)
                # Resolve the actually-used device name for UI logging.
                try:
                    used_idx = stream_kwargs.get("device")
                    if used_idx is None:
                        used_idx = sd.default.device[0]
                    info = sd.query_devices(used_idx)
                    self.opened_device_name = (
                        f"{info.get('name', f'device {used_idx}')}  ({label}, {sample_rate} Hz)"
                    )
                except Exception:
                    self.opened_device_name = label
                return True
            except Exception as exc:
                logger.warning("AudioRecorder attempt %s failed: %s", label, exc)
                last_exc = exc
                # The stream object may exist if InputStream() succeeded but
                # .start() failed — close it so the device handle is freed.
                stream = self._stream
                self._stream = None
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        logger.debug("Closing failed stream attempt failed", exc_info=True)
                continue

        if last_exc is not None:
            self.last_error = f"{type(last_exc).__name__}: {last_exc}"
        else:
            self.last_error = "no audio devices available"
        return False

    def _build_attempt_chain(self, sd) -> List[Tuple[str, dict]]:
        """Return a list of (label, kwargs) device combos to try in order.

        We deliberately route through WASAPI / DirectSound only. MME's
        shared mode is buggy with Bluetooth devices, and WDM-KS exclusive
        mode locks the audio device for everyone else (including BT
        profile switching, which makes headphones go silent).
        """
        chain: List[Tuple[str, dict]] = []
        seen: Set[Tuple[Optional[int], int]] = set()
        sample_rates = []
        for rate in (self.sample_rate, 48000, 44100):
            if rate not in sample_rates:
                sample_rates.append(rate)

        def add_attempt(label: str, device: Optional[int]) -> None:
            for rate in sample_rates:
                key = (device, rate)
                if key in seen:
                    continue
                seen.add(key)
                kwargs = {"samplerate": rate}
                if device is not None:
                    kwargs["device"] = device
                chain.append((f"{label} ({rate} Hz)", kwargs))

        # Determine if user-saved device is on a safe host API. Some users
        # may have a stale device index from before we filtered the list.
        device_is_safe = False
        if self.device is not None:
            try:
                info = sd.query_devices(self.device)
                host_idx = info.get("hostapi", -1)
                host_name = ""
                if 0 <= host_idx < len(sd.query_hostapis()):
                    host_name = sd.query_hostapis()[host_idx].get("name", "").lower()
                if "wasapi" in host_name or "directsound" in host_name:
                    device_is_safe = True
            except Exception:
                pass

        # 1. User-selected device (only if it's on a safe host API).
        if self.device is not None and device_is_safe:
            add_attempt(f"device={self.device}", self.device)

        # 2. WASAPI default input — almost always works on modern Windows.
        try:
            host_apis = sd.query_hostapis()
            for host in host_apis:
                if "wasapi" in host.get("name", "").lower():
                    default_in = host.get("default_input_device", -1)
                    if default_in is not None and default_in >= 0:
                        add_attempt(f"WASAPI default (device={default_in})", default_in)
                    break
        except Exception:
            pass

        # 3. DirectSound default input — fallback if WASAPI is unavailable.
        try:
            for host in sd.query_hostapis():
                if "directsound" in host.get("name", "").lower():
                    default_in = host.get("default_input_device", -1)
                    if default_in is not None and default_in >= 0:
                        add_attempt(f"DirectSound default (device={default_in})", default_in)
                    break
        except Exception:
            pass

        # 4. Any remaining safe input device. This catches common cases where
        # Windows default points at a virtual/disabled mic, but a USB/Bluetooth
        # device is available and works.
        try:
            host_apis = sd.query_hostapis()
            for idx, dev in enumerate(sd.query_devices()):
                if dev.get("max_input_channels", 0) <= 0:
                    continue
                host_idx = dev.get("hostapi", -1)
                host_name = ""
                if 0 <= host_idx < len(host_apis):
                    host_name = host_apis[host_idx].get("name", "")
                host_lower = host_name.lower()
                if "wasapi" not in host_lower and "directsound" not in host_lower:
                    continue
                name = dev.get("name", f"device {idx}")
                add_attempt(f"{name} ({host_name}, device={idx})", idx)
        except Exception:
            pass

        return chain

    def stop(self):
        """Stop capture and return audio as float32 numpy array in [-1, 1].

        Returns None if no audio was captured.
        """
        if not self._recording or self._stream is None:
            return None

        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            logger.exception("Error closing audio stream")
        finally:
            self._stream = None
            self._recording = False

        with self._lock:
            chunks = self._chunks
            self._chunks = []
            self.last_stream_statuses = list(dict.fromkeys(self._stream_status_seen))

        if not chunks:
            return None

        try:
            import numpy as np
            audio_int16 = np.concatenate(chunks).flatten()
            if audio_int16.size == 0:
                return None
            audio_f32 = audio_int16.astype(np.float32) / 32768.0
            if self._active_sample_rate != self.sample_rate:
                old_len = int(audio_f32.size)
                new_len = max(1, int(round(old_len * self.sample_rate / self._active_sample_rate)))
                old_x = np.linspace(0.0, 1.0, num=old_len, endpoint=False)
                new_x = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
                audio_f32 = np.interp(new_x, old_x, audio_f32).astype(np.float32)
            return audio_f32
        except Exception:
            logger.exception("Failed to assemble audio array")
            return None

    def duration_seconds(self, audio) -> float:
        """Compute duration in seconds for a captured audio array."""
        if audio is None:
            return 0.0
        return float(len(audio)) / float(self.sample_rate)
