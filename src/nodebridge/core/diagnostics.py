"""Structured diagnostics and translation reports.

Translation quality is never silent. Every noteworthy finding is a
:class:`Diagnostic`. Aggregate results become a :class:`TranslationReport`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable


class DiagnosticSeverity(str, Enum):
    """How serious a diagnostic is."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class TranslationStatus(str, Enum):
    """How faithfully an operation can be (or was) translated."""

    EXACT = "exact"
    EQUIVALENT = "equivalent"
    APPROXIMATED = "approximated"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


@dataclass
class Diagnostic:
    """One structured finding attached to a graph, node, or connection."""

    code: str
    message: str
    severity: DiagnosticSeverity = DiagnosticSeverity.WARNING
    node_id: str | None = None
    connection_id: str | None = None
    socket_id: str | None = None
    operation: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready representation."""
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
        }
        if self.node_id is not None:
            payload["node_id"] = self.node_id
        if self.connection_id is not None:
            payload["connection_id"] = self.connection_id
        if self.socket_id is not None:
            payload["socket_id"] = self.socket_id
        if self.operation is not None:
            payload["operation"] = self.operation
        if self.details:
            payload["details"] = dict(self.details)
        return payload


@dataclass
class OperationOutcome:
    """Per-node translation classification."""

    node_id: str
    operation: str
    status: TranslationStatus
    note: str = ""
    source_type: str = ""


@dataclass
class TranslationReport:
    """Compatibility / translation summary for one graph and one target."""

    source_application: str
    source_system: str
    target: str
    nodes_analysed: int = 0
    outcomes: list[OperationOutcome] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def counts(self) -> dict[TranslationStatus, int]:
        """Number of outcomes in each :class:`TranslationStatus`."""
        counter: Counter[TranslationStatus] = Counter(
            outcome.status for outcome in self.outcomes
        )
        return {status: counter.get(status, 0) for status in TranslationStatus}

    def add_outcome(self, outcome: OperationOutcome) -> None:
        self.outcomes.append(outcome)
        self.nodes_analysed = len(self.outcomes)

    def add_diagnostic(self, diagnostic: Diagnostic) -> None:
        self.diagnostics.append(diagnostic)

    def errors(self) -> list[Diagnostic]:
        return [
            item
            for item in self.diagnostics
            if item.severity is DiagnosticSeverity.ERROR
        ]

    def format_text(self) -> str:
        """Human-readable report matching the project brief."""
        counts = self.counts()
        lines = [
            "NodeBridge Translation Report",
            "=============================",
            "Source:",
            f"{self.source_application} {self.source_system}".strip(),
            "Target:",
            self.target,
            f"Nodes analysed: {self.nodes_analysed}",
            f"Exact:        {counts[TranslationStatus.EXACT]}",
            f"Equivalent:   {counts[TranslationStatus.EQUIVALENT]}",
            f"Approximated: {counts[TranslationStatus.APPROXIMATED]}",
            f"Partial:      {counts[TranslationStatus.PARTIAL]}",
            f"Unsupported:  {counts[TranslationStatus.UNSUPPORTED]}",
        ]
        unsupported = [
            outcome
            for outcome in self.outcomes
            if outcome.status is TranslationStatus.UNSUPPORTED
        ]
        if unsupported:
            lines.append("Unsupported:")
            for outcome in unsupported:
                label = outcome.source_type or outcome.operation
                suffix = f" — {outcome.note}" if outcome.note else ""
                lines.append(f"- {label}{suffix}")
        approximated = [
            outcome
            for outcome in self.outcomes
            if outcome.status is TranslationStatus.APPROXIMATED
        ]
        if approximated:
            lines.append("Approximation:")
            for outcome in approximated:
                label = outcome.source_type or outcome.operation
                suffix = f" — {outcome.note}" if outcome.note else ""
                lines.append(f"- {label}{suffix}")
        warnings = [
            item
            for item in self.diagnostics
            if item.severity is DiagnosticSeverity.WARNING
        ]
        if warnings:
            lines.append("Warnings:")
            for item in warnings:
                lines.append(f"- {item.message}")
        return "\n".join(lines) + "\n"

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready representation."""
        counts = self.counts()
        return {
            "source": {
                "application": self.source_application,
                "system": self.source_system,
            },
            "target": self.target,
            "nodes_analysed": self.nodes_analysed,
            "counts": {status.value: counts[status] for status in TranslationStatus},
            "outcomes": [
                {
                    "node_id": outcome.node_id,
                    "operation": outcome.operation,
                    "status": outcome.status.value,
                    "note": outcome.note,
                    "source_type": outcome.source_type,
                }
                for outcome in self.outcomes
            ],
            "diagnostics": [item.as_dict() for item in self.diagnostics],
        }


def collect_diagnostics(
    diagnostics: Iterable[Diagnostic],
    *,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Return diagnostics, optionally filtered by *severity*."""
    if severity is None:
        return list(diagnostics)
    return [item for item in diagnostics if item.severity is severity]
