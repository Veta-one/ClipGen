"""Dependency check and installation helpers for transcription.

The transcription stack pulls in ~1.5 GB of CUDA + faster-whisper. Users who
do not need voice transcription should not pay that cost. This module:

• check_dependencies()   — fast import probe, returns missing list
• install_dependencies() — runs `pip install` in a subprocess, streams output

Frozen-app caveat
-----------------
When ClipGen runs as a PyInstaller .exe, ``sys.executable`` IS the .exe
(not a Python interpreter), so calling ``sys.executable -m pip install ...``
would re-launch ClipGen for every install attempt. We work around this by
locating a real system Python (``py.exe`` launcher or ``python.exe`` on
PATH) and running pip through that interpreter. The installed packages
land in the user's site-packages, which our frozen entry point adds to
``sys.path`` at startup so they remain importable.
"""

import importlib
import importlib.metadata
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger('ClipGen')


# Shared infrastructure both engines rely on (audio capture, model downloads,
# numpy). These are installed regardless of which engine the user picks.
SHARED_PACKAGES = [
    ("sounddevice", "sounddevice==0.5.5"),
    ("numpy", "numpy==2.4.4"),
    ("huggingface_hub", "huggingface_hub==0.36.2"),
    # scipy is only used for WAV file I/O in the Parakeet path. Pinning a
    # specific minor would clash with numpy 2.4.x because scipy<1.15 caps
    # numpy at <2.3. Use a loose range instead — the only API we touch
    # (``scipy.io.wavfile.write``) has been stable since the 1.0 series.
    ("scipy", "scipy>=1.15.0,<2"),
]

# Whisper-specific packages (faster-whisper + CTranslate2 backend).
WHISPER_PACKAGES = [
    ("faster_whisper", "faster-whisper==1.2.1"),
    ("ctranslate2", "ctranslate2==4.7.1"),
    # tqdm with full submodules — faster-whisper imports tqdm.contrib.concurrent
    # at runtime, which the PyInstaller-bundled minimal tqdm may not include.
    ("tqdm.contrib", "tqdm==4.67.1"),
]

# Parakeet-specific packages (ONNX backend via onnx-asr).
#
# onnx-asr <0.6 had a hardcoded list of supported model aliases; the
# ``nemo-parakeet-tdt-0.6b-v3`` alias only landed in 0.11.0. Pinning
# 0.4.0 here was the cause of "Model 'nemo-parakeet-tdt-0.6b-v3' not
# supported!" errors on Load. Use a lower-bound range so future
# improvements (extra Parakeet variants, faster decoding) ship to users.
PARAKEET_PACKAGES = [
    ("onnxruntime", "onnxruntime-gpu==1.20.1"),
    ("onnx_asr", "onnx-asr>=0.11.0,<1"),
]

# REQUIRED_PACKAGES kept as the legacy alias used elsewhere in the code base.
# It now resolves to the union of shared + Whisper deps, which preserves the
# original behaviour for code paths that were Whisper-only before the refactor.
REQUIRED_PACKAGES = SHARED_PACKAGES + WHISPER_PACKAGES

# CUDA libraries are Windows-only and only relevant for GPU inference.
# Both engines benefit when a CUDA-capable GPU is available.
CUDA_PACKAGES = [
    ("nvidia.cuda_runtime", "nvidia-cuda-runtime-cu12==12.9.79"),
    ("nvidia.cublas", "nvidia-cublas-cu12==12.9.2.10"),
    ("nvidia.cufft", "nvidia-cufft-cu12==11.4.1.4"),
    ("nvidia.cudnn", "nvidia-cudnn-cu12==9.22.0.52"),
    ("nvidia.cuda_nvrtc", "nvidia-cuda-nvrtc-cu12==12.9.86"),
    ("nvidia.nvjitlink", "nvidia-nvjitlink-cu12==12.9.86"),
]


def _packages_for_engine(engine: str) -> List[tuple]:
    """Return the (module, pip_spec) list a specific engine needs."""
    if engine == "parakeet":
        return SHARED_PACKAGES + PARAKEET_PACKAGES
    # Default + explicit "whisper".
    return SHARED_PACKAGES + WHISPER_PACKAGES


def _dist_name_from_pip_spec(pip_spec: str) -> str:
    """Extract the package/distribution name from a simple pip requirement."""
    match = re.match(r"\s*([A-Za-z0-9_.-]+)", pip_spec)
    return match.group(1) if match else pip_spec


