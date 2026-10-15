"""Optional fallback interface for operations no translator handles.

NodeBridge's translation is deterministic and does not need an AI
service. A ``TranslationFallbackProvider`` may be plugged in later (for
example an LLM-backed suggester), but its output is only ever added to
the report as a suggestion for a human; it is never executed or counted
as a translation. The default is ``fallback = None``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class FallbackSuggestion:
    summary: str
    code: str = ""
    provider: str = ""


@runtime_checkable
class TranslationFallbackProvider(Protocol):
    name: str

    def suggest(self, op, graph, target: str) -> FallbackSuggestion | None:  # pragma: no cover - protocol
        ...
