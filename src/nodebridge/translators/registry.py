"""Registry of semantic translation handlers.

New operations register themselves here. The central translator does not
need a giant lookup table edited by hand for every node.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from nodebridge.core.diagnostics import TranslationStatus
from nodebridge.core.exceptions import TranslationError
from nodebridge.core.node import IRNode

TranslationFn = Callable[..., Any]


@dataclass(frozen=True)
class TranslationHandler:
    """A registered mapping from an IR operation to a target backend."""

    operation: str
    target: str
    function: TranslationFn
    status: TranslationStatus = TranslationStatus.EXACT
    kind: str = "exact"


@dataclass
class TranslationRegistry:
    """Operation × target → handler.

    Kinds:

    * ``exact`` — one semantic operation, faithful mapping
    * ``compound`` — expands to several target operations
    * ``procedural`` — generated code / wrangle / snippet
    * ``fallback`` — used only when no exact/compound handler exists
    """

    _handlers: dict[tuple[str, str], TranslationHandler] = field(default_factory=dict)
    _fallbacks: dict[tuple[str, str], TranslationHandler] = field(default_factory=dict)

    def register(self, handler: TranslationHandler) -> TranslationHandler:
        key = (handler.operation, handler.target)
        store = self._fallbacks if handler.kind == "fallback" else self._handlers
        if key in store:
            raise TranslationError(
                f"Translation already registered for {handler.operation} → {handler.target}"
            )
        store[key] = handler
        return handler

    def lookup(self, operation: str, target: str) -> TranslationHandler | None:
        """Return the primary handler, or a fallback, or ``None``."""
        key = (operation, target)
        if key in self._handlers:
            return self._handlers[key]
        return self._fallbacks.get(key)

    def targets_for(self, operation: str) -> list[str]:
        """Targets that have any handler for *operation*."""
        names = {
            target
            for (op, target) in list(self._handlers) + list(self._fallbacks)
            if op == operation
        }
        return sorted(names)

    def operations_for(self, target: str) -> list[str]:
        """Operations that have any handler for *target*."""
        names = {
            op
            for (op, tgt) in list(self._handlers) + list(self._fallbacks)
            if tgt == target
        }
        return sorted(names)


DEFAULT_TRANSLATION_REGISTRY = TranslationRegistry()


def register_translation(
    source: str,
    target: str,
    *,
    status: TranslationStatus = TranslationStatus.EXACT,
    kind: str = "exact",
    registry: TranslationRegistry | None = None,
) -> Callable[[TranslationFn], TranslationFn]:
    """Decorator that registers a translation function.

    Example::

        @register_translation(source="geometry.transform", target="houdini")
        def translate_transform(node: IRNode) -> GraphFragment:
            ...
    """

    catalog = registry or DEFAULT_TRANSLATION_REGISTRY

    def decorator(function: TranslationFn) -> TranslationFn:
        catalog.register(
            TranslationHandler(
                operation=source,
                target=target,
                function=function,
                status=status,
                kind=kind,
            )
        )
        return function

    return decorator


def translate_node(
    node: IRNode,
    target: str,
    *,
    registry: TranslationRegistry | None = None,
    **kwargs: Any,
) -> Any:
    """Dispatch *node* through the registry. Raises if nothing is registered."""
    catalog = registry or DEFAULT_TRANSLATION_REGISTRY
    handler = catalog.lookup(node.operation, target)
    if handler is None:
        raise TranslationError(
            f"No translation registered for {node.operation!r} → {target!r}"
        )
    return handler.function(node, **kwargs)
