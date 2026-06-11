"""Register CUDA DLL search paths from nvidia-* pip packages.

When CUDA libraries are installed via pip (nvidia-cublas-cu12, nvidia-cudnn-cu12),
their DLLs live under site-packages/nvidia/<lib>/bin and are not on PATH.
faster-whisper / CTranslate2 will fail to find them unless we register those
directories explicitly.

This is Windows-only; on Linux the wheels expose .so files via RPATH.
"""

import importlib.util
import logging
import os
import sys

logger = logging.getLogger('ClipGen')

_REGISTERED = False
_DLL_DIRECTORY_HANDLES = []


def setup_cuda_dll_paths() -> bool:
    """Register CUDA DLL directories from site-packages/nvidia/*/bin.

    Returns True on success (or already registered), False if nvidia package
    is not installed.
    """
    global _REGISTERED
    if _REGISTERED:
        return True
    if sys.platform != "win32":
        _REGISTERED = True
        return True

    try:
        nvidia_spec = importlib.util.find_spec("nvidia")
        if nvidia_spec is None or not nvidia_spec.submodule_search_locations:
            return False

        nvidia_root = nvidia_spec.submodule_search_locations[0]
        for sub in ("cublas", "cufft", "cudnn", "cuda_nvrtc", "cuda_runtime", "nvjitlink"):
            bin_dir = os.path.join(nvidia_root, sub, "bin")
            if os.path.isdir(bin_dir):
                try:
                    _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(bin_dir))
                except (OSError, AttributeError):
                    pass
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")

        _REGISTERED = True
        return True
    except Exception:
        logger.exception("CUDA DLL path setup failed")
        return False


def detect_gpu() -> dict:
    """Return basic GPU info via nvidia-smi if available.

    Returns:
        Dict with keys: available (bool), name (str), free_mb (int),
        total_mb (int). Missing values default to None.
    """
    info = {"available": False, "name": None, "free_mb": None, "total_mb": None}
    try:
        import subprocess
        import sys as _sys
        # Same CREATE_NO_WINDOW flag we use for the pip subprocess — without
        # it, calling nvidia-smi from a windowless .exe pops a black console.
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.free,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=(subprocess.CREATE_NO_WINDOW if _sys.platform == "win32" else 0),
        )
        if result.returncode == 0 and result.stdout.strip():
            line = result.stdout.strip().splitlines()[0]
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                info["available"] = True
                info["name"] = parts[0]
                info["free_mb"] = int(parts[1])
                info["total_mb"] = int(parts[2])
    except Exception:
        pass
    return info
