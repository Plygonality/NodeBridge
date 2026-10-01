"""Translation confidence classification.

EXACT
    The target should reproduce the source behaviour to a very high degree.
EQUIVALENT
    The procedural intent is preserved, but implementation details or
    generated samples (e.g. random point positions) may differ.
APPROXIMATE
    The target produces a similar result but not the full source behaviour.
UNSUPPORTED
    No reliable target implementation exists. A placeholder is generated
    and the gap is reported; it is never silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Confidence(str, Enum):
    EXACT = "EXACT"
    EQUIVALENT = "EQUIVALENT"
    APPROXIMATE = "APPROXIMATE"
    UNSUPPORTED = "UNSUPPORTED"

    @property
    def rank(self) -> int:
        return _RANK[self]

    @property
    def symbol(self) -> str:
        return _SYMBOL[self]

    @property
    def label(self) -> str:
        return self.value.title()

    def worst(self, other: "Confidence") -> "Confidence":
        return self if self.rank >= other.rank else other

    def allowed_by(self, strictness: "Strictness") -> bool:
        return self.rank <= strictness.max_rank


_RANK = {Confidence.EXACT: 0, Confidence.EQUIVALENT: 1, Confidence.APPROXIMATE: 2, Confidence.UNSUPPORTED: 3}
_SYMBOL = {Confidence.EXACT: "✓", Confidence.EQUIVALENT: "≈", Confidence.APPROXIMATE: "~", Confidence.UNSUPPORTED: "✕"}


class Strictness(str, Enum):
    EXACT_ONLY = "EXACT_ONLY"
    ALLOW_EQUIVALENT = "ALLOW_EQUIVALENT"
    ALLOW_APPROXIMATE = "ALLOW_APPROXIMATE"

    @property
    def max_rank(self) -> int:
        return {"EXACT_ONLY": 0, "ALLOW_EQUIVALENT": 1, "ALLOW_APPROXIMATE": 2}[self.value]


@dataclass
class Classification:
    """How one semantic operation will be realized on a target."""

    confidence: Confidence
    explanation: str = ""
    implementation: str = ""
    limitations: list[str] = field(default_factory=list)
    fallback: str = ""

    def downgrade(self, confidence: Confidence, reason: str) -> "Classification":
        """Return a copy at ``confidence`` or worse, recording why."""
        worse = self.confidence.worst(confidence)
        limitations = list(self.limitations)
        if reason and reason not in limitations:
            limitations.append(reason)
        return Classification(worse, self.explanation, self.implementation, limitations, self.fallback)

    def as_dict(self) -> dict:
        return {
            "confidence": self.confidence.value,
            "explanation": self.explanation,
            "implementation": self.implementation,
            "limitations": self.limitations,
            "fallback": self.fallback,
        }


UNSUPPORTED_DEFAULT = Classification(
    Confidence.UNSUPPORTED,
    "No NodeBridge translation is implemented for this operation on this target.",
    "placeholder",
    [],
    "A placeholder node with a note is generated so the network stays connected.",
)
