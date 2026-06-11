"""Whisper model lifecycle manager.

Responsibilities:
• Load the configured faster-whisper model with GPU->CPU fallback chain.
• Keep it cached for fast inference, behind a lock.
• Auto-unload after N minutes of idle to free VRAM.
• Run inference in worker threads; emit Qt signals for UI updates.

State machine:
    UNLOADED -> LOADING -> READY -> TRANSCRIBING -> READY -> UNLOADED
                LOADING -> ERROR
"""

import gc
import logging
import os
import shutil
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
from .deps import check_dependencies, check_runtime_health
from .download_worker import download_hf_file_external
from .worker_client import WhisperWorkerClient
from ..core.constants import APPLICATION_PATH

logger = logging.getLogger('ClipGen')


def _models_dir() -> str:
    """Local model cache: ``<program>/Models/``.

    Stored next to the .exe (or repo root in dev) so the user can drop in
    pre-downloaded models manually instead of waiting for HuggingFace.
    """
    path = os.path.join(APPLICATION_PATH, "Models")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


REQUIRED_MODEL_FILES = (
    "model.bin",
    "config.json",
    "tokenizer.json",
)

OPTIONAL_MODEL_FILES = (
    "vocabulary.txt",
    "preprocessor_config.json",
)

DOWNLOAD_FILE_EXTENSIONS = (
    ".bin",
    ".json",
    ".txt",
    ".model",
)


def _repo_cache_dir(repo: str) -> str:
    return os.path.join(_models_dir(), "models--" + repo.replace("/", "--"))


def _snapshot_validation_errors(snapshot_dir: str) -> List[str]:
    """Return validation errors for a faster-whisper snapshot folder."""
    errors: List[str] = []
    if not os.path.isdir(snapshot_dir):
        return [f"snapshot folder does not exist: {snapshot_dir}"]

    for filename in REQUIRED_MODEL_FILES:
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

    if not any(os.path.isfile(os.path.join(snapshot_dir, name)) for name in OPTIONAL_MODEL_FILES):
        errors.append("missing vocabulary.txt or preprocessor_config.json")

    model_bin = os.path.join(snapshot_dir, "model.bin")
    if os.path.isfile(model_bin):
        try:
            if os.path.getsize(model_bin) < 10 * 1024 * 1024:
                errors.append("model.bin is suspiciously small")
        except OSError:
            pass

    return errors


def get_model_snapshot_path(model_name: str) -> Optional[str]:
    """Return the newest valid local snapshot path for a configured model."""
    repo = MODEL_REPO_MAP.get(model_name, model_name)
    if "/" not in repo:
        return None
    snapshots = os.path.join(_repo_cache_dir(repo), "snapshots")
    if not os.path.isdir(snapshots):
        return None

    candidates: List[Tuple[float, str]] = []
    try:
        for name in os.listdir(snapshots):
            path = os.path.join(snapshots, name)
            if not os.path.isdir(path):
                continue
            if _snapshot_validation_errors(path):
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


def is_model_downloaded(model_name: str) -> bool:
    """Check whether a complete model snapshot is already on disk.

    HuggingFace caches under ``Models/models--<owner>--<repo>/``. A snapshot
    is considered usable only when the core faster-whisper files exist.
    """
    return get_model_snapshot_path(model_name) is not None


def cleanup_stale_download_files(model_name: str, older_than_seconds: int = 600) -> int:
    """Remove stale zero-byte partial download files for the selected model.

    This intentionally avoids deleting non-empty partial blobs because
    HuggingFace can resume them. Zero-byte leftovers are usually from a
    frozen-app hang before any network bytes were written.
    """
    repo = MODEL_REPO_MAP.get(model_name, model_name)
    if "/" not in repo:
        return 0
    base = _repo_cache_dir(repo)
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

    # Best effort: remove stale zero-byte lock files in HuggingFace's global
    # cache lock folder for this repo.
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


