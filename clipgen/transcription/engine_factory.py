"""Factory: pick the right ASR engine manager from config.

Adding a new engine in the future:
    1. Implement ``BaseASRManager`` in ``<name>_manager.py``
    2. Add an ``elif`` branch below
    3. Add the engine's sub-config to ``DEFAULT_CONFIG["transcription"]``
"""

import logging
from typing import Any, Dict

from .base_asr_manager import BaseASRManager

logger = logging.getLogger('ClipGen')


SUPPORTED_ENGINES = ("whisper", "parakeet")


def create_asr_manager(config: Dict[str, Any], lang: Dict[str, Any]) -> BaseASRManager:
    """Instantiate the configured engine. Falls back to Whisper on unknown names."""
    engine = (config.get("transcription", {}).get("engine") or "whisper").lower()

    if engine == "parakeet":
        from .parakeet_manager import ParakeetModelManager
        return ParakeetModelManager(config, lang)

    if engine != "whisper":
        logger.warning("Unknown ASR engine '%s', falling back to whisper", engine)

    from .model_manager import WhisperModelManager
    return WhisperModelManager(config, lang)
