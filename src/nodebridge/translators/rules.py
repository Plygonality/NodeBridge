"""Translation rule kinds.

Rules describe *how* an operation should be realized, not a flat
node-name substitution table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RuleKind(str, Enum):
    """How a rule expands an IR operation."""

    EXACT = "exact"
    COMPOUND = "compound"
    PROCEDURAL = "procedural"
    FALLBACK = "fallback"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class TranslationRule:
    """Declarative description of one operation → target realization."""

    operation: str
    target: str
    kind: RuleKind = RuleKind.EXACT
    recipe: str = ""
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
