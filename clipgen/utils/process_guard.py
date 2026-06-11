"""Child-process lifetime guard (Windows).

ClipGen spawns helper ``python.exe`` processes: the isolated Whisper
inference worker and HuggingFace download helpers. Windows never kills
children when the parent dies, so after a crash / Task Manager kill the
worker would keep several GB of model weights resident until reboot.

Two defenses live here:

• ``attach_to_kill_job(proc)`` — puts a child into a Job Object created
  with ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE``. The only handle to the job
  belongs to this process; when ClipGen exits *for any reason* the OS
  closes the handle and terminates every process in the job.

• ``sweep_orphaned_helpers_async()`` — startup cleanup for helpers leaked
  by previous app versions or by scenarios the job object cannot cover
  (e.g. the job API being unavailable). Finds helper processes by the
  unique temp-script markers in their command line and kills them only
  when their parent process is already gone, so helpers of another live
  ClipGen instance are never touched.
"""

import logging
import os
import subprocess
import sys
import threading
import time
from typing import Optional

logger = logging.getLogger("ClipGen")

# Temp-script name prefixes used by worker_client.py / download_worker.py.
# They are unique enough to identify our helper processes in a command line.
HELPER_CMDLINE_MARKERS = (
    "clipgen_whisper_worker_",
    "clipgen_hf_download_",
)

_job_lock = threading.Lock()
_job_handle: Optional[int] = None
_job_failed = False


def _create_kill_on_close_job():
    """Create a Job Object that kills all member processes when closed."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    JobObjectExtendedLimitInformation = 9

    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())

    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = kernel32.SetInformationJobObject(
        handle,
        JobObjectExtendedLimitInformation,
        ctypes.byref(info),
        ctypes.sizeof(info),
    )
    if not ok:
        err = ctypes.get_last_error()
        kernel32.CloseHandle(handle)
        raise ctypes.WinError(err)
    return handle


def attach_to_kill_job(proc: subprocess.Popen) -> bool:
    """Tie a child process's lifetime to ours. Returns True on success.

    Best effort: failure is logged and the caller keeps working — the
    in-worker parent watchdog still covers the orphan case.
    """
    global _job_handle, _job_failed
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        with _job_lock:
            if _job_handle is None and not _job_failed:
                try:
                    _job_handle = _create_kill_on_close_job()
                except Exception:
                    _job_failed = True
                    logger.exception("Failed to create kill-on-close job object")
            job = _job_handle
        if job is None:
            return False

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        ok = kernel32.AssignProcessToJobObject(job, int(proc._handle))
        if not ok:
            logger.warning(
                "AssignProcessToJobObject failed for pid %s (error %s)",
                proc.pid, ctypes.get_last_error(),
            )
            return False
        return True
    except Exception:
        logger.exception("Failed to attach child process to kill job")
        return False


def sweep_orphaned_helpers_async() -> None:
    """Kill helper processes leaked by previous runs; remove stale scripts.

    Runs in a daemon thread — process enumeration via CIM takes a second
    or two and must not delay startup.
    """
    if sys.platform != "win32":
        return
    threading.Thread(
        target=_sweep_orphaned_helpers,
        daemon=True,
        name="OrphanHelperSweep",
    ).start()


def _sweep_orphaned_helpers() -> None:
    marker_regex = "|".join(HELPER_CMDLINE_MARKERS)
    # Candidates are python*/py* processes whose command line contains one of
    # our unique temp-script markers. A helper is an orphan only when its
    # parent process no longer exists — helpers of a live ClipGen instance
    # keep their parent and are skipped.
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name LIKE 'py%'\" | "
        f"Where-Object {{ $_.CommandLine -match '{marker_regex}' }} | "
        "ForEach-Object { "
        "$parent = $null; "
        "try { $parent = Get-Process -Id $_.ParentProcessId -ErrorAction Stop } catch {}; "
        "if (-not $parent) { "
        "try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; "
        "Write-Output ('killed ' + $_.ProcessId) } catch {} } }"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=90,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        out = (completed.stdout or "").strip()
        if out:
            logger.info(
                "Cleaned up orphaned transcription helpers from a previous run: %s",
                out.replace("\n", ", "),
            )
    except Exception:
        logger.debug("Orphan helper sweep failed", exc_info=True)

    _remove_stale_helper_scripts()


def _remove_stale_helper_scripts(older_than_seconds: int = 24 * 3600) -> None:
    """Delete leftover helper temp scripts from crashed runs."""
    try:
        import glob
        import tempfile

        now = time.time()
        temp_dir = tempfile.gettempdir()
        for marker in HELPER_CMDLINE_MARKERS:
            for path in glob.glob(os.path.join(temp_dir, marker + "*.py")):
                try:
                    if now - os.path.getmtime(path) > older_than_seconds:
                        os.remove(path)
                except OSError:
                    continue
    except Exception:
        logger.debug("Stale helper script cleanup failed", exc_info=True)