def _version_satisfies(installed: str, pip_spec: str) -> bool:
    """Return True when an installed distribution satisfies our pinned range.

    This intentionally handles only the operators used by the package lists
    above. It avoids importing target modules such as onnxruntime, because
    loading native DLLs into ClipGen would block pip from replacing them.
    """
    constraints = re.findall(r"(==|>=|<=|>|<)\s*([^,\s]+)", pip_spec)
    if not constraints:
        return True

    try:
        from packaging.version import Version
    except Exception:
        Version = None  # type: ignore

    def parsed(value: str):
        if Version is not None:
            return Version(value)
        parts = []
        for chunk in re.split(r"[^\d]+", value):
            if chunk:
                parts.append(int(chunk))
        return tuple(parts)

    try:
        current = parsed(installed)
        for operator, expected_text in constraints:
            expected = parsed(expected_text)
            if operator == "==" and current != expected:
                return False
            if operator == ">=" and current < expected:
                return False
            if operator == "<=" and current > expected:
                return False
            if operator == ">" and current <= expected:
                return False
            if operator == "<" and current >= expected:
                return False
    except Exception:
        logger.debug("Could not compare installed version %s with %s",
                     installed, pip_spec, exc_info=True)
        return False
    return True


def _is_requirement_satisfied(module_name: str, pip_spec: str) -> bool:
    """Check module presence and installed distribution version."""
    import importlib.util

    try:
        spec = importlib.util.find_spec(module_name)
    except (ImportError, ValueError, ModuleNotFoundError):
        spec = None
    if spec is None:
        return False

    dist_name = _dist_name_from_pip_spec(pip_spec)
    try:
        installed_version = importlib.metadata.version(dist_name)
    except importlib.metadata.PackageNotFoundError:
        return False
    except Exception:
        logger.debug("Could not read installed package version for %s",
                     dist_name, exc_info=True)
        return False

    return _version_satisfies(installed_version, pip_spec)


PYTHON_NOT_FOUND_ERROR = "python-not-found"


def ensure_user_site_on_path() -> bool:
    """Make freshly pip-installed ``--user`` packages importable now.

    The frozen exe adds the user site-packages dir to ``sys.path`` at
    startup only when it already exists (see ``main._bootstrap_user_site``).
    On a clean machine that directory is first CREATED by the in-app
    installer, so the running process must pick it up dynamically —
    otherwise every dependency check keeps failing until a restart.
    Returns True when the user site dir is on ``sys.path``.
    """
    if not getattr(sys, "frozen", False) or sys.platform != "win32":
        return True
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return False
    py_dir = f"Python{sys.version_info.major}{sys.version_info.minor}"
    user_site = os.path.join(appdata, "Python", py_dir, "site-packages")
    if not os.path.isdir(user_site):
        return False
    if user_site not in sys.path:
        sys.path.insert(0, user_site)
        importlib.invalidate_caches()
        logger.info("Added user site-packages to sys.path: %s", user_site)
    return True


def _find_pip_python() -> Optional[List[str]]:
    """Interpreter argv used for ``pip install --user`` in frozen mode.

    Prefers the Python whose X.Y matches the frozen app — ``--user``
    packages then land in the exact site-packages directory the exe
    scans (``%APPDATA%/Python/PythonXY/site-packages``). Falls back to
    any system Python so installation still works for the isolated
    worker even when versions differ.
    """
    version_flag = f"-{sys.version_info.major}.{sys.version_info.minor}"
    candidates: List[List[str]] = []
    if sys.platform == "win32":
        py_launcher = shutil.which("py")
        if py_launcher:
            candidates.append([py_launcher, version_flag])
    fallback = _find_external_python()
    if fallback:
        candidates.append(fallback)
    for argv in candidates:
        try:
            probe = subprocess.run(
                [*argv, "-c", "pass"],
                capture_output=True,
                timeout=20,
                creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
            )
            if probe.returncode == 0:
                return argv
        except Exception:
            continue
    return None


