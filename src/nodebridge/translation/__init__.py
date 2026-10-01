"""Public translation confidence and optional fallback hooks."""

from nodebridge.translation.confidence import Confidence, confidence_for, summarize_confidence
from nodebridge.translation.fallback import NullFallback, TranslationFallbackProvider

__all__ = [
    "Confidence",
    "NullFallback",
    "TranslationFallbackProvider",
    "confidence_for",
    "summarize_confidence",
]
