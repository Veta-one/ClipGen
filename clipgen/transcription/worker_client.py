"""Subprocess client for isolated faster-whisper inference."""

import base64
import io
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from queue import Empty, Queue
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

from .deps import find_worker_python
from ..utils.process_guard import attach_to_kill_job

logger = logging.getLogger("ClipGen")


WORKER_SOURCE = r'''
import base64
import io
import json
import os
import sys
import traceback

_DLL_HANDLES = []


def _start_parent_watchdog():
    """Exit as soon as the ClipGen process that spawned us dies.

    Windows never kills children with their parent. Without this guard a
    crash (or any exit path that skips worker shutdown) would leave this
    process holding the loaded model in RAM/VRAM indefinitely. ``os._exit``
    is used deliberately: CUDA/CTranslate2 interpreter finalization can
    hang, and a hung exit would defeat the whole point.
    """
    try:
        ppid = int(os.environ.get("CLIPGEN_PARENT_PID", ""))
    except ValueError:
        return
    import threading

    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel32.WaitForSingleObject.restype = ctypes.c_uint32
        SYNCHRONIZE = 0x00100000
        INFINITE = 0xFFFFFFFF
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, ppid)
        if not handle:
            os._exit(2)

        def waiter():
            kernel32.WaitForSingleObject(handle, INFINITE)
            os._exit(2)
    else:
        import time as _time

        def waiter():
            while True:
                try:
                    os.kill(ppid, 0)
                except OSError:
                    os._exit(2)
                _time.sleep(2.0)

    threading.Thread(target=waiter, daemon=True).start()


_start_parent_watchdog()


def _setup_cuda_paths():
    if sys.platform != "win32" or not hasattr(os, "add_dll_directory"):
        return
    try:
        import importlib.util
        spec = importlib.util.find_spec("nvidia")
        if spec is None or not spec.submodule_search_locations:
            return
        root = spec.submodule_search_locations[0]
        for sub in ("cublas", "cufft", "cudnn", "cuda_nvrtc", "cuda_runtime", "nvjitlink"):
            path = os.path.join(root, sub, "bin")
            if os.path.isdir(path):
                try:
                    _DLL_HANDLES.append(os.add_dll_directory(path))
                except Exception:
                    pass
                os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass


_setup_cuda_paths()

import numpy as np
from faster_whisper import WhisperModel

_model = None
_signature = None


def _reply(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _segment_to_dict(seg):
    return {
        "text": getattr(seg, "text", ""),
        "start": getattr(seg, "start", None),
        "end": getattr(seg, "end", None),
        "avg_logprob": getattr(seg, "avg_logprob", None),
        "no_speech_prob": getattr(seg, "no_speech_prob", None),
        "compression_ratio": getattr(seg, "compression_ratio", None),
    }


def _handle(req):
    global _model, _signature
    cmd = req.get("cmd")
    if cmd == "ping":
        return {"ok": True, "pong": True}
    if cmd == "load":
        if _model is not None and _signature == req.get("signature"):
            return {"ok": True, "already_loaded": True}
        _model = None
        _signature = None
        _model = WhisperModel(
            req["model_target"],
            device=req.get("device", "auto"),
            compute_type=req.get("compute_type", "default"),
            download_root=req.get("download_root"),
            local_files_only=bool(req.get("local_files_only", False)),
        )
        _signature = req.get("signature")
        if req.get("warmup", True):
            try:
                silence = np.zeros(1600, dtype=np.float32)
                segments, _info = _model.transcribe(
                    silence,
                    beam_size=1,
                    vad_filter=False,
                    without_timestamps=True,
                )
                list(segments)
            except Exception:
                pass
        return {"ok": True}
    if cmd == "transcribe":
        if _model is None:
            return {"ok": False, "error": "model is not loaded"}
        audio_bytes = base64.b64decode(req["audio"])
        audio = np.load(io.BytesIO(audio_bytes), allow_pickle=False)
        kwargs = dict(req.get("kwargs") or {})
        segments_iter, info = _model.transcribe(audio, **kwargs)
        segments = [_segment_to_dict(seg) for seg in segments_iter]
        info_obj = {
            "language": getattr(info, "language", None),
            "language_probability": getattr(info, "language_probability", None),
            "duration": getattr(info, "duration", None),
            "duration_after_vad": getattr(info, "duration_after_vad", None),
        }
        return {"ok": True, "segments": segments, "info": info_obj}
    if cmd == "unload":
        _model = None
        _signature = None
        return {"ok": True}
    if cmd == "shutdown":
        _model = None
        _signature = None
        return {"ok": True, "shutdown": True}
    return {"ok": False, "error": "unknown command: " + str(cmd)}


for line in sys.stdin:
    try:
        req = json.loads(line)
        resp = _handle(req)
        _reply(resp)
        if resp.get("shutdown"):
            break
    except Exception as exc:
        try:
            _reply({
                "ok": False,
                "error": type(exc).__name__ + ": " + str(exc),
                "traceback": traceback.format_exc(),
            })
        except Exception:
            # stdout pipe is gone — the parent died. Nothing to talk to.
            break

# Hard exit on EOF/shutdown: interpreter finalization with CUDA/CTranslate2
# loaded is known to hang on some driver versions, which would keep the
# model resident in a zombie process forever.
try:
    sys.stdout.flush()
except Exception:
    pass
os._exit(0)
'''