def _find_external_python() -> Optional[List[str]]:
    """Return argv prefix for an external system Python, or None if absent.

    Used in frozen .exe mode where ``sys.executable`` points at the .exe
    itself. Tries the Windows ``py`` launcher first (it picks the highest
    installed Python automatically), then falls back to ``python.exe`` on
    PATH.
    """
    if sys.platform == "win32":
        py_launcher = shutil.which("py")
        if py_launcher:
            # Prefer Python 3.x. The launcher will pick the latest available.
            return [py_launcher, "-3"]
    py_exe = shutil.which("python")
    if py_exe:
        return [py_exe]
    py3 = shutil.which("python3")
    if py3:
        return [py3]
    return None


_worker_python_lock = threading.Lock()
_worker_python: Optional[List[str]] = None


def find_worker_python() -> Optional[List[str]]:
    """Return argv for the interpreter used to spawn helper subprocesses.

    Unlike ``_find_external_python`` this resolves the *real* ``python.exe``
    behind the ``py`` launcher. Helper processes (Whisper worker, download
    helper) must be killable: when they are spawned through ``py.exe`` the
    launcher is the direct child, so ``Popen.kill()`` only kills the
    launcher and orphans the actual ``python.exe`` grandchild together with
    several GB of loaded model weights. The resolution result is cached for
    the process lifetime.
    """
    global _worker_python
    if not getattr(sys, "frozen", False):
        # Dev mode: the running interpreter is the one whose site-packages
        # passed the dependency check.
        return [sys.executable]
    with _worker_python_lock:
        if _worker_python is not None:
            return list(_worker_python) or None
        argv = _find_external_python()
        if not argv:
            _worker_python = []
            return None
        resolved = list(argv)
        try:
            completed = subprocess.run(
                [*argv, "-c", "import sys; print(sys.executable)"],
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
            )
            lines = (completed.stdout or "").strip().splitlines()
            path = lines[-1].strip() if lines else ""
            if completed.returncode == 0 and path and os.path.isfile(path):
                resolved = [path]
            else:
                logger.warning(
                    "Could not resolve real python behind %s; using launcher argv",
                    argv,
                )
        except Exception:
            logger.debug("Real python resolution failed", exc_info=True)
        _worker_python = resolved
        return list(resolved)


def check_dependencies(include_cuda: bool = True) -> List[str]:
    """Return list of missing import names for the Whisper stack.

    Kept for backwards compatibility — Whisper code paths still call this
    directly. New code should prefer ``check_dependencies_for_engine``.
    """
    return check_dependencies_for_engine("whisper", include_cuda=include_cuda)


def _onnxruntime_gpu_build_intact() -> bool:
    """True when the installed onnxruntime files still contain the CUDA provider.

    The CPU-only ``onnxruntime`` wheel and ``onnxruntime-gpu`` unpack into
    the SAME package folder. When the CPU wheel installs last (onnx-asr
    pulls it in as a dependency), the ``onnxruntime-gpu`` dist-info still
    reports the right version — but the CUDA provider DLL is gone and
    inference silently runs on CPU. Checked via the file system only, so
    no native DLLs get mapped into this process.
    """
    try:
        import importlib.util
        spec = importlib.util.find_spec("onnxruntime")
        if spec is None or not spec.submodule_search_locations:
            return True  # not installed at all — version check handles it
        root = spec.submodule_search_locations[0]
        return os.path.isfile(
            os.path.join(root, "capi", "onnxruntime_providers_cuda.dll")
        )
    except Exception:
        logger.debug("onnxruntime build check failed", exc_info=True)
        return True


def check_dependencies_for_engine(engine: str, include_cuda: bool = True) -> List[str]:
    """Return list of missing import names for a specific ASR engine.

    Checks importability plus installed distribution versions without fully
    importing the target packages. Loading e.g. ``onnxruntime`` would map its
    native DLLs into the running ClipGen process, and Windows then refuses to
    let pip overwrite those DLLs during a subsequent ``Install / Download``.
    """
    # Pick up packages installed by the in-app installer during this
    # session — without this a clean machine would need a restart.
    ensure_user_site_on_path()

    missing: List[str] = []
    targets = list(_packages_for_engine(engine))
    if include_cuda and sys.platform == "win32":
        targets.extend(CUDA_PACKAGES)

    for module_name, pip_spec in targets:
        if not _is_requirement_satisfied(module_name, pip_spec):
            missing.append(module_name)

    # A version match is not enough for onnxruntime-gpu: the CPU wheel may
    # have overwritten its files. Flag it so "Install / Download" becomes
    # clickable again and the install path re-asserts the GPU build.
    if (engine == "parakeet" and sys.platform == "win32"
            and "onnxruntime" not in missing
            and not _onnxruntime_gpu_build_intact()):
        missing.append("onnxruntime")
    return missing


