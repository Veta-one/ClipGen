"""Main entry point for ClipGen application.

CRITICAL: this file performs CUDA DLL registration and pre-imports
faster_whisper *before* anything else. Both must happen before any other
imports (especially PyQt5) — otherwise PyInstaller's bootloader pre-warms
Qt DLLs in a way that breaks subsequent CTranslate2 GPU init with a
0xC0000005 access violation. Order matters; do not rearrange.
"""

# --- Pre-import setup (DO NOT MOVE) ---
import os as _os
import sys as _sys

_DLL_DIRECTORY_HANDLES = []


def _bootstrap_log(msg: str) -> None:
    """Write a line to fault_log.txt during early bootstrap."""
    try:
        if getattr(_sys, "frozen", False):
            base = _os.path.dirname(_sys.executable)
        else:
            base = _os.getcwd()
        path = _os.path.join(base, "fault_log.txt")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[bootstrap] {msg}\n")
    except Exception:
        pass


def _bootstrap_user_site() -> None:
    """Insert the user's pip site-packages at the front of ``sys.path``."""
    if not getattr(_sys, "frozen", False):
        return
    if _sys.platform != "win32":
        return
    appdata = _os.environ.get("APPDATA", "")
    if not appdata:
        _bootstrap_log("user_site: no APPDATA env var")
        return
    py_dir = f"Python{_sys.version_info.major}{_sys.version_info.minor}"
    user_site = _os.path.join(appdata, "Python", py_dir, "site-packages")
    if _os.path.isdir(user_site) and user_site not in _sys.path:
        _sys.path.insert(0, user_site)
        _bootstrap_log(f"user_site: added {user_site}")
    else:
        _bootstrap_log(f"user_site: not adding (exists={_os.path.isdir(user_site)})")


def _bootstrap_cuda_paths() -> None:
    """Register CUDA DLL search paths from nvidia-* pip packages."""
    if _sys.platform != "win32":
        return
    if not hasattr(_os, "add_dll_directory"):
        _bootstrap_log("cuda_paths: os.add_dll_directory missing")
        return
    try:
        import importlib.util
        nvidia_spec = importlib.util.find_spec("nvidia")
        if nvidia_spec is None or not nvidia_spec.submodule_search_locations:
            _bootstrap_log("cuda_paths: nvidia package not found")
            return
        nvidia_root = nvidia_spec.submodule_search_locations[0]
        registered = []
        for sub in ("cublas", "cufft", "cudnn", "cuda_nvrtc", "cuda_runtime", "nvjitlink"):
            bin_dir = _os.path.join(nvidia_root, sub, "bin")
            if _os.path.isdir(bin_dir):
                try:
                    _DLL_DIRECTORY_HANDLES.append(_os.add_dll_directory(bin_dir))
                except Exception as exc:
                    _bootstrap_log(f"cuda_paths: add_dll_directory({bin_dir}) failed: {exc}")
                    continue
                _os.environ["PATH"] = (
                    bin_dir + _os.pathsep + _os.environ.get("PATH", "")
                )
                registered.append(sub)
        _bootstrap_log(f"cuda_paths: registered {registered}")
    except Exception as exc:
        _bootstrap_log(f"cuda_paths: failed: {exc}")


def _bootstrap_preload_whisper() -> None:
    """Eagerly load faster_whisper / CTranslate2 native libs.

    This MUST happen before PyQt5 is imported anywhere — otherwise CUDA
    init in WhisperModel() crashes with an access violation. Silently
    no-ops if the deps aren't installed.

    We also probe ``ctranslate2.get_cuda_device_count()`` to force the
    CUDA runtime to initialise *now*, in a clean process state, before
    Qt or any other library has a chance to load conflicting DLLs. This
    pinned-down CUDA context survives subsequent Qt initialisation.
    """
    try:
        import importlib
        importlib.import_module("faster_whisper")
        _bootstrap_log("preload_whisper: faster_whisper loaded")
    except ImportError as exc:
        _bootstrap_log(f"preload_whisper: ImportError: {exc}")
        return
    except Exception as exc:
        _bootstrap_log(f"preload_whisper: failed: {exc}")
        return

    # Warm up CUDA runtime now so subsequent WhisperModel() calls don't
    # need to bootstrap CUDA in a polluted DLL/thread context.
    try:
        import importlib
        ct2 = importlib.import_module("ctranslate2")
        if hasattr(ct2, "get_cuda_device_count"):
            count = ct2.get_cuda_device_count()
            _bootstrap_log(f"preload_whisper: CUDA devices = {count}")
    except Exception as exc:
        _bootstrap_log(f"preload_whisper: CUDA probe failed: {exc}")


_bootstrap_log(f"=== ClipGen startup at {_os.getpid()} ===")
_bootstrap_log(f"frozen={getattr(_sys, 'frozen', False)} executable={_sys.executable}")
_bootstrap_user_site()
_bootstrap_cuda_paths()
_bootstrap_preload_whisper()
# --- End of pre-import setup ---

import faulthandler
import os
import sys
import time
import traceback


def _enable_native_crash_log() -> None:
    """Capture C-level crashes (segfault, access violation) to a file.

    Python's ``sys.excepthook`` only fires for Python exceptions. Native
    crashes from CUDA / CTranslate2 / sounddevice would otherwise just
    silently disappear in a frozen .exe (no console attached). This makes
    them land in ``fault_log.txt`` next to the executable.
    """
    try:
        # Place the log next to the executable so users can find it.
        if getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.getcwd()
        path = os.path.join(base, "fault_log.txt")
        # Open in append mode and keep the handle alive on the module —
        # closing it would defeat the whole point.
        global _fault_log_handle
        _fault_log_handle = open(path, "a", encoding="utf-8", buffering=1)
        _fault_log_handle.write(
            f"\n=== faulthandler enabled at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
        )
        faulthandler.enable(file=_fault_log_handle, all_threads=True)
    except Exception:
        # Non-fatal: just continue without native crash capture.
        pass


_enable_native_crash_log()


def exception_hook(exctype, value, tb):
    """Handle uncaught exceptions by logging to file."""
    with open("error_log.txt", "a", encoding="utf-8") as f:
        f.write(f"\n\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        f.write(f"Exception: {exctype.__name__}: {value}\n")
        f.write("".join(traceback.format_tb(tb)))

    # Call default hook
    sys.__excepthook__(exctype, value, tb)


def main():
    """Main entry point."""
    # Install exception hook
    sys.excepthook = exception_hook

    # Note: CUDA DLL paths and faster_whisper preload have already been
    # done at module import time (see _bootstrap_* functions at the top
    # of this file). They MUST happen before PyQt5 is imported.

    try:
        from clipgen.app import ClipGenApp

        app = ClipGenApp()
        sys.exit(app.run())

    except Exception as e:
        print(f"Failed to start: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
