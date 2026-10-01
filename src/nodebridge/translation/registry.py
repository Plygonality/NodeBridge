"""Translator registry.

Translators are registered per (target, context, semantic kind)::

    @translator("SCATTER", target="houdini", context="sop",
                confidence=Confidence.EQUIVALENT,
                implementation="scatter SOP",
                explanation="...")
    def scatter(ctx, op): ...

Each translator carries its own capability metadata (default confidence,
implementation, limitations, fallback) and an optional ``classify``
function for configuration-dependent confidence. The capability matrix
is derived from this metadata; nothing is hardcoded in UI tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .confidence import Classification, Confidence


@dataclass
class Translator:
    kind: str
    target: str
    context: str
    fn: Callable[..., Any]
    confidence: Confidence
    implementation: str = ""
    explanation: str = ""
    limitations: tuple[str, ...] = ()
    fallback: str = ""
    classify_fn: Callable[..., Classification | None] | None = None

    def default_classification(self) -> Classification:
        return Classification(self.confidence, self.explanation, self.implementation, list(self.limitations), self.fallback)

    def classify(self, op: Any, graph: Any) -> Classification:
        base = self.default_classification()
        if self.classify_fn is not None:
            result = self.classify_fn(op, graph, base)
            if result is not None:
                return result
        return base


@dataclass
class TranslatorRegistry:
    _items: dict[tuple[str, str, str], Translator] = field(default_factory=dict)

    def register(self, item: Translator) -> Translator:
        key = (item.target, item.context, item.kind)
        if key in self._items:
            raise ValueError(f"translator already registered for {key}")
        self._items[key] = item
        return item

    def get(self, target: str, context: str, kind: str) -> Translator | None:
        return self._items.get((target, context, kind))

    def for_target(self, target: str, context: str | None = None) -> list[Translator]:
        return [t for (tg, ctx, _), t in sorted(self._items.items()) if tg == target and (context is None or ctx == context)]

    def kinds(self, target: str, context: str) -> set[str]:
        return {k for (tg, ctx, k) in self._items if tg == target and ctx == context}

    def __len__(self) -> int:
        return len(self._items)


REGISTRY = TranslatorRegistry()


def translator(
    kinds: str | Iterable[str],
    *,
    target: str,
    context: str,
    confidence: Confidence,
    implementation: str = "",
    explanation: str = "",
    limitations: Iterable[str] = (),
    fallback: str = "",
    classify: Callable[..., Classification | None] | None = None,
    registry: TranslatorRegistry | None = None,
):
    """Register a translator function for one or more semantic kinds."""

    names = [kinds] if isinstance(kinds, str) else list(kinds)

    target_registry = registry if registry is not None else REGISTRY

    def decorator(fn):
        for kind in names:
            target_registry.register(
                Translator(kind, target, context, fn, confidence, implementation, explanation, tuple(limitations), fallback, classify)
            )
        return fn

    return decorator