def check_runtime_health(include_cuda: bool = True) -> Dict[str, Any]:
    """Return a structured runtime report for the transcription stack.

    ``check_dependencies()`` intentionally stays cheap and import-only for
    UI refreshes. This deeper probe is used before heavy model operations
    and by diagnostics, where native-library and audio-backend details matter.
    """
    report: Dict[str, Any] = {
        "ok": True,
        "missing": check_dependencies(include_cuda=include_cuda),
        "errors": [],
        "warnings": [],
        "ctranslate2": {},
        "audio": {},
        "cuda": {},
    }
    if report["missing"]:
        report["ok"] = False
        report["errors"].append("missing imports: " + ", ".join(report["missing"]))

    try:
        import ctranslate2
        report["ctranslate2"]["version"] = getattr(ctranslate2, "__version__", "unknown")
        try:
            report["ctranslate2"]["cpu_compute_types"] = sorted(
                ctranslate2.get_supported_compute_types("cpu")
            )
        except Exception as exc:
            report["ok"] = False
            report["errors"].append(f"ctranslate2 cpu compute probe failed: {exc}")
        if include_cuda:
            try:
                cuda_count = ctranslate2.get_cuda_device_count()
                report["cuda"]["device_count"] = cuda_count
                if cuda_count > 0:
                    try:
                        report["cuda"]["compute_types"] = sorted(
                            ctranslate2.get_supported_compute_types("cuda")
                        )
                    except Exception as exc:
                        report["warnings"].append(f"cuda compute probe failed: {exc}")
                else:
                    report["warnings"].append("CUDA device count is 0")
            except Exception as exc:
                report["warnings"].append(f"CUDA device probe failed: {exc}")
    except Exception as exc:
        report["ok"] = False
        report["errors"].append(f"ctranslate2 import/probe failed: {type(exc).__name__}: {exc}")

    if sys.platform == "win32":
        system32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
        dll_names = ["vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"]
        report["vc_runtime"] = {
            name: os.path.isfile(os.path.join(system32, name))
            for name in dll_names
        }

    try:
        import sounddevice as sd
        devices = sd.query_devices()
        input_count = sum(1 for dev in devices if dev.get("max_input_channels", 0) > 0)
        report["audio"]["input_device_count"] = input_count
        report["audio"]["default_device"] = sd.default.device
        if input_count <= 0:
            report["ok"] = False
            report["errors"].append("no audio input devices reported by sounddevice")
    except Exception as exc:
        report["ok"] = False
        report["errors"].append(f"sounddevice probe failed: {type(exc).__name__}: {exc}")

    return report


def _reassert_onnxruntime_gpu(
    interp_argv: List[str],
    user_flag: List[str],
    log: Callable[[str], None],
) -> None:
    """Re-install the GPU onnxruntime build after a Parakeet install.

    ``onnx-asr`` depends on the CPU-only ``onnxruntime`` wheel. Both wheels
    unpack into the SAME ``onnxruntime/`` folder, so whichever installs
    last wins — and the CPU build silently replaces the CUDA one. The model
    then quietly runs ~10x slower on CPU while the UI says "CUDA".
    """
    gpu_spec = next(
        (spec for name, spec in PARAKEET_PACKAGES if name == "onnxruntime"),
        "onnxruntime-gpu",
    )
    commands = [
        [*interp_argv, "-m", "pip", "uninstall", "-y", "onnxruntime"],
        [*interp_argv, "-m", "pip", "install", *user_flag,
         "--force-reinstall", "--no-deps", gpu_spec],
    ]
    for cmd in commands:
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
            )
            if completed.returncode != 0:
                logger.warning(
                    "onnxruntime GPU reassert step failed (%s): %s",
                    " ".join(cmd[-3:]),
                    (completed.stderr or completed.stdout or "")[-400:],
                )
        except Exception:
            logger.exception("onnxruntime GPU reassert step crashed")
    logger.info("Re-asserted GPU onnxruntime build after Parakeet install")


