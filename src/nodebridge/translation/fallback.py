"""Optional fallback when the compiler has no target implementation.

The default provider is ``None``. Graph translation does not call an LLM,
a cloud API, or any local model. A later provider can implement this
interface and return a comment. The compiler will not execute that text.
"""

from __future__ import annotations

from typing import Protocol

from nodebridge.ir.semantic import Operation


class TranslationFallbackProvider(Protocol):
    """Suggest a human-readable fallback for an unsupported operation."""

    def suggest(self, operation: Operation, target: str, reason: str) -> str | None:
        """Return a comment, or ``None`` when there is nothing to add."""
