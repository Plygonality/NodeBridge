"""Semantic translation layer. Independent of source adapters and backends."""

from nodebridge.translators.compatibility import analyse_compatibility
from nodebridge.translators.registry import (
    DEFAULT_TRANSLATION_REGISTRY,
    TranslationHandler,
    TranslationRegistry,
    register_translation,
    translate_node,
)
from nodebridge.translators.rules import RuleKind, TranslationRule
from nodebridge.translators.semantic import translate_graph

__all__ = [
    "DEFAULT_TRANSLATION_REGISTRY",
    "RuleKind",
    "TranslationHandler",
    "TranslationRegistry",
    "TranslationRule",
    "analyse_compatibility",
    "register_translation",
    "translate_graph",
    "translate_node",
]