# State name constants are defined in base_asr_manager and re-exported above
# so any callers doing ``from .model_manager import STATE_READY`` keep working.


# faster-whisper repository IDs for each user-facing model name.
MODEL_REPO_MAP = {
    "large-v3": "Systran/faster-whisper-large-v3",
    # large-v3-turbo: 5–6x faster than large-v3 with a ~1–2% WER regression.
    # Systran has not published a turbo CT2 conversion as of May 2026; the
    # ``deepdml`` repo is the most-used community port (FP16 weights, same
    # file layout faster-whisper expects).
    "large-v3-turbo": "deepdml/faster-whisper-large-v3-turbo-ct2",
    "medium": "Systran/faster-whisper-medium",
    "small": "Systran/faster-whisper-small",
    "base": "Systran/faster-whisper-base",
    "tiny": "Systran/faster-whisper-tiny",
}


class WhisperModelManager(BaseASRManager):
    """Owns the Whisper model and exposes a thread-safe transcribe() API."""

    engine_name = "whisper"
    supports_streaming = False

    # state_changed / log_signal / info_signal come from BaseASRManager.
    # Internal-only signals stay here.
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
        self._model = None
        self._model_lock = threading.RLock()
        self._loaded_signature: Optional[tuple] = None  # (model, device, compute_type)
        self._actual_device: Optional[str] = None
        self._actual_compute: Optional[str] = None
        self._last_load_seconds: Optional[float] = None
        self._load_generation = 0
        self._download_cancel = threading.Event()
        self._last_fallback_errors: List[Tuple[str, str, str]] = []
        self._worker: Optional[WhisperWorkerClient] = None
        self._worker_loaded = False

        # Idle timer must live on the main thread; we trigger via signals.
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._on_idle_timeout)
        self._idle_reset_requested.connect(self._reset_idle_timer)
        self._idle_stop_requested.connect(self._stop_idle_timer)

    # ------------------------------------------------------------------ helpers

    def _tr_section(self) -> Dict[str, Any]:
        """Shared transcription config (engine-agnostic keys)."""
        return self.config.get("transcription", {})

    def _whisper_section(self) -> Dict[str, Any]:
        """Whisper-specific config (post-migration nested under 'whisper').

        Falls back to the flat ``transcription.*`` keys for the brief window
        between in-memory upgrade and the migration save — keeps the loader
        robust if migration hasn't run for any reason.
        """
        tr = self.config.get("transcription", {})
        nested = tr.get("whisper")
        return nested if isinstance(nested, dict) else tr

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
        return (
            self._state in (STATE_READY, STATE_TRANSCRIBING)
            and (self._model is not None or self._worker_loaded)
        )

    def requires_download(self) -> bool:
        """True when the configured model weights are not on disk yet.

        Used by the hotkey path: a voice key press must never silently
        kick off a multi-GB download — that belongs to the Settings
        button where the user sees progress and can cancel.
        """
        tr = self._whisper_section()
        if (tr.get("model_path_override", "") or "").strip():
            return False
        return not is_model_downloaded(tr.get("model", "large-v3"))

    def get_runtime_info(self) -> Dict[str, Any]:
        return {
            "engine": self.engine_name,
            "state": self._state,
            "model": (self._whisper_section().get("model") if not self.is_loaded()
                      else (self._loaded_signature[0] if self._loaded_signature else None)),
            "device": self._actual_device,
            "compute_type": self._actual_compute,
            "load_seconds": self._last_load_seconds,
            "fallback_errors": list(self._last_fallback_errors),
        }

    def update_lang(self, lang: Dict[str, Any]) -> None:
        self.lang = lang

    # ------------------------------------------------------------------ load

    def load_async(self) -> threading.Thread:
        """Kick off model loading in a worker thread."""
        with self._model_lock:
            if self._state in (STATE_LOADING, STATE_TRANSCRIBING):
                return None  # already busy
            if self.is_loaded():
                return None  # already loaded

        thread = threading.Thread(target=self._load_blocking, daemon=True,
                                  name="WhisperModelLoad")
        thread.start()
        return thread

    def load_blocking(self) -> bool:
        """Load the model synchronously. Returns True on success."""
        return self._load_blocking()

    def download_async(self) -> threading.Thread:
        """Download the configured model in a worker thread (no VRAM load).

        Returns the worker thread so the caller can join if needed.
        """
        thread = threading.Thread(target=self._download_only,
                                  daemon=True, name="WhisperDownloadOnly")
        thread.start()
        return thread

    def cancel_download(self) -> None:
        """Request cancellation of the active model download."""
        self._download_cancel.set()
        with self._model_lock:
            self._load_generation += 1
        self._emit_log("transcription_download_cancel_requested", self.INFO_COLOR)

    def cancel_transcription(self) -> None:
        """Cancel active inference by terminating the isolated worker."""
        worker = None
        with self._model_lock:
            if self._state != STATE_TRANSCRIBING:
                return
            self._load_generation += 1
            worker = self._worker
            self._worker = None
            self._worker_loaded = False
            self._model = None
            self._loaded_signature = None
            self._actual_device = None
            self._actual_compute = None
            self._last_load_seconds = None
            self._set_state(STATE_UNLOADED)
        if worker is not None:
            worker.shutdown(kill=True)
        self._emit_log("transcription_cancelled", self.INFO_COLOR)
        self.info_signal.emit(self.get_runtime_info())

    def _download_only(self) -> bool:
        """Download the configured model without loading it into memory."""
        tr = self._whisper_section()
        model_name = tr.get("model", "large-v3")
        path_override = tr.get("model_path_override", "").strip()
        if path_override:
            return True  # nothing to download — user supplied a local path
        if is_model_downloaded(model_name):
            return True  # already on disk
        repo = MODEL_REPO_MAP.get(model_name, model_name)
        self._set_state(STATE_DOWNLOADING)
        try:
            ok = self._download_model_with_progress(model_name, repo)
        finally:
            # Return to UNLOADED so the UI shows the load button as enabled
            # for the freshly-downloaded model.
            self._set_state(STATE_UNLOADED)
            self.info_signal.emit(self.get_runtime_info())
        return ok

    def _load_blocking(self) -> bool:
        with self._model_lock:
            self._load_generation += 1
            generation = self._load_generation

        tr = self._whisper_section()
        missing = check_dependencies(include_cuda=False)
        if missing:
            self._emit_log("transcription_deps_missing", self.ERROR_COLOR)
            self._set_state(STATE_ERROR)
            return False

        # Make CUDA libraries findable if installed via pip.
        setup_cuda_dll_paths()

        model_name = tr.get("model", "large-v3")
        device_pref = tr.get("device", "auto")
        compute_pref = tr.get("compute_type", "float16")

        health = check_runtime_health(include_cuda=device_pref != "cpu")
        if not health.get("ok", False):
            logger.warning("Transcription runtime health warnings/errors: %s", health)
            errors = "; ".join(str(e) for e in health.get("errors", [])[:3])
            if errors:
                self.log_signal.emit(f"  Runtime check: {errors}", self.ERROR_COLOR)

        repo = MODEL_REPO_MAP.get(model_name, model_name)
        path_override = tr.get("model_path_override", "").strip()
        model_target = path_override or repo
        local_files_only = bool(not path_override and get_model_snapshot_path(model_name))
        use_worker = bool(tr.get("isolate_inference_process", True))

        # Download phase first (with progress) if the weights aren't on disk
        # yet. This way the user sees a real progress bar in the log instead
        # of a long silent stall before "Loading...".
        if not path_override and not is_model_downloaded(model_name):
            removed = cleanup_stale_download_files(model_name)
            if removed:
                logger.info("Cleaned %s stale Whisper download files", removed)
            self._set_state(STATE_DOWNLOADING)
            ok = self._download_model_with_progress(model_name, repo)
            if not ok:
                self._set_state(STATE_ERROR)
                return False
        if not path_override:
            local_snapshot = get_model_snapshot_path(model_name)
            if local_snapshot:
                model_target = local_snapshot
                local_files_only = True

        self._set_state(STATE_LOADING)
        self._emit_log("transcription_model_loading",
                       self.INFO_COLOR, model=model_name)
        start = time.time()

        # Build fallback chain.
        attempts = []
        if device_pref == "cpu":
            attempts.append(("cpu", "int8"))
        elif device_pref == "cuda":
            for compute in (compute_pref, "int8_float16", "int8"):
                if ("cuda", compute) not in attempts:
                    attempts.append(("cuda", compute))
            attempts.append(("cpu", "int8"))
        else:  # auto
            for compute in (compute_pref, "int8_float16", "int8"):
                if ("cuda", compute) not in attempts:
                    attempts.append(("cuda", compute))
            attempts.append(("cpu", "int8"))

        WhisperModel = None  # noqa: N806
        if not use_worker:
            try:
                # Hidden from PyInstaller via importlib so the .exe does not
                # bundle the ~1.5 GB faster-whisper/CTranslate2/CUDA stack.
                import importlib
                fw_module = importlib.import_module("faster_whisper")
                WhisperModel = fw_module.WhisperModel  # noqa: N806
            except ImportError:
                self._emit_log("transcription_deps_missing", self.ERROR_COLOR)
                self._set_state(STATE_ERROR)
                return False

        last_error: Optional[Exception] = None
        attempt_errors: List[Tuple[str, str, str]] = []
        for device, compute in attempts:
            try:
                # Note: local_files_only=False so first launch can download.
                # download_root steers HuggingFace's cache into our local
                # ``Models/`` folder so the user can manage downloaded
                # weights side-by-side with the .exe (and pre-seed them
                # manually if desired).
                with self._model_lock:
                    if generation != self._load_generation:
                        return False
                    if self._model is not None:
                        del self._model
                        self._model = None
                        gc.collect()
                    if use_worker:
                        if self._worker is None:
                            self._worker = WhisperWorkerClient()
                        ok, error = self._worker.load(
                            model_target=model_target,
                            model_name=model_name,
                            device=device,
                            compute_type=compute,
                            download_root=_models_dir(),
                            local_files_only=local_files_only,
                        )
                        if not ok:
                            try:
                                self._worker.shutdown(kill=True)
                            except Exception:
                                pass
                            self._worker = None
                            raise RuntimeError(error or "isolated worker load failed")
                        self._worker_loaded = True
                    else:
                        self._model = WhisperModel(
                            model_target,
                            device=device,
                            compute_type=compute,
                            download_root=_models_dir(),
                            local_files_only=local_files_only,
                        )
                    self._loaded_signature = (model_name, device, compute)
                    self._actual_device = device
                    self._actual_compute = compute
                if not use_worker:
                    self._warmup()
                duration = time.time() - start
                self._last_load_seconds = duration
                self._last_fallback_errors = attempt_errors
                # One gray line so the user can always see WHERE the model
                # actually landed (the status pill shows it too, but logs
                # keep the history).
                self._emit_log(
                    "transcription_model_loaded_on",
                    "#888888",
                    device=f"{device.upper()} ({compute})",
                    seconds=duration,
                )
                if device == "cpu" and device_pref != "cpu":
                    self._emit_log("transcription_cuda_unavailable",
                                   self.INFO_COLOR)
                self._set_state(STATE_READY)
                self.info_signal.emit(self.get_runtime_info())
                self._idle_reset_requested.emit()
                return True
            except Exception as exc:  # try next combo
                last_error = exc
                attempt_errors.append((device, compute, str(exc)))
                logger.warning("Model load failed for %s/%s: %s",
                               device, compute, exc)
                continue

        # All attempts failed
        err_msg = str(last_error) if last_error else "unknown"
        self._last_fallback_errors = attempt_errors
        try:
            from .diagnostics import write_diagnostics_report
            report_path = write_diagnostics_report(self.config)
            logger.info("Transcription diagnostics written to %s", report_path)
        except Exception:
            logger.debug("Failed to write transcription diagnostics", exc_info=True)
        self._emit_log("transcription_load_failed",
                       self.ERROR_COLOR, error=err_msg)
        for device, compute, error in attempt_errors[:4]:
            self.log_signal.emit(
                f"  {device}/{compute}: {error}",
                "#888888",
            )
        self._set_state(STATE_ERROR)
        return False

    # Approximate download sizes (MB) used for progress percentage. These
    # are the on-disk weights for each Systran/faster-whisper-* repo.
    _MODEL_SIZE_MB = {
        "large-v3": 3060,
        "large-v3-turbo": 1620,
        "medium": 1530,
        "small": 470,
        "base": 145,
        "tiny": 75,
    }

    def _download_model_with_progress(self, model_name: str, repo: str) -> bool:
        """Download model weights one file at a time.

        HuggingFace still owns the actual HTTP transfer, so cancellation is
        cooperative between files. That is still a large improvement over a
        single opaque ``snapshot_download()`` call because the UI can stop
        cleanly before the next model asset begins and stale locks are cleaned
        before each attempt.
        """
        try:
            import importlib
            hf = importlib.import_module("huggingface_hub")
        except ImportError:
            self._emit_log("transcription_deps_missing", self.ERROR_COLOR)
            return False

        target_root = _models_dir()
        self._download_cancel.clear()
        cleanup_stale_download_files(model_name)

        # Engine-specific copy first; falls back to the neutral key.
        if "transcription_downloading_whisper" in self._logs_section():
            self._emit_log("transcription_downloading_whisper", self.INFO_COLOR,
                           model=model_name)
        else:
            self._emit_log("transcription_downloading", self.INFO_COLOR,
                           model=model_name)

        try:
            os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")
            os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")
            api = hf.HfApi()
            info = api.model_info(repo_id=repo)
            siblings = getattr(info, "siblings", []) or []
            files: List[Tuple[str, Optional[int]]] = []
            for sibling in siblings:
                name = getattr(sibling, "rfilename", "")
                if not name or name.startswith("."):
                    continue
                lower = name.lower()
                if lower.endswith((".md", ".gitattributes")):
                    continue
                if not lower.endswith(DOWNLOAD_FILE_EXTENSIONS):
                    continue
                size = getattr(sibling, "size", None)
                files.append((name, int(size) if isinstance(size, int) else None))
            if not files:
                raise RuntimeError(f"No downloadable model files found for {repo}")

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
                # for the throttle/speed logic. A fresh instance per file so
                # percent state doesn't leak between files.
                reporter = DownloadProgressReporter(self.log_signal.emit)

                ok, error = download_hf_file_external(
                    repo_id=repo,
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
            logger.exception("Model download failed")
            self._emit_log("transcription_download_failed",
                           self.ERROR_COLOR, error=str(exc))
            return False

        snapshot = get_model_snapshot_path(model_name)
        if not snapshot:
            self._emit_log(
                "transcription_download_failed",
                self.ERROR_COLOR,
                error="download finished but no valid model snapshot was found",
            )
            return False
        self.log_signal.emit("  100%", "#888888")
        self._emit_log("transcription_download_done", self.SUCCESS_COLOR,
                       model=model_name)
        return True

    def _warmup(self) -> None:
        """Run a tiny dummy transcription to JIT-compile CUDA kernels."""
        try:
            import numpy as np
            silence = np.zeros(1600, dtype=np.float32)  # 0.1s of silence
            segments_iter, _info = self._model.transcribe(
                silence, beam_size=1, vad_filter=False,
                without_timestamps=True,
            )
            list(segments_iter)
        except Exception:
            logger.debug("Warmup failed (non-fatal)", exc_info=True)

    # ------------------------------------------------------------------ unload

    def unload(self, idle_triggered: bool = False) -> None:
        with self._model_lock:
            self._load_generation += 1
            if self._model is None and self._state == STATE_UNLOADED:
                return
            self._model = None
            if self._worker is not None:
                try:
                    self._worker.unload()
                except Exception:
                    logger.debug("Whisper worker unload failed", exc_info=True)
                try:
                    self._worker.shutdown(kill=True)
                except Exception:
                    pass
                self._worker = None
            self._worker_loaded = False
            self._loaded_signature = None
            self._actual_device = None
            self._actual_compute = None
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
        """Reset auto-unload countdown. Call after each transcription."""
        # Must run in main thread because QTimer requires it; we are usually
        # called from worker thread, so use a queued connection via signal.
        try:
            self._idle_reset_requested.emit()
        except Exception:
            pass

    # ------------------------------------------------------------------ inference

    def transcribe(
        self,
        audio,  # numpy array, float32, 16 kHz mono
        language: Optional[str] = None,
        initial_prompt: Optional[str] = None,
        audio_duration: Optional[float] = None,
    ):
        """Run Whisper inference. Returns list of segments + info object.

        Caller must ensure the model is loaded (state == READY). If not,
        returns (None, None) and emits an error log.
        """
        with self._model_lock:
            if self._state not in (STATE_READY,) or (self._model is None and not self._worker_loaded):
                return None, None
            signature = self._loaded_signature
            model = self._model
            worker = self._worker if self._worker_loaded else None
            self._set_state(STATE_TRANSCRIBING)

        try:
            tr = self._whisper_section()
            beam_size = int(tr.get("beam_size", 1) or 1)
            vad_filter = bool(tr.get("vad_filter", True))
            vad_min_duration = float(tr.get("vad_min_duration_seconds", 1.0) or 0)
            if vad_filter and audio_duration is not None and audio_duration < vad_min_duration:
                vad_filter = False
            # "auto" means let Whisper detect; pass None to faster-whisper.
            lang_arg = None
            if language and language not in ("auto", "", None):
                lang_arg = language

            kwargs = dict(
                beam_size=beam_size,
                vad_filter=vad_filter,
                condition_on_previous_text=False,
                without_timestamps=True,
            )
            if lang_arg:
                kwargs["language"] = lang_arg
            if initial_prompt:
                kwargs["initial_prompt"] = initial_prompt

            try:
                if worker is not None:
                    return worker.transcribe(audio, kwargs)
                else:
                    segments_iter, info = model.transcribe(audio, **kwargs)
                    segments = list(segments_iter)
                    return segments, info
            except Exception as exc:
                logger.exception("Whisper transcription failed")
                with self._model_lock:
                    if worker is not None and worker is self._worker:
                        try:
                            worker.shutdown(kill=True)
                        except Exception:
                            pass
                        self._worker = None
                        self._worker_loaded = False
                    if self._state == STATE_TRANSCRIBING:
                        self._set_state(STATE_ERROR)
                self._emit_log(
                    "transcription_failed",
                    self.ERROR_COLOR,
                    error=f"{type(exc).__name__}: {exc}",
                )
                if worker is not None and signature:
                    self._emit_log("transcription_worker_restart_next_load", self.INFO_COLOR)
                return None, None
        finally:
            with self._model_lock:
                # Return to READY only if this exact model is still active.
                if self._state == STATE_TRANSCRIBING and (self._model is model or worker is self._worker):
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
            worker = self._worker
            self._worker = None
            self._worker_loaded = False
        if release_model:
            self.unload()
        elif worker is not None:
            worker.shutdown(kill=True)
