"""Application constants and default configuration."""

import os
import sys
import ctypes
import logging

# Version
__version__ = "2.4.1"

# Windows App ID for taskbar grouping
APP_ID = 'company.clipgen.app.1.0'
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)

# Application path detection
if getattr(sys, 'frozen', False):
    APPLICATION_PATH = os.path.dirname(sys.executable)
elif __file__:
    APPLICATION_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(APPLICATION_PATH)


def resource_path(relative_path: str) -> str:
    """Get correct path to resource, works in both .py and .exe."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# Logger setup
logger = logging.getLogger('ClipGen')
logger.setLevel(logging.INFO)
_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.ERROR)
_console_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
)
logger.addHandler(_console_handler)


# Default configuration
DEFAULT_CONFIG = {
    "provider": "gemini",
    "openai_base_url": "https://openrouter.ai/api/v1",
    "openai_api_keys": [
        {"key": "", "name": "Main Key", "usage_timestamps": [], "active": True}
    ],
    "openai_models": [
        {"name": "deepseek/deepseek-chat", "test_status": "not_tested", "test_duration": 0.0},
        {"name": "anthropic/claude-3.5-sonnet", "test_status": "not_tested", "test_duration": 0.0},
        {"name": "openai/gpt-4o", "test_status": "not_tested", "test_duration": 0.0}
    ],
    "openai_active_model": "deepseek/deepseek-chat",
    "api_keys": [
        {"key": "YOUR_API_KEY_HERE", "name": "Main Key", "usage_timestamps": [], "active": True}
    ],
    "gemini_models": [
        {"name": "gemini-2.0-flash"},
        {"name": "gemini-1.5-pro"},
        {"name": "gemini-1.5-flash"}
    ],
    "active_model": "gemini-2.0-flash",
    "language": "en",
    "api_keys_visible": False,
    "auto_switch_api_keys": True,
    "proxy_enabled": False,
    "proxy_type": "HTTP",
    "proxy_string": "",
    "ui_scale": 1.0,
    "skipped_version": "",
    "hotkeys": [
        {
            "combination": "Ctrl+F1",
            "name": "F1 Text Correction",
            "log_color": "#FFFFFF",
            "type": "text_action",
            "prompt": "Fix grammar and spelling. Correct any typos, grammatical errors, and punctuation issues in the following text while maintaining its original meaning and style. Only provide the corrected text, nothing else.",
            "use_custom_model": False,
            "custom_provider": None,
            "custom_model": None,
            "learning_mode": False,
            "learning_prompt": "",
            "transcription_language": "auto",
            "transcription_initial_prompt": "",
            "transcription_strip_trailing_period": False
        },
        {
            "combination": "Ctrl+F2",
            "name": "F2 Translation",
            "log_color": "#FBB6CE",
            "type": "text_action",
            "prompt": "Translate to Russian. Provide only the translation, nothing else.",
            "use_custom_model": False,
            "custom_provider": None,
            "custom_model": None,
            "learning_mode": False,
            "learning_prompt": "",
            "transcription_language": "auto",
            "transcription_initial_prompt": "",
            "transcription_strip_trailing_period": False
        }
    ],
    "transcription": {
        "enabled": False,
        "engine": "whisper",
        "default_language": "auto",
        "preload_on_start": False,
        "auto_unload_minutes": 5,
        "filter_hallucinations": True,
        "hallucination_blacklist": [
            "Субтитры сделал",
            "Продолжение следует",
            "amara.org",
            "Спасибо за просмотр",
            "Subtitles by",
            "Thanks for watching"
        ],
        "feedback_sounds": True,
        "streaming_enabled": False,
        "streaming_interval": 1.5,
        "audio": {
            "sample_rate": 16000,
            "blocksize": 1024,
            "latency": "low",
            "input_device": None,
            "max_record_seconds": 120
        },
        "whisper": {
            "model": "large-v3",
            "device": "auto",
            "compute_type": "float16",
            "beam_size": 1,
            "vad_filter": True,
            "vad_min_duration_seconds": 1.0,
            "whisper_initial_prompt": "",
            "postprocess_prompt": "",
            "model_path_override": "",
            "isolate_inference_process": True
        },
        "parakeet": {
            "model": "nemo-parakeet-tdt-0.6b-v3",
            "providers": ["CUDA", "CPU"],
            "quantization": "",
            "model_path_override": ""
        }
    },
    "default_learning_prompt": """You are a language tutor. Analyze the corrections made to the text.

IGNORE (don't explain):
- Typos (random letter mistakes like "helo" -> "hello")
- Symbol replacements ($ € ₽)
- Capitalization changes

EXPLAIN only real mistakes:
- Spelling: why the word is spelled this way (rule + brief explanation)
- Punctuation: why comma/dash is needed here
- Grammar: if word form was corrected

Format:
**mistake** -> **correct**
*Rule: brief explanation*

---
Original: {original}
Result: {result}

If only typos were fixed — return empty string."""
}
