"""Translator registry.

Translators register themselves instead of living in one ``if node.type``
cascade. A translator is a function plus the confidence metadata the report
uses when the function does not override it.

    @translator(
        OperationKind.SCATTER,
        "houdini",
        confidence=Confidence.EQUIVALENT,
        implementation="scatter::2.0",
        explanation="Houdini Scatter SOP distributes points on the input surface.",
    )
    def translate_scatter(operation, context):
        ...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from nodebridge.ir.semantic import Operation, OperationKind
from nodebridge.translation.confidence import Classification, Confidence


@dataclass
class Translator:
    operation: OperationKind
    target: str
    confidence: Confidence
    implementation: str
    explanation: str
    limitations: tuple[str, ...] = ()
    fallback: str | None = None
    function: Callable | None = None

    def classification(self) -> Classification:
        return Classification(
            confidence=self.confidence,
            explanation=self.explanation,
            implementation=self.implementation,
            limitations=self.limitations,
            fallback=self.fallback,
            emitted=self.confidence is not Confidence.UNSUPPORTED,
        )


@dataclass
class TranslatorRegistry:
    """Maps ``(operation, target)`` to one translator."""

    _items: dict[tuple[OperationKind, str], Translator] = field(default_factory=dict)

    def register(self, translator: Translator) -> None:
        key = (translator.operation, translator.target)
        if key in self._items:
            raise ValueError(
                f"Translator already registered for {translator.operation.value} -> {translator.target}"
            )
        self._items[key] = translator

    def get(self, operation: OperationKind, target: str) -> Translator | None:
        return self._items.get((operation, target))

    def for_target(self, target: str) -> list[Translator]:
        return [item for (kind, name), item in self._items.items() if name == target]

    def operations(self) -> list[OperationKind]:
        return sorted({kind for kind, _target in self._items}, key=lambda item: item.value)


REGISTRY = TranslatorRegistry()


def translator(
    operation: OperationKind,
    target: str,
    *,
    confidence: Confidence,
    implementation: str,
    explanation: str,
    limitations: tuple[str, ...] = (),
    fallback: str | None = None,
):
    """Register ``function`` as the translator for one operation and target."""

    def decorate(function: Callable) -> Callable:
        REGISTRY.register(
            Translator(
                operation=operation,
                target=target,
                confidence=confidence,
                implementation=implementation,
                explanation=explanation,
                limitations=limitations,
                fallback=fallback,
                function=function,
            )
        )
        return function

    return decorate


def require_translator(operation: Operation, target: str) -> Translator | None:
    return REGISTRY.get(operation.kind, target)
