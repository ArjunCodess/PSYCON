"""Transparent PRD language and conversation features for English transcripts."""

from __future__ import annotations

import re
from collections import Counter
from enum import Enum
from typing import Any

import numpy as np

from ml.src.transcription import TranscriptionResult, TranscriptionStatus


LANGUAGE_FEATURE_EXTRACTOR = "psycon_language"
_WORD = re.compile(r"[a-zA-Z]+(?:'[a-zA-Z]+)?")
_SENTENCE = re.compile(r"[^.!?]+[.!?]?")
_POSITIVE = frozenset(
    {"calm", "comfortable", "confident", "enjoy", "fine", "glad", "good", "happy", "hope", "relaxed", "safe", "well"}
)
_NEGATIVE = frozenset(
    {"afraid", "angry", "anxious", "bad", "difficult", "frustrated", "sad", "scared", "stress", "stressed", "stressful", "tired", "unhappy", "upset", "worried"}
)
_EMOTIONS = {
    "positive": _POSITIVE,
    "anxiety": frozenset({"afraid", "anxious", "nervous", "panic", "scared", "stress", "stressed", "stressful", "tense", "worried"}),
    "sadness": frozenset({"cry", "down", "lonely", "sad", "unhappy"}),
    "anger": frozenset({"angry", "annoyed", "frustrated", "hate", "upset"}),
    "fatigue": frozenset({"exhausted", "sleepy", "tired", "weary"}),
}
_STOPWORDS = frozenset(
    {"a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "i", "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "was", "we", "with", "you"}
)


class LanguageFeatureStatus(str, Enum):
    COMPLETE = "complete"
    INSUFFICIENT_TEXT = "insufficient_text"
    UNSUPPORTED_LANGUAGE = "unsupported_language"
    TRANSCRIPTION_UNAVAILABLE = "transcription_unavailable"


def extract_language_features(transcription: TranscriptionResult) -> dict[str, Any]:
    """Return auditable lexical features without making a clinical interpretation."""

    if transcription.status is not TranscriptionStatus.COMPLETE:
        return _empty(
            LanguageFeatureStatus.TRANSCRIPTION_UNAVAILABLE,
            f"transcription_status_{transcription.status.value}",
        )
    if transcription.language != "en":
        language = transcription.language or "unknown"
        return _empty(
            LanguageFeatureStatus.UNSUPPORTED_LANGUAGE,
            f"language_{language}_not_supported_by_english_lexicons",
        )

    words = [word.lower() for word in _WORD.findall(transcription.text)]
    if len(words) < 3:
        return _empty(LanguageFeatureStatus.INSUFFICIENT_TEXT, "fewer_than_3_words")
    sentences = [sentence.strip() for sentence in _SENTENCE.findall(transcription.text) if _WORD.search(sentence)]
    counts = Counter(words)
    positive_count = sum(counts[word] for word in _POSITIVE)
    negative_count = sum(counts[word] for word in _NEGATIVE)
    sentiment_score = (positive_count - negative_count) / max(1, positive_count + negative_count)
    emotion_counts = {
        name: sum(counts[word] for word in lexicon)
        for name, lexicon in _EMOTIONS.items()
    }
    transitions = _topic_transitions(transcription)
    speech_duration = sum(segment.end_s - segment.start_s for segment in transcription.segments)
    total_span = (
        transcription.segments[-1].end_s - transcription.segments[0].start_s
        if transcription.segments
        else 0.0
    )
    pause_duration = max(0.0, total_span - speech_duration)
    return {
        "status": LanguageFeatureStatus.COMPLETE.value,
        "extractor": LANGUAGE_FEATURE_EXTRACTOR,
        "reasons": [],
        "word_count": len(words),
        "unique_word_count": len(counts),
        "vocabulary_diversity": len(counts) / len(words),
        "sentence_count": len(sentences),
        "mean_sentence_length_words": len(words) / max(1, len(sentences)),
        "sentiment_score": sentiment_score,
        "sentiment_label": "positive" if sentiment_score > 0 else "negative" if sentiment_score < 0 else "neutral",
        "emotion_word_counts": emotion_counts,
        "topic_transition_mean": float(np.mean(transitions)) if transitions else 0.0,
        "topic_transition_count": sum(value >= 0.7 for value in transitions),
        "speech_segment_count": len(transcription.segments),
        "speech_duration_s": speech_duration,
        "pause_duration_s": pause_duration,
        "words_per_minute": len(words) / speech_duration * 60 if speech_duration > 0 else 0.0,
        "speaker_diarization_available": False,
    }


def _topic_transitions(transcription: TranscriptionResult) -> list[float]:
    content_sets = [
        {word.lower() for word in _WORD.findall(segment.text) if word.lower() not in _STOPWORDS}
        for segment in transcription.segments
    ]
    transitions: list[float] = []
    for previous, current in zip(content_sets, content_sets[1:]):
        union = previous | current
        transitions.append(1.0 - len(previous & current) / len(union) if union else 0.0)
    return transitions


def _empty(status: LanguageFeatureStatus, reason: str) -> dict[str, Any]:
    return {
        "status": status.value,
        "extractor": LANGUAGE_FEATURE_EXTRACTOR,
        "reasons": [reason],
    }