class WhisperWorkerClient:
    """Persistent JSON-lines subprocess around ``faster_whisper.WhisperModel``."""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._script_path: Optional[str] = None
        self._lock = threading.RLock()
        self._stderr_tail: List[str] = []

    def start(self) -> bool:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return True
            python_argv = find_worker_python()
            if not python_argv:
                logger.warning("External Python not found; isolated Whisper worker disabled")
                return False

            fd, path = tempfile.mkstemp(prefix="clipgen_whisper_worker_", suffix=".py")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(WORKER_SOURCE)
            env = {
                **os.environ,
                "PYTHONUNBUFFERED": "1",
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
                # The worker's parent watchdog waits on this PID and exits
                # when ClipGen dies, so the model never outlives the app.
                "CLIPGEN_PARENT_PID": str(os.getpid()),
            }
            self._proc = subprocess.Popen(
                [*python_argv, "-u", path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
            )
            # Second line of defense: the OS terminates every process in the
            # job when ClipGen exits for any reason (including crashes).
            attach_to_kill_job(self._proc)
            self._script_path = path
            threading.Thread(target=self._read_stderr, daemon=True).start()
            try:
                # Generous timeout: a cold import of numpy + faster_whisper
                # (AV scan, cold disk cache) has been measured at 30+ s.
                # request() still fails fast if the process dies.
                resp = self.request({"cmd": "ping"}, timeout=120)
                return bool(resp.get("ok"))
            except Exception:
                logger.exception("Failed to start isolated Whisper worker")
                self.shutdown(kill=True)
                return False

    def _read_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for line in proc.stderr:
            text = line.rstrip()
            if text:
                self._stderr_tail.append(text)
                self._stderr_tail = self._stderr_tail[-40:]
                logger.debug("whisper-worker: %s", text)

    def request(self, payload: Dict[str, Any], timeout: float = 120) -> Dict[str, Any]:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                raise RuntimeError("Whisper worker is not running")
            assert self._proc.stdin is not None
            assert self._proc.stdout is not None
            proc = self._proc
            stdout = self._proc.stdout
            self._proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self._proc.stdin.flush()

            line_queue: Queue = Queue(maxsize=1)

            def read_stdout_line() -> None:
                try:
                    line_queue.put(stdout.readline())
                except Exception as exc:
                    line_queue.put(exc)

            threading.Thread(
                target=read_stdout_line,
                daemon=True,
                name="WhisperWorkerStdoutRead",
            ).start()

            deadline = time.time() + timeout
            while True:
                if time.time() > deadline:
                    tail = "\n".join(self._stderr_tail[-10:])
                    try:
                        if proc.poll() is None:
                            proc.kill()
                    finally:
                        if self._proc is proc:
                            self._proc = None
                    detail = f": {tail}" if tail else ""
                    raise TimeoutError(f"Whisper worker request timed out{detail}")
                try:
                    item = line_queue.get(timeout=0.05)
                except Empty:
                    if proc.poll() is not None:
                        tail = "\n".join(self._stderr_tail[-10:])
                        raise RuntimeError(f"Whisper worker exited with {proc.returncode}: {tail}")
                    continue
                if isinstance(item, Exception):
                    raise RuntimeError(f"Whisper worker stdout read failed: {item}")
                line = item
                if line:
                    return json.loads(line)
                if proc.poll() is not None:
                    tail = "\n".join(self._stderr_tail[-10:])
                    raise RuntimeError(f"Whisper worker exited with {proc.returncode}: {tail}")

    def load(
        self,
        model_target: str,
        model_name: str,
        device: str,
        compute_type: str,
        download_root: str,
        local_files_only: bool,
    ) -> Tuple[bool, str]:
        if not self.start():
            return False, "worker failed to start"
        resp = self.request(
            {
                "cmd": "load",
                "model_target": model_target,
                "device": device,
                "compute_type": compute_type,
                "download_root": download_root,
                "local_files_only": local_files_only,
                "signature": [model_name, device, compute_type, model_target],
                "warmup": True,
            },
            timeout=180,
        )
        return bool(resp.get("ok")), str(resp.get("error", ""))

    def transcribe(self, audio, kwargs: Dict[str, Any]) -> Tuple[List[Any], Dict[str, Any]]:
        if self._proc is None or self._proc.poll() is not None:
            raise RuntimeError("Whisper worker is not running")
        buffer = io.BytesIO()
        import numpy as np
        np.save(buffer, audio.astype(np.float32, copy=False), allow_pickle=False)
        audio_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
        resp = self.request(
            {"cmd": "transcribe", "audio": audio_b64, "kwargs": kwargs},
            timeout=300,
        )
        if not resp.get("ok"):
            raise RuntimeError(str(resp.get("error", "worker transcription failed")))
        segments = [SimpleNamespace(**item) for item in resp.get("segments", [])]
        info = dict(resp.get("info") or {})
        return segments, info

    def unload(self) -> None:
        try:
            if self._proc is not None and self._proc.poll() is None:
                self.request({"cmd": "unload"}, timeout=30)
        except Exception:
            logger.debug("Whisper worker unload failed", exc_info=True)

    def shutdown(self, kill: bool = False) -> None:
        proc = self._proc
        self._proc = None
        try:
            if proc is not None and proc.poll() is None:
                if kill:
                    proc.kill()
                    proc.wait(timeout=5)
                else:
                    try:
                        self._proc = proc
                        self.request({"cmd": "shutdown"}, timeout=15)
                    finally:
                        self._proc = None
                    proc.wait(timeout=10)
        except Exception:
            try:
                if proc is not None and proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=5)
            except Exception:
                pass
        finally:
            if self._script_path:
                try:
                    os.remove(self._script_path)
                except OSError:
                    pass
                self._script_path = None
