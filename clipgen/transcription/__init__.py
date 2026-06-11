"""Voice transcription package - Whisper-based push-to-talk speech-to-text.

This package is designed to be lazy-imported. Only when transcription is
enabled by the user, the heavy dependencies (faster-whisper, sounddevice,
numpy, CUDA libs) are loaded.

Public entry points:
    WhisperModelManager — load/unload model with idle auto-unload
    AudioRecorder       — sounddevice-based microphone capture
    Transcriber         — orchestrates record -> transcribe -> paste
    check_dependencies  — lightweight check that required packages exist

IMPORTANT: importing this package registers CUDA DLL search paths from
site-packages/nvidia/*/bin BEFORE any submodule that touches faster_whisper
or ctranslate2. This ordering is required on Windows — those native libs
resolve their CUDA dependencies at *import* time, not on first use, so the
DLL directory must already be registered when they are loaded. We learned
this the hard way: without it, WhisperModel() crashes with a 0xC0000005
access violation deep in CTranslate2.
"""

from .cuda_setup import setup_cuda_dll_paths

setup_cuda_dll_paths()

from .deps import check_dependencies, install_dependencies

__all__ = ["check_dependencies", "install_dependencies"]
