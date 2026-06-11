"""External HuggingFace download helper.

The main PyInstaller process intentionally avoids doing large model HTTP
transfers itself. Running ``hf_hub_download`` in an external Python process
lets ClipGen cancel an in-flight large file by terminating that helper.

Progress reporting: we don't pipe HF's tqdm output (it draws via ``\\r``
which doesn't survive line-buffered PIPE reads cleanly). Instead the
poll loop watches the cache for ``.incomplete`` blob files and reports
their on-disk byte size — that's the same number HF would print, and
costs us a single ``os.stat`` per polling tick.
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable, Optional, Tuple

from .deps import find_worker_python
from ..utils.process_guard import attach_to_kill_job

logger = logging.getLogger("ClipGen")


DOWNLOAD_SOURCE = r'''
import json
import os
import sys
import traceback

try:
    from huggingface_hub import hf_hub_download

    repo_id = sys.argv[1]
    filename = sys.argv[2]
    cache_dir = sys.argv[3]
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")
    path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        cache_dir=cache_dir,
    )
    print(json.dumps({"ok": True, "path": path}, ensure_ascii=False), flush=True)
except Exception as exc:
    print(json.dumps({
        "ok": False,
        "error": type(exc).__name__ + ": " + str(exc),
        "traceback": traceback.format_exc(),
    }, ensure_ascii=False), flush=True)
    sys.exit(1)
'''


def _scan_incomplete_blob(cache_dir: str, repo_id: str) -> int:
    """Return the byte size of the largest ``.incomplete`` blob in this repo's cache.

    HF buffers the download in ``cache_dir/models--<owner>--<repo>/blobs/<sha>.incomplete``
    and renames it to ``<sha>`` once verified. While the download is in
    flight that single file's size is exactly how many bytes have arrived.
    Returns 0 if no in-progress blob is found.
    """
    repo_root = os.path.join(
        cache_dir, "models--" + repo_id.replace("/", "--"), "blobs"
    )
    if not os.path.isdir(repo_root):
        return 0
    largest = 0
    try:
        for name in os.listdir(repo_root):
            if not name.endswith(".incomplete"):
                continue
            try:
                size = os.path.getsize(os.path.join(repo_root, name))
            except OSError:
                continue
            if size > largest:
                largest = size
    except OSError:
        return 0
    return largest


def download_hf_file_external(
    repo_id: str,
    filename: str,
    cache_dir: str,
    cancel_event: threading.Event,
    timeout: Optional[float] = None,
    expected_size: Optional[int] = None,
    on_progress: Optional[Callable[[int, Optional[int]], None]] = None,
) -> Tuple[bool, str]:
    """Download one HF file in an external Python process.

    Args:
        expected_size: total size in bytes when known (from HF model_info).
            Used to compute a percentage; passed through to ``on_progress``.
        on_progress: callback invoked with ``(downloaded_bytes, expected_size)``
            roughly twice a second while the file is in flight. Throttling
            and humanisation belongs in the caller — this layer only ships
            raw byte counts.
    """
    python_argv = find_worker_python()
    if not python_argv:
        return False, "external Python interpreter not found"

    fd, script_path = tempfile.mkstemp(prefix="clipgen_hf_download_", suffix=".py")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(DOWNLOAD_SOURCE)

    env = {
        **os.environ,
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    proc = None
    try:
        proc = subprocess.Popen(
            [*python_argv, "-u", script_path, repo_id, filename, cache_dir],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
        )
        # If ClipGen dies mid-download, the OS kills the helper with us —
        # otherwise it would keep pulling gigabytes in the background.
        attach_to_kill_job(proc)
        started = time.time()
        last_progress_emit = 0.0
        last_reported_bytes = 0
        # Tighter polling than the original 0.2s sleep — at 30 MB/s a 72 MB
        # file finishes in 2.4s, so we need <500ms cadence to catch it
        # while it's still in ``.incomplete`` form.
        POLL_INTERVAL = 0.4
        while proc.poll() is None:
            if cancel_event.is_set():
                proc.kill()
                return False, "cancelled"
            if timeout is not None and time.time() - started > timeout:
                proc.kill()
                return False, "download helper timed out"
            if on_progress is not None:
                now = time.time()
                if now - last_progress_emit >= POLL_INTERVAL:
                    bytes_done = _scan_incomplete_blob(cache_dir, repo_id)
                    if bytes_done > 0 and bytes_done != last_reported_bytes:
                        try:
                            on_progress(bytes_done, expected_size)
                        except Exception:
                            logger.debug("on_progress callback failed", exc_info=True)
                        last_reported_bytes = bytes_done
                    last_progress_emit = now
            time.sleep(POLL_INTERVAL / 2)

        stdout, stderr = proc.communicate(timeout=5)
        last_line = ""
        for line in stdout.splitlines():
            if line.strip():
                last_line = line.strip()
        if last_line:
            try:
                data = json.loads(last_line)
                if data.get("ok"):
                    # Tiny files often finish between polls and the
                    # ``.incomplete`` file is gone before we ever see it,
                    # so emit a synthetic 100% so the caller can render a
                    # final status line. Big files also benefit — there's
                    # always a tail period where bytes_done = total_bytes
                    # but we missed it in the polling cadence.
                    if on_progress is not None and expected_size:
                        try:
                            on_progress(int(expected_size), expected_size)
                        except Exception:
                            logger.debug("on_progress final callback failed", exc_info=True)
                    return True, str(data.get("path", ""))
                return False, str(data.get("error", "download failed"))
            except json.JSONDecodeError:
                pass
        err = (stderr or stdout or f"download helper exited with {proc.returncode}").strip()
        return False, err[-2000:]
    except Exception as exc:
        logger.debug("External HF download failed", exc_info=True)
        try:
            if proc is not None and proc.poll() is None:
                proc.kill()
        except Exception:
            pass
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        try:
            os.remove(script_path)
        except OSError:
            pass
