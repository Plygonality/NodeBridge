"""Optional translation fallback.

The compiler does not call an LLM. ``fallback`` is ``None`` unless a later
integration supplies a :class:`TranslationFallbackProvider`. A provider may
only return an explanation string. It must not be required for generation.
"""

from __future__ import annotations

from typing import Protocol


class TranslationFallbackProvider(Protocol):
    """Suggest a human-readable note for an operation a backend cannot lower."""

    def suggest(self, operation: str, target: str, *, note: str = "") -> str | None:
        """Return an explanation, or ``None`` to leave the diagnostic unchanged."""
        ...


class NullFallback:
    """The default provider. It never invents a translation."""

    def suggest(self, operation: str, target: str, *, note: str = "") -> str | None:
        del operation, target, note
        return None
