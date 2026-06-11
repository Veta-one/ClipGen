"""Diagnostics report for the Whisper transcription runtime."""

import importlib
import importlib.metadata
import importlib.util
import os
import platform
import sys
import time
from typing import Any, Dict, Iterable, List

from ..core.constants import APPLICATION_PATH
from .cuda_setup import detect_gpu, setup_cuda_dll_paths
from .deps import _find_external_python, check_runtime_health
from .model_manager import (
    MODEL_REPO_MAP,
    _repo_cache_dir,
    _snapshot_validation_errors,
    get_model_snapshot_path,
)


PACKAGES = (
    "faster_whisper",
    "ctranslate2",
    "numpy",
    "sounddevice",
    "huggingface_hub",
    "httpx",
    "requests",
    "urllib3",
    "certifi",
    "tqdm",
)


def _line(key: str, value: Any) -> str:
    return f"{key}: {value}"


def _module_origin(name: str) -> str:
    try:
        spec = importlib.util.find_spec(name)
    except Exception as exc:
        return f"error: {exc}"
    if spec is None:
        return "not found"
    return spec.origin or str(spec.submodule_search_locations or "")


def _package_version(name: str) -> str:
    dist_name = name.replace("_", "-")
    try:
        return importlib.metadata.version(dist_name)
    except Exception:
        try:
            mod = importlib.import_module(name)
            return str(getattr(mod, "__version__", "unknown"))
        except Exception:
            return "not installed"


def _safe_import_report(name: str) -> List[str]:
    lines = [
        _line(f"{name}.version", _package_version(name)),
        _line(f"{name}.origin", _module_origin(name)),
    ]
    return lines


def _vc_runtime_lines() -> List[str]:
    lines: List[str] = []
    search_roots: List[str] = []
    if getattr(sys, "frozen", False):
        search_roots.append(getattr(sys, "_MEIPASS", ""))
    search_roots.append(os.path.dirname(sys.executable))
    search_roots.append(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32"))

    names = (
        "msvcp140.dll",
        "msvcp140_1.dll",
        "msvcp140_2.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
    )
    seen = set()
    for root in search_roots:
        if not root or not os.path.isdir(root):
            continue
        for name in names:
            path = os.path.join(root, name)
            if not os.path.isfile(path) or path in seen:
                continue
            seen.add(path)
            try:
                size = os.path.getsize(path)
            except OSError:
                size = "?"
            lines.append(_line("vc_runtime", f"{path} ({size} bytes)"))
    return lines


def _model_cache_lines(config: Dict[str, Any]) -> List[str]:
    tr = config.get("transcription", {}) if isinstance(config, dict) else {}
    model_name = tr.get("model", "large-v3")
    repo = MODEL_REPO_MAP.get(model_name, model_name)
    lines = [
        _line("model.selected", model_name),
        _line("model.repo", repo),
        _line("model.path_override", tr.get("model_path_override", "")),
        _line("model.isolate_inference_process", tr.get("isolate_inference_process", True)),
    ]
    snapshot = get_model_snapshot_path(model_name)
    lines.append(_line("model.valid_snapshot", snapshot or "none"))
    if "/" in repo:
        snapshots = os.path.join(_repo_cache_dir(repo), "snapshots")
        if os.path.isdir(snapshots):
            try:
                for name in os.listdir(snapshots):
                    path = os.path.join(snapshots, name)
                    if os.path.isdir(path):
                        errors = _snapshot_validation_errors(path)
                        status = "valid" if not errors else "invalid: " + "; ".join(errors)
                        lines.append(_line("model.snapshot", f"{path} => {status}"))
            except OSError as exc:
                lines.append(_line("model.snapshot_error", exc))
    return lines


def _audio_lines() -> List[str]:
    lines: List[str] = []
    try:
        import sounddevice as sd
        host_apis = sd.query_hostapis()
        lines.append(_line("sounddevice.default", sd.default.device))
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) <= 0:
                continue
            host_name = ""
            host_idx = dev.get("hostapi", -1)
            if 0 <= host_idx < len(host_apis):
                host_name = host_apis[host_idx].get("name", "")
            lines.append(
                _line(
                    "audio.input",
                    f"{idx}: {dev.get('name')} ({host_name}), channels={dev.get('max_input_channels')}",
                )
            )
    except Exception as exc:
        lines.append(_line("audio.error", f"{type(exc).__name__}: {exc}"))
    return lines


def build_diagnostics_lines(config: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    lines.append("ClipGen transcription diagnostics")
    lines.append("=" * 36)
    lines.append(_line("timestamp", time.strftime("%Y-%m-%d %H:%M:%S")))
    lines.append(_line("platform", platform.platform()))
    lines.append(_line("python", sys.version.replace("\n", " ")))
    lines.append(_line("executable", sys.executable))
    lines.append(_line("frozen", getattr(sys, "frozen", False)))
    lines.append(_line("application_path", APPLICATION_PATH))
    lines.append(_line("sys_path_first", sys.path[:5]))
    lines.append(_line("external_python", _find_external_python()))
    lines.append("")

    lines.append("[packages]")
    for package in PACKAGES:
        lines.extend(_safe_import_report(package))
    lines.append("")

    lines.append("[ctranslate2]")
    try:
        setup_cuda_dll_paths()
        import ctranslate2
        lines.append(_line("ct2.version", getattr(ctranslate2, "__version__", "unknown")))
        lines.append(_line("ct2.cuda_devices", ctranslate2.get_cuda_device_count()))
        try:
            lines.append(_line("ct2.compute.cpu", sorted(ctranslate2.get_supported_compute_types("cpu"))))
        except Exception as exc:
            lines.append(_line("ct2.compute.cpu.error", exc))
        try:
            lines.append(_line("ct2.compute.cuda", sorted(ctranslate2.get_supported_compute_types("cuda"))))
        except Exception as exc:
            lines.append(_line("ct2.compute.cuda.error", exc))
    except Exception as exc:
        lines.append(_line("ct2.error", f"{type(exc).__name__}: {exc}"))
    lines.append("")

    lines.append("[runtime_health]")
    try:
        health = check_runtime_health(include_cuda=True)
        for key in ("ok", "missing", "errors", "warnings"):
            lines.append(_line(f"runtime.{key}", health.get(key)))
        lines.append(_line("runtime.ctranslate2", health.get("ctranslate2")))
        lines.append(_line("runtime.cuda", health.get("cuda")))
        lines.append(_line("runtime.audio", health.get("audio")))
        lines.append(_line("runtime.vc_runtime", health.get("vc_runtime")))
    except Exception as exc:
        lines.append(_line("runtime.error", f"{type(exc).__name__}: {exc}"))
    lines.append("")

    lines.append("[gpu]")
    for key, value in detect_gpu().items():
        lines.append(_line(f"gpu.{key}", value))
    lines.append("")

    lines.append("[model_cache]")
    lines.extend(_model_cache_lines(config))
    lines.append("")

    lines.append("[audio]")
    lines.extend(_audio_lines())
    lines.append("")

    lines.append("[vc_runtime]")
    lines.extend(_vc_runtime_lines())
    lines.append("")

    return lines


def write_diagnostics_report(config: Dict[str, Any], path: str = None) -> str:
    """Write a diagnostics report and return its path."""
    if path is None:
        path = os.path.join(APPLICATION_PATH, "transcription_diagnostics.txt")
    lines = build_diagnostics_lines(config)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(str(line) for line in lines))
        f.write("\n")
    return path
