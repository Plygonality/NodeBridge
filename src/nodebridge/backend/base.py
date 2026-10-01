"""Target backend contract.

A backend classifies semantic operations and generates code that builds a
native graph. It does not bake geometry.
"""

from __future__ import annotations

from typing import Protocol

from nodebridge.ir.semantic import OperationKind, SemanticGraph
from nodebridge.translation.confidence import Classification, Confidence


class TargetBackend(Protocol):
    """Generate a native DCC script from semantic IR."""

    id: str

    def supports(self, operation: OperationKind) -> bool:
        """Return True when a translator exists and it is not unsupported."""

    def classify(self, operation: OperationKind) -> Classification:
        """Default classification for an operation, before per-node overrides."""

    def generate(self, graph: SemanticGraph, options: object) -> tuple[str, list]:
        """Return generated source and one record per semantic operation."""
