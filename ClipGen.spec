# -*- mode: python ; coding: utf-8 -*-

import os

from PyInstaller.utils.hooks import collect_submodules


block_cipher = None

hiddenimports = [
    "fileinput",
    "clipgen",
    "clipgen.app",
    "clipgen.core",
    "clipgen.api",
    "clipgen.hotkeys",
    "clipgen.ui",
    "clipgen.utils",
    "clipgen.utils.process_guard",
    "clipgen.testing",
    "clipgen.transcription",
    "clipgen.transcription.base_asr_manager",
    "clipgen.transcription.engine_factory",
    "clipgen.transcription.deps",
    "clipgen.transcription.diagnostics",
    "clipgen.transcription.cuda_setup",
    "clipgen.transcription.download_worker",
    "clipgen.transcription.filters",
    "clipgen.transcription.audio_recorder",
    "clipgen.transcription.model_manager",
    "clipgen.transcription.parakeet_manager",
    "clipgen.transcription.transcriber",
    "clipgen.transcription.worker_client",
]
hiddenimports += collect_submodules("tqdm")

# Heavy ML stacks are NOT bundled — users install them on demand via the
# Settings "Install / Download" button which writes to their user
# site-packages. The frozen entry point adds that path to sys.path at
# startup so imports resolve at runtime. This keeps the .exe small and
# lets the same .exe support multiple engines without bloating to >2 GB.
excludes = [
    # Whisper backend
    "faster_whisper",
    "ctranslate2",
    # Parakeet (ONNX) backend
    "onnxruntime",
    "onnx_asr",
    "onnx",
    # Shared audio + numerics + HF
    "sounddevice",
    "scipy",
    "numpy",
    "numpy.libs",
    "huggingface_hub",
    "openblas",
    "openblas64",
    # CUDA libraries (installed alongside whichever engine needs them)
    "nvidia",
    # Heavy stacks NeMo would pull in if installed (we use ONNX, not NeMo,
    # but exclude to be safe if user accidentally has them)
    "torch",
    "torchvision",
    "torchaudio",
    "transformers",
    "lightning",
    "lightning_fabric",
    "pytorch_lightning",
    "sklearn",
    "matplotlib",
    "cv2",
    "tensorflow",
    "av",
    "numba",
    "llvmlite",
    "einops",
    "functorch",
    "torchmetrics",
    "pandas",
    "sympy",
    "pytest",
]


vc_runtime_names = {
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
}


def _is_conflicting_vc_runtime(binary):
    dest = binary[0].replace("/", "\\").lower()
    name = os.path.basename(dest)
    if name not in vc_runtime_names:
        return False
    return dest.startswith("pyqt5\\qt5\\bin\\") or "\\" not in dest


a = Analysis(
    ["clipgen/main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("lang", "lang"),
        ("ClipGen.ico", "."),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# PyQt5 wheels bundle old VC runtime DLLs (14.26). CTranslate2 4.7.1 is
# sensitive to that in frozen apps and crashes inside models.Whisper().
# Keep PyQt/Qt itself, but force a single modern VC runtime set at bundle root.
a.binaries = [binary for binary in a.binaries if not _is_conflicting_vc_runtime(binary)]

for dll_name in sorted(vc_runtime_names):
    dll_path = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", dll_name)
    if os.path.isfile(dll_path):
        a.binaries.append((dll_name, dll_path, "BINARY"))

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ClipGen",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="ClipGen.ico",
)
