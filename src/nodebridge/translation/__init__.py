"""Confidence labels, translator registration, and the fallback interface."""

from nodebridge.translation.confidence import Classification, Confidence, Strictness, TranslationRecord
from nodebridge.translation.fallback import TranslationFallbackProvider
from nodebridge.translation.registry import REGISTRY, translator

__all__ = [
    "REGISTRY",
    "Classification",
    "Confidence",
    "Strictness",
    "TranslationFallbackProvider",
    "TranslationRecord",
    "translator",
]
