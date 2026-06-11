"""NVIDIA Parakeet ONNX engine manager.

Mirrors :class:`WhisperModelManager` so :class:`Transcriber` stays
engine-agnostic. The engine wraps the ``onnx_asr`` library which itself
delegates to ``onnxruntime`` for inference. Audio comes in as the same
numpy float32/16 kHz array Whisper expects; we serialise it to a temp
WAV because ``onnx_asr.recognize`` only accepts file paths.

Reference implementation: ``superwhisper0/parakeet_test/app_onnx.py`` —
identical model alias, identical providers, identical quantization knobs.

State machine identical to Whisper:
    UNLOADED -> LOADING -> READY -> TRANSCRIBING -> READY -> UNLOADED
                LOADING -> ERROR
                UNLOADED -> DOWNLOADING -> UNLOADED
"""

import gc
import logging
import os
import shutil
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import pyqtSignal, QTimer

from .base_asr_manager import (
    BaseASRManager,
    DownloadProgressReporter,
    STATE_UNLOADED,
    STATE_LOADING,
    STATE_DOWNLOADING,
    STATE_READY,
    STATE_TRANSCRIBING,
    STATE_ERROR,
)
from .cuda_setup import setup_cuda_dll_paths
from .deps import check_dependencies_for_engine
from .download_worker import download_hf_file_external
from ..core.constants import APPLICATION_PATH

logger = logging.getLogger('ClipGen')


# HuggingFace repository for the ONNX-converted Parakeet weights.
# This is what ``onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", ...)``
# pulls from on first run (model alias → istupakov repo).
PARAKEET_HF_REPO = "istupakov/parakeet-tdt-0.6b-v3-onnx"

# onnx_asr's alias for the Parakeet TDT 0.6B v3 model.
PARAKEET_MODEL_ALIAS = "nemo-parakeet-tdt-0.6b-v3"

# Approximate total weight size in MB — used for download progress display.
# Encoder data file dominates (~2.4 GB); decoder + encoder graph + vocab + config
# add another ~115 MB.
PARAKEET_TOTAL_MB = 2515

# Files we expect inside a healthy snapshot folder. The ``encoder-model.onnx.data``
# is the multi-gigabyte external-tensor file that goes alongside the graph.
REQUIRED_PARAKEET_FILES = (
    "config.json",
    "encoder-model.onnx",
    "encoder-model.onnx.data",
    "decoder_joint-model.onnx",
    "vocab.txt",
)

# Optional int8-quantized variants. Present in some snapshots; we treat
# them as bonus weights to download when the user picks ``quantization=int8``.
INT8_PARAKEET_FILES = (
    "encoder-model.int8.onnx",
    "encoder-model.int8.onnx.data",
    "decoder_joint-model.int8.onnx",
)

# Files ignored entirely (READMEs, license, etc.).
SKIP_DOWNLOAD_SUFFIXES = (".md", ".gitattributes")


def _models_dir() -> str:
    """Local model cache root: ``<program>/Models/parakeet/``.

    Kept separate from Whisper's ``Models/`` root so the user can wipe one
    engine's weights without touching the other.
    """
    path = os.path.join(APPLICATION_PATH, "Models", "parakeet")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def _repo_cache_dir() -> str:
    """HF-style cache folder for the Parakeet repo."""
    return os.path.join(_models_dir(), "models--" + PARAKEET_HF_REPO.replace("/", "--"))


