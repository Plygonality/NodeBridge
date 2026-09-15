"""Semantic translation layer. Independent of source adapters and backends."""

from nodebridge.translators.compatibility import analyse_compatibility
from nodebridge.translators.registry import (
    DEFAULT_TRANSLATION_REGISTRY,
    TranslationHandler,
    TranslationRegistry,
    register_translation,
)
from nodebridge.translators.rules import RuleKind, TranslationRule

__all__ = [
    "DEFAULT_TRANSLATION_REGISTRY",
    "RuleKind",
    "TranslationHandler",
    "TranslationRegistry",
    "TranslationRule",
    "analyse_compatibility",
    "register_translation",
]
