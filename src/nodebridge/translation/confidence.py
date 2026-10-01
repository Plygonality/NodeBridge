"""Translation confidence.

Every emitted operation is one of:

* ``EXACT`` — the target should reproduce the source behavior very closely.
* ``EQUIVALENT`` — the procedural intention is preserved. Samples, topology,
  or implementation details may differ.
* ``APPROXIMATE`` — the target can produce a similar result, not the full
  source behavior.
* ``UNSUPPORTED`` — no reliable target implementation exists.

NodeBridge does not claim pixel-identical or vertex-identical output unless
a translation is classified ``EXACT`` and the report does not list a
numerical limitation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Confidence(str, Enum):
    EXACT = "exact"
    EQUIVALENT = "equivalent"
    APPROXIMATE = "approximate"
    UNSUPPORTED = "unsupported"


_RANK = {
    Confidence.EXACT: 0,
    Confidence.EQUIVALENT: 1,
    Confidence.APPROXIMATE: 2,
    Confidence.UNSUPPORTED: 3,
}


class Strictness(str, Enum):
    """How far from exact a generated implementation is allowed to be."""

    EXACT_ONLY = "exact_only"
    ALLOW_EQUIVALENT = "allow_equivalent"
    ALLOW_APPROXIMATE = "allow_approximate"

    def allows(self, confidence: Confidence) -> bool:
        if confidence is Confidence.UNSUPPORTED:
            return False
        if self is Strictness.EXACT_ONLY:
            return confidence is Confidence.EXACT
        if self is Strictness.ALLOW_EQUIVALENT:
            return _RANK[confidence] <= _RANK[Confidence.EQUIVALENT]
        return _RANK[confidence] <= _RANK[Confidence.APPROXIMATE]


@dataclass
class Classification:
    """Why an operation received its confidence, and what was generated."""

    confidence: Confidence
    explanation: str
    implementation: str
    limitations: tuple[str, ...] = ()
    fallback: str | None = None
    emitted: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "confidence": self.confidence.value,
            "explanation": self.explanation,
            "implementation": self.implementation,
            "limitations": list(self.limitations),
            "fallback": self.fallback,
            "emitted": self.emitted,
        }


@dataclass
class TranslationRecord:
    """One operation after capability resolution."""

    operation_id: str
    operation_name: str
    operation: str
    classification: Classification
    source_types: tuple[str, ...] = ()
    notes: list[str] = field(default_factory=list)

    @property
    def confidence(self) -> Confidence:
        return self.classification.confidence
