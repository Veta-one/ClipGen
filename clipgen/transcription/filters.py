"""Statistical hallucination filter for Whisper output.

Whisper occasionally produces phantom phrases on silent or noisy audio
(typical examples: "Subtitles by amara.org", "Спасибо за просмотр").
This module filters them based on segment-level metadata that
faster-whisper exposes (avg_logprob, no_speech_prob, compression_ratio)
and a user-editable blacklist.
"""

import re
import string
from typing import Iterable, List, Optional, Tuple


# Conservative thresholds taken from superwhisper0 / OpenAI Whisper recommendations.
DEFAULT_MAX_NO_SPEECH_PROB = 0.6
DEFAULT_MIN_AVG_LOGPROB = -1.0
DEFAULT_MAX_COMPRESSION_RATIO = 2.4


_PUNCT_TRANSLATION = str.maketrans("", "", string.punctuation + "«»“”„…—–")


def _normalize_for_match(text: str) -> str:
    text = (text or "").lower().translate(_PUNCT_TRANSLATION)
    return re.sub(r"\s+", " ", text).strip()


def filter_segments(
    segments: Iterable,
    blacklist: Optional[List[str]] = None,
    max_no_speech_prob: float = DEFAULT_MAX_NO_SPEECH_PROB,
    min_avg_logprob: float = DEFAULT_MIN_AVG_LOGPROB,
    max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO,
) -> List:
    """Filter Whisper segments using statistical signals + blacklist.

    Args:
        segments: Iterable of faster-whisper Segment objects.
        blacklist: Phrases that mark a segment as a hallucination
                   (case-insensitive substring match).
        max_no_speech_prob: Drop if probability of no-speech > threshold.
        min_avg_logprob: Drop if average log-probability < threshold.
        max_compression_ratio: Drop if compression ratio > threshold
                              (a strong sign of repetition).

    Returns:
        Filtered list of segments preserving original order.
    """
    blacklist_lower = [_normalize_for_match(b) for b in (blacklist or []) if b.strip()]
    kept: List = []
    for seg in segments:
        text = (getattr(seg, "text", "") or "").strip()
        if not text:
            continue

        no_speech = getattr(seg, "no_speech_prob", 0.0) or 0.0
        avg_logprob = getattr(seg, "avg_logprob", 0.0) or 0.0
        compression = getattr(seg, "compression_ratio", 0.0) or 0.0

        if no_speech > max_no_speech_prob:
            continue
        if avg_logprob < min_avg_logprob:
            continue
        if compression > max_compression_ratio:
            continue

        text_lower = _normalize_for_match(text)
        if any(bad in text_lower for bad in blacklist_lower):
            continue

        kept.append(seg)
    return kept


def filter_segments_with_reasons(
    segments: Iterable,
    blacklist: Optional[List[str]] = None,
    max_no_speech_prob: float = DEFAULT_MAX_NO_SPEECH_PROB,
    min_avg_logprob: float = DEFAULT_MIN_AVG_LOGPROB,
    max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO,
) -> Tuple[List, List[Tuple[str, str]]]:
    """Filter segments and return dropped-text reasons for diagnostics/logs."""
    blacklist_lower = [_normalize_for_match(b) for b in (blacklist or []) if b.strip()]
    kept: List = []
    dropped: List[Tuple[str, str]] = []
    for seg in segments:
        text = (getattr(seg, "text", "") or "").strip()
        if not text:
            continue

        no_speech = getattr(seg, "no_speech_prob", 0.0) or 0.0
        avg_logprob = getattr(seg, "avg_logprob", 0.0) or 0.0
        compression = getattr(seg, "compression_ratio", 0.0) or 0.0
        text_lower = _normalize_for_match(text)

        reason = ""
        if no_speech > max_no_speech_prob:
            reason = f"no_speech_prob={no_speech:.2f}"
        elif avg_logprob < min_avg_logprob:
            reason = f"avg_logprob={avg_logprob:.2f}"
        elif compression > max_compression_ratio:
            reason = f"compression_ratio={compression:.2f}"
        elif any(bad in text_lower for bad in blacklist_lower):
            reason = "blacklist"

        if reason:
            dropped.append((text, reason))
        else:
            kept.append(seg)
    return kept, dropped


def join_segments(segments: Iterable) -> str:
    """Join segment texts into a single normalized string."""
    parts = [(getattr(s, "text", "") or "").strip() for s in segments]
    return " ".join(p for p in parts if p).strip()