def _validate_snapshot(snapshot_dir: str) -> List[str]:
    """Return list of validation errors for a downloaded Parakeet snapshot."""
    errors: List[str] = []
    if not os.path.isdir(snapshot_dir):
        return [f"snapshot folder does not exist: {snapshot_dir}"]
    for filename in REQUIRED_PARAKEET_FILES:
        path = os.path.join(snapshot_dir, filename)
        if not os.path.isfile(path):
            errors.append(f"missing {filename}")
            continue
        try:
            size = os.path.getsize(path)
        except OSError as exc:
            errors.append(f"cannot stat {filename}: {exc}")
            continue
        if size <= 0:
            errors.append(f"{filename} is empty")
    # encoder-model.onnx.data must be the heavy one — sanity-check size.
    big_path = os.path.join(snapshot_dir, "encoder-model.onnx.data")
    if os.path.isfile(big_path):
        try:
            if os.path.getsize(big_path) < 100 * 1024 * 1024:
                errors.append("encoder-model.onnx.data is suspiciously small")
        except OSError:
            pass
    return errors


def get_parakeet_snapshot_path() -> Optional[str]:
    """Return the newest valid local snapshot folder, or None."""
    snapshots = os.path.join(_repo_cache_dir(), "snapshots")
    if not os.path.isdir(snapshots):
        return None
    candidates: List[Tuple[float, str]] = []
    try:
        for name in os.listdir(snapshots):
            path = os.path.join(snapshots, name)
            if not os.path.isdir(path):
                continue
            if _validate_snapshot(path):
                continue
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                mtime = 0.0
            candidates.append((mtime, path))
    except OSError:
        return None
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def is_parakeet_downloaded() -> bool:
    """True when a complete Parakeet snapshot is on disk."""
    return get_parakeet_snapshot_path() is not None


def cleanup_stale_parakeet_files(older_than_seconds: int = 600) -> int:
    """Remove stale zero-byte/lock partial download files."""
    base = _repo_cache_dir()
    if not os.path.isdir(base):
        return 0
    removed = 0
    now = time.time()
    for root, _dirs, files in os.walk(base):
        for filename in files:
            if not (filename.endswith(".incomplete") or filename.endswith(".lock")):
                continue
            path = os.path.join(root, filename)
            try:
                age = now - os.path.getmtime(path)
                size = os.path.getsize(path)
            except OSError:
                continue
            if age < older_than_seconds:
                continue
            if filename.endswith(".incomplete") and size > 0:
                continue
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass

    lock_root = os.path.join(_models_dir(), ".locks", os.path.basename(base))
    if os.path.isdir(lock_root):
        for root, _dirs, files in os.walk(lock_root):
            for filename in files:
                if not filename.endswith(".lock"):
                    continue
                path = os.path.join(root, filename)
                try:
                    age = now - os.path.getmtime(path)
                except OSError:
                    continue
                if age < older_than_seconds:
                    continue
                try:
                    os.remove(path)
                    removed += 1
                except OSError:
                    pass
        try:
            if not os.listdir(lock_root):
                shutil.rmtree(lock_root)
        except OSError:
            pass
    return removed


# Provider strings as displayed in the UI → onnxruntime EP name list.
# Each chain ends with CPUExecutionProvider so onnxruntime falls back if the
# preferred provider can't initialise.
_PROVIDER_CHAINS = {
    "CUDA": ["CUDAExecutionProvider", "CPUExecutionProvider"],
    "DirectML": ["DmlExecutionProvider", "CPUExecutionProvider"],
    "TensorRT": ["TensorrtExecutionProvider", "CUDAExecutionProvider",
                 "CPUExecutionProvider"],
    "CPU": ["CPUExecutionProvider"],
}


class _ParakeetSegment:
    """Whisper-segment-shaped adapter so ``filters.py`` works unchanged.

    ``filters.py`` reads four attributes via ``getattr(seg, attr, 0.0)``:
    ``text``, ``avg_logprob``, ``no_speech_prob``, ``compression_ratio``.
    Parakeet doesn't surface any of those confidence stats, so we fill in
    neutral values that fall safely inside the default thresholds and the
    blacklist still does its job on the ``text`` field.
    """

    __slots__ = ("text", "avg_logprob", "no_speech_prob", "compression_ratio",
                 "start", "end")

    def __init__(self, text: str, audio_duration: Optional[float] = None) -> None:
        self.text = text
        self.avg_logprob = -0.3      # comfortably above min threshold (-1.0)
        self.no_speech_prob = 0.0    # we got non-empty text → not silence
        self.compression_ratio = 1.5 # well below upper bound (2.4)
        self.start = 0.0
        self.end = float(audio_duration or 0.0)