def install_dependencies(
    on_log: Optional[Callable[[str], None]] = None,
    on_done: Optional[Callable[[bool, Optional[str]], None]] = None,
    include_cuda: bool = True,
    engine: str = "whisper",
) -> threading.Thread:
    """Install missing dependencies in a background thread.

    Returns the worker thread so caller can join it if needed.
    """
    def log(msg: str) -> None:
        logger.info(msg)
        if on_log:
            on_log(msg)

    def done(ok: bool, err: Optional[str] = None) -> None:
        if on_done:
            on_done(ok, err)

    def worker() -> None:
        try:
            packages = [spec for _, spec in _packages_for_engine(engine)]
            if include_cuda and sys.platform == "win32":
                packages.extend(spec for _, spec in CUDA_PACKAGES)

            # In a frozen .exe, sys.executable IS the .exe — running it with
            # ``-m pip install`` would just re-launch ClipGen instead of pip.
            # Locate an external system Python in that case.
            if getattr(sys, "frozen", False):
                python_argv = _find_pip_python()
                if python_argv is None:
                    logger.warning(
                        "No external Python interpreter found for pip install"
                    )
                    # Marker error — the caller maps it to a localized
                    # message (UI strings must not be hardcoded here).
                    done(False, PYTHON_NOT_FOUND_ERROR)
                    return
                # Install into the user's site-packages so it survives across
                # ClipGen versions (--user). The frozen entry point adds the
                # user site-packages directory to sys.path at startup.
                interp_argv = list(python_argv)
                user_flag = ["--user"]
            else:
                interp_argv = [sys.executable]
                user_flag = []
            base_cmd = [*interp_argv, "-m", "pip", "install", *user_flag]

            # ``--progress-bar raw`` (pip 23.2+) emits one ``Progress N of M``
            # line per chunk to stdout — perfect for streaming a humanised
            # download percentage to the in-app log instead of leaving the
            # user staring at "Скачиваю onnxruntime-gpu..." for 30 seconds
            # while a 245 MB wheel transfers in silence.
            cmd = [*base_cmd, "--progress-bar", "raw", *packages]
            log(f"Running: {' '.join(cmd)}")

            # Use subprocess with line streaming so the user sees progress.
            # CREATE_NO_WINDOW: ClipGen.exe is windowless (console=False), so
            # spawning a console-mode child like py.exe would otherwise pop a
            # black cmd window on top of the Logs tab. We pipe stdout/stderr
            # through the in-app log instead — the empty console is just noise.
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                text=True,
                encoding="utf-8",
                errors="replace",
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
                creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
            )
            # Die together with ClipGen instead of churning on as an orphan;
            # pip's wheel cache makes a re-run cheap.
            try:
                from ..utils.process_guard import attach_to_kill_job
                attach_to_kill_job(proc)
            except Exception:
                logger.debug("Could not attach pip to kill job", exc_info=True)

            assert proc.stdout is not None
            last_output = [time.monotonic()]

            def pump() -> None:
                try:
                    for line in proc.stdout:
                        last_output[0] = time.monotonic()
                        stripped = line.rstrip()
                        if stripped:
                            log(stripped)
                except Exception:
                    logger.debug("pip output pump stopped", exc_info=True)

            pump_thread = threading.Thread(
                target=pump, daemon=True, name="PipOutputPump"
            )
            pump_thread.start()

            # pip prints progress lines continuously while downloading, so a
            # long silence means it is genuinely stuck (dead mirror, hung
            # resolver) — without this guard the install thread would block
            # forever and the UI would show no error.
            INACTIVITY_LIMIT_SECONDS = 15 * 60
            while True:
                rc = proc.poll()
                if rc is not None:
                    break
                if time.monotonic() - last_output[0] > INACTIVITY_LIMIT_SECONDS:
                    proc.kill()
                    try:
                        proc.wait(timeout=10)
                    except Exception:
                        pass
                    msg = "pip produced no output for 15 minutes; installation aborted"
                    log(msg)
                    done(False, msg)
                    return
                time.sleep(0.5)

            pump_thread.join(timeout=5)
            if rc == 0:
                if engine == "parakeet":
                    # onnx-asr's CPU-only onnxruntime dependency overwrites
                    # the GPU build — put the CUDA-capable wheel back.
                    _reassert_onnxruntime_gpu(interp_argv, user_flag, log)
                done(True)
            else:
                done(False, f"pip exited with code {rc}")
        except Exception as exc:
            logger.exception("Dependency installation failed")
            done(False, str(exc))

    thread = threading.Thread(target=worker, daemon=True, name="WhisperDepsInstall")
    thread.start()
    return thread
