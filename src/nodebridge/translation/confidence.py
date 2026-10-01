"""User-facing translation confidence.

Internal recipes still use the finer :class:`TranslationStatus` values
(``LOWERED``, ``CUSTOM_CODE``, ``BAKED``). Reports and the Blender panel
collapse those into four classes:

* ``EXACT`` — target behavior should match the source to a very high degree.
* ``EQUIVALENT`` — the procedural intention is preserved. Implementation
  details, topology, or random samples may differ.
* ``APPROXIMATE`` — a similar result is possible, but not the full behavior.
* ``UNSUPPORTED`` — no reliable target implementation exists.
"""

from __future__ import annotations

from collections import Counter
from enum import Enum

from nodebridge.core.diagnostics import TranslationReport, TranslationStatus


class Confidence(str, Enum):
    EXACT = "exact"
    EQUIVALENT = "equivalent"
    APPROXIMATE = "approximate"
    UNSUPPORTED = "unsupported"


_EQUIVALENT_VALUES = frozenset({"lowered", "custom_code"})
_APPROXIMATE_VALUES = frozenset({"approximate", "baked"})


def confidence_for(status: TranslationStatus | str) -> Confidence:
    """Map an internal status onto the four public classes."""
    value = status.value if isinstance(status, TranslationStatus) else str(status)
    if value == "exact":
        return Confidence.EXACT
    if value in _EQUIVALENT_VALUES:
        return Confidence.EQUIVALENT
    if value in _APPROXIMATE_VALUES:
        return Confidence.APPROXIMATE
    return Confidence.UNSUPPORTED


def summarize_confidence(report: TranslationReport) -> dict[Confidence, int]:
    """Count outcomes in the four public classes."""
    counter: Counter[Confidence] = Counter()
    for outcome in report.outcomes:
        counter[confidence_for(outcome.status)] += 1
    return {item: counter.get(item, 0) for item in Confidence}