def _extract_text(result: Any) -> str:
    """Pull text out of whatever ``model.recognize`` returned.

    onnx_asr's return type isn't fully stable across versions: it may be a
    bare string, a list of strings, an object with ``.text`` /
    ``.transcript`` / ``.tokens``, or a tuple. Match the same defensive
    walker the standalone parakeet_test app uses.
    """
    if result is None:
        return ""
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, (list, tuple)) and result:
        return _extract_text(result[0])
    for attr in ("text", "transcript", "tokens"):
        if hasattr(result, attr):
            v = getattr(result, attr)
            extracted = _extract_text(v)
            if extracted:
                return extracted
    return str(result).strip()


def _format_exception(exc: Exception) -> str:
    """Return a GUI-friendly exception string, even for empty native errors."""
    text = str(exc).strip()
    if text:
        return f"{type(exc).__name__}: {text}"
    return repr(exc)


class ParakeetModelManager(BaseASRManager):
    """Owns the Parakeet ONNX session and exposes the ASR contract."""

    engine_name = "parakeet"
    # Parakeet RNN-T can produce partial hypotheses on a growing buffer;
    # the foundation is here even though :class:`Transcriber` only wires
    # in the actual loop in a follow-up change.
    supports_streaming = True

    _idle_reset_requested = pyqtSignal()
    _idle_stop_requested = pyqtSignal()

    INFO_COLOR = "#A3BFFA"
    ERROR_COLOR = "#FF5F57"
    SUCCESS_COLOR = "#28A745"

    def __init__(self, config: Dict[str, Any], lang: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.config = config
        self.lang = lang

        self._state = STATE_UNLOADED
        self._model: Optional[Any] = None
        self._model_lock = threading.RLock()
        self._loaded_signature: Optional[Tuple[str, str, str]] = None
        self._actual_provider: Optional[str] = None
        self._actual_quant: Optional[str] = None
        self._last_load_seconds: Optional[float] = None
        self._load_generation = 0
        self._download_cancel = threading.Event()
        self._last_fallback_errors: List[Tuple[str, str, str]] = []

        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._on_idle_timeout)
        self._idle_reset_requested.connect(self._reset_idle_timer)
        self._idle_stop_requested.connect(self._stop_idle_timer)

    # ------------------------------------------------------------------ helpers

    def _tr_section(self) -> Dict[str, Any]:
        return self.config.get("transcription", {})

    def _parakeet_section(self) -> Dict[str, Any]:
        sub = self._tr_section().get("parakeet")
        return sub if isinstance(sub, dict) else {}

    def _logs_section(self) -> Dict[str, Any]:
        return self.lang.get("logs", {})

    def _emit_log(self, key: str, color: str = INFO_COLOR, **fmt) -> None:
        template = self._logs_section().get(key, key)
        try:
            msg = template.format(**fmt) if fmt else template
        except (KeyError, IndexError, ValueError):
            msg = template
        self.log_signal.emit(msg, color)

    def _set_state(self, state: str) -> None:
        if self._state != state:
            self._state = state
            self.state_changed.emit(state)

    def get_state(self) -> str:
        return self._state

    def is_loaded(self) -> bool:
        return self._state in (STATE_READY, STATE_TRANSCRIBING) and self._model is not None

    def requires_download(self) -> bool:
        """True when Parakeet weights are not on disk yet (see Whisper
        manager: hotkey presses must not trigger silent downloads)."""
        if (self._parakeet_section().get("model_path_override") or "").strip():
            return False
        return not is_parakeet_downloaded()

    def get_runtime_info(self) -> Dict[str, Any]:
        return {
            "engine": self.engine_name,
            "state": self._state,
            "model": (self._parakeet_section().get("model") if not self.is_loaded()
                      else (self._loaded_signature[0] if self._loaded_signature else None)),
            "device": self._actual_provider,
            "compute_type": self._actual_quant or "",
            "load_seconds": self._last_load_seconds,
            "fallback_errors": list(self._last_fallback_errors),
        }

    def update_lang(self, lang: Dict[str, Any]) -> None:
        self.lang = lang

    # ------------------------------------------------------------------ load

    def load_async(self) -> Optional[threading.Thread]:
        with self._model_lock:
            if self._state in (STATE_LOADING, STATE_TRANSCRIBING):
                return None
            if self.is_loaded():
                return None
        thread = threading.Thread(target=self._load_blocking, daemon=True,
                                  name="ParakeetLoad")
        thread.start()
        return thread

    def load_blocking(self) -> bool:
        return self._load_blocking()

    def download_async(self) -> threading.Thread:
        thread = threading.Thread(target=self._download_only, daemon=True,
                                  name="ParakeetDownloadOnly")
        thread.start()
        return thread

    def cancel_download(self) -> None:
        self._download_cancel.set()
        with self._model_lock:
            self._load_generation += 1
        self._emit_log("transcription_download_cancel_requested", self.INFO_COLOR)

    def cancel_transcription(self) -> None:
        """Best-effort cancel — we cannot interrupt onnxruntime mid-call,
        so we just flip state back to READY once inference returns. The
        ``_load_generation`` bump prevents stale completions from racing."""
        with self._model_lock:
            if self._state != STATE_TRANSCRIBING:
                return
            self._load_generation += 1
        self._emit_log("transcription_cancelled", self.INFO_COLOR)

    def _download_only(self) -> bool:
        path_override = (self._parakeet_section().get("model_path_override") or "").strip()
        if path_override:
            return True
        if is_parakeet_downloaded():
            return True
        self._set_state(STATE_DOWNLOADING)
        try:
            ok = self._download_with_progress()
        finally:
            self._set_state(STATE_UNLOADED)
            self.info_signal.emit(self.get_runtime_info())
        return ok

    def _load_blocking(self) -> bool:
        with self._model_lock:
            self._load_generation += 1
            generation = self._load_generation

        # Make CUDA DLLs visible to onnxruntime-gpu (same setup Whisper uses).
        setup_cuda_dll_paths()

        missing = check_dependencies_for_engine("parakeet", include_cuda=False)
        if missing:
            self._emit_log("transcription_deps_missing", self.ERROR_COLOR)
            self._set_state(STATE_ERROR)
            return False

        cfg = self._parakeet_section()
        path_override = (cfg.get("model_path_override") or "").strip()
        providers_pref = cfg.get("providers") or ["CUDA", "CPU"]
        if isinstance(providers_pref, str):
            providers_pref = [providers_pref]
        quant_pref = (cfg.get("quantization") or "").strip()

        # Make sure weights are on disk before loading.
        if not path_override and not is_parakeet_downloaded():
            removed = cleanup_stale_parakeet_files()
            if removed:
                logger.info("Cleaned %s stale Parakeet download files", removed)
            self._set_state(STATE_DOWNLOADING)
            ok = self._download_with_progress()
            if not ok:
                self._set_state(STATE_ERROR)
                return False

        snapshot_dir = path_override or get_parakeet_snapshot_path()
        if not snapshot_dir or not os.path.isdir(snapshot_dir):
            self._emit_log("transcription_load_failed", self.ERROR_COLOR,
                           error="parakeet snapshot path missing")
            self._set_state(STATE_ERROR)
            return False

        self._set_state(STATE_LOADING)
        self._emit_log("transcription_model_loading", self.INFO_COLOR,
                       model=PARAKEET_MODEL_ALIAS)
        start = time.time()

        try:
            import onnx_asr  # type: ignore
        except ImportError:
            self._emit_log("transcription_deps_missing", self.ERROR_COLOR)
            self._set_state(STATE_ERROR)
            return False

        # Try each preferred provider (CUDA → DirectML → CPU as configured).
        attempt_errors: List[Tuple[str, str, str]] = []
        last_error: Optional[Exception] = None
        for provider_choice in providers_pref:
            chain = _PROVIDER_CHAINS.get(provider_choice, ["CPUExecutionProvider"])
            try:
                with self._model_lock:
                    if generation != self._load_generation:
                        return False
                    if self._model is not None:
                        del self._model
                        self._model = None
                        gc.collect()
                    kwargs: Dict[str, Any] = {
                        "path": snapshot_dir,
                        "providers": chain,
                    }
                    if quant_pref:
                        kwargs["quantization"] = quant_pref
                    self._model = onnx_asr.load_model(PARAKEET_MODEL_ALIAS, **kwargs)
                    self._loaded_signature = (PARAKEET_MODEL_ALIAS, provider_choice,
                                              quant_pref or "default")
                    self._actual_provider = provider_choice
                    self._actual_quant = quant_pref or ""
                self._warmup(snapshot_dir)
                self._last_load_seconds = time.time() - start
                self._last_fallback_errors = attempt_errors
                self._set_state(STATE_READY)
                self.info_signal.emit(self.get_runtime_info())
                self._idle_reset_requested.emit()
                if provider_choice != providers_pref[0]:
                    self._emit_log("transcription_cuda_unavailable", self.INFO_COLOR)
                return True
            except Exception as exc:
                last_error = exc
                attempt_errors.append((provider_choice, quant_pref or "default", str(exc)))
                logger.warning("Parakeet load failed for provider %s: %s",
                               provider_choice, exc)
                continue

        # All providers failed.
        err_msg = str(last_error) if last_error else "unknown"
        self._last_fallback_errors = attempt_errors
        self._emit_log("transcription_load_failed", self.ERROR_COLOR, error=err_msg)
        for provider, quant, error in attempt_errors[:4]:
            self.log_signal.emit(f"  {provider}/{quant}: {error}", "#888888")
        self._set_state(STATE_ERROR)
        return False

    def _download_with_progress(self) -> bool:
        """Pull weights file-by-file via the shared download_worker subprocess.

        We list the repo via ``huggingface_hub.HfApi`` first, then fetch each
        file in its own subprocess so the user gets a progress line per file
        and cancellation is cooperative between files.
        """
        try:
            import importlib
            hf = importlib.import_module("huggingface_hub")
        except ImportError:
            self._emit_log("transcription_deps_missing", self.ERROR_COLOR)
            return False

        target_root = _models_dir()
        self._download_cancel.clear()
        cleanup_stale_parakeet_files()

        # Engine-specific copy first; falls back to the neutral key.
        if "transcription_downloading_parakeet" in self._logs_section():
            self._emit_log("transcription_downloading_parakeet", self.INFO_COLOR,
                           model=PARAKEET_MODEL_ALIAS)
        else:
            self._emit_log("transcription_downloading", self.INFO_COLOR,
                           model=PARAKEET_MODEL_ALIAS)

        try:
            os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")
            os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")
            api = hf.HfApi()
            info = api.model_info(repo_id=PARAKEET_HF_REPO)
            siblings = getattr(info, "siblings", []) or []
            quant_pref = (self._parakeet_section().get("quantization") or "").strip()
            files: List[Tuple[str, Optional[int]]] = []
            for sibling in siblings:
                name = getattr(sibling, "rfilename", "")
                if not name or name.startswith("."):
                    continue
                lower = name.lower()
                if lower.endswith(SKIP_DOWNLOAD_SUFFIXES):
                    continue
                # Skip int8 variants when the user didn't pick int8, and skip
                # default variants when they did. Keep config.json + vocab.txt
                # always.
                is_int8 = ".int8." in lower
                if is_int8 and quant_pref != "int8":
                    continue
                if not is_int8 and quant_pref == "int8":
                    # int8 mode still wants the encoder.data file because
                    # onnx external-data references resolve at load time.
                    if name not in REQUIRED_PARAKEET_FILES:
                        continue
                size = getattr(sibling, "size", None)
                files.append((name, int(size) if isinstance(size, int) else None))
            if not files:
                raise RuntimeError(f"No downloadable model files found for {PARAKEET_HF_REPO}")

            total_bytes = sum(size or 0 for _name, size in files)
            done_bytes = 0
            for index, (filename, size) in enumerate(files, start=1):
                if self._download_cancel.is_set():
                    self._emit_log("transcription_download_cancelled", self.INFO_COLOR)
                    return False

                # Header line with overall progress + per-file size hint.
                size_suffix = f" ({size / 1024 / 1024:.0f} MB)" if size else ""
                if total_bytes > 0:
                    pct = int(done_bytes / total_bytes * 100)
                    self.log_signal.emit(
                        f"  {pct}%  file {index}/{len(files)}: {filename}{size_suffix}",
                        "#888888",
                    )
                else:
                    self.log_signal.emit(
                        f"  file {index}/{len(files)}: {filename}{size_suffix}",
                        "#888888",
                    )

                # Per-file progress reporter — see DownloadProgressReporter
                # for the throttle/speed logic. A fresh instance per file
                # so percent state doesn't leak between files.
                reporter = DownloadProgressReporter(self.log_signal.emit)

                ok, error = download_hf_file_external(
                    repo_id=PARAKEET_HF_REPO,
                    filename=filename,
                    cache_dir=target_root,
                    cancel_event=self._download_cancel,
                    timeout=None,
                    expected_size=size,
                    on_progress=reporter,
                )
                if not ok:
                    if error == "cancelled":
                        self._emit_log("transcription_download_cancelled", self.INFO_COLOR)
                        return False
                    raise RuntimeError(error)
                done_bytes += size or 0
            if self._download_cancel.is_set():
                self._emit_log("transcription_download_cancelled", self.INFO_COLOR)
                return False
        except Exception as exc:
            logger.exception("Parakeet download failed")
            self._emit_log("transcription_download_failed", self.ERROR_COLOR,
                           error=str(exc))
            return False

        snapshot = get_parakeet_snapshot_path()
        if not snapshot:
            self._emit_log(
                "transcription_download_failed",
                self.ERROR_COLOR,
                error="download finished but no valid model snapshot was found",
            )
            return False
        self.log_signal.emit("  100%", "#888888")
        self._emit_log("transcription_download_done", self.SUCCESS_COLOR,
                       model=PARAKEET_MODEL_ALIAS)
        return True

    def _warmup(self, snapshot_dir: str) -> None:
        """Fire one zero-amplitude transcribe so first real call stays fast.

        onnxruntime JIT-compiles the GPU graph on first inference; without
        the warmup the initial user-facing transcription takes 2-3x as long.
        """
        try:
            import numpy as np
            import scipy.io.wavfile as wav_io  # type: ignore
            tmp = tempfile.NamedTemporaryFile(
                suffix=".wav", prefix="clipgen_pk_warmup_", delete=False
            )
            tmp.close()
            try:
                silence = np.zeros(16000, dtype=np.int16)  # 1 s silence
                wav_io.write(tmp.name, 16000, silence)
                _ = self._model.recognize(tmp.name)
            finally:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass
        except Exception:
            logger.debug("Parakeet warmup failed (non-fatal)", exc_info=True)

    # ------------------------------------------------------------------ unload

    def unload(self, idle_triggered: bool = False) -> None:
        with self._model_lock:
            self._load_generation += 1
            if self._model is None and self._state == STATE_UNLOADED:
                return
            self._model = None
            self._loaded_signature = None
            self._actual_provider = None
            self._actual_quant = None
            self._last_load_seconds = None
            gc.collect()

        self._idle_stop_requested.emit()
        if idle_triggered:
            minutes = self._tr_section().get("auto_unload_minutes", 5)
            self._emit_log("transcription_model_unloaded_idle",
                           self.INFO_COLOR, minutes=minutes)
        else:
            self._emit_log("transcription_model_unloaded", self.INFO_COLOR)
        self._set_state(STATE_UNLOADED)
        self.info_signal.emit(self.get_runtime_info())

    # ------------------------------------------------------------------ idle

    def _reset_idle_timer(self) -> None:
        self._idle_timer.stop()
        minutes = int(self._tr_section().get("auto_unload_minutes", 5) or 0)
        if minutes > 0 and self._state == STATE_READY:
            self._idle_timer.start(minutes * 60 * 1000)

    def _stop_idle_timer(self) -> None:
        self._idle_timer.stop()

    def _on_idle_timeout(self) -> None:
        if self._state == STATE_READY:
            self.unload(idle_triggered=True)

    def reset_idle(self) -> None:
        try:
            self._idle_reset_requested.emit()
        except Exception:
            pass

    # ------------------------------------------------------------------ inference

    def transcribe(
        self,
        audio,  # numpy float32, mono, 16 kHz
        language: Optional[str] = None,
        initial_prompt: Optional[str] = None,
        audio_duration: Optional[float] = None,
    ) -> Tuple[Optional[List[Any]], Optional[Dict[str, Any]]]:
        with self._model_lock:
            if self._state != STATE_READY or self._model is None:
                return None, None
            model = self._model
            self._set_state(STATE_TRANSCRIBING)

        wav_path: Optional[str] = None
        try:
            import numpy as np
            import scipy.io.wavfile as wav_io  # type: ignore

            # Persist the captured audio to a temp WAV so onnx_asr can read it.
            # Float32 in [-1, 1] → int16 PCM (Parakeet/onnx_asr expects PCM).
            audio_int16 = np.clip(audio * 32767.0, -32768, 32767).astype(np.int16)
            tmp = tempfile.NamedTemporaryFile(
                suffix=".wav", prefix="clipgen_pk_", delete=False
            )
            wav_path = tmp.name
            tmp.close()
            wav_io.write(wav_path, 16000, audio_int16)

            try:
                result = model.recognize(wav_path)
            except Exception as exc:
                logger.exception("Parakeet transcription failed")
                with self._model_lock:
                    if self._state == STATE_TRANSCRIBING:
                        self._set_state(STATE_ERROR)
                self._emit_log(
                    "transcription_failed",
                    self.ERROR_COLOR,
                    error=_format_exception(exc),
                )
                return None, None

            text = _extract_text(result)
            if not text:
                return [], {
                    "language": language or "auto",
                    "duration": float(audio_duration or 0.0),
                }

            segment = _ParakeetSegment(text=text, audio_duration=audio_duration)
            info = {
                "language": language or "auto",
                "language_probability": 1.0,
                "duration": float(audio_duration or 0.0),
                "duration_after_vad": float(audio_duration or 0.0),
            }
            return [segment], info
        except Exception as exc:
            logger.exception("Parakeet transcription failed")
            with self._model_lock:
                if self._state == STATE_TRANSCRIBING:
                    self._set_state(STATE_ERROR)
            self._emit_log(
                "transcription_failed",
                self.ERROR_COLOR,
                error=_format_exception(exc),
            )
            return None, None
        finally:
            if wav_path:
                try:
                    os.unlink(wav_path)
                except OSError:
                    pass
            with self._model_lock:
                if self._state == STATE_TRANSCRIBING and self._model is model:
                    self._set_state(STATE_READY)
            self.reset_idle()

    # ------------------------------------------------------------------ shutdown

    def shutdown(self, release_model: bool = False) -> None:
        try:
            self._idle_timer.stop()
        except Exception:
            pass
        with self._model_lock:
            self._load_generation += 1
        if release_model:
            self.unload()
