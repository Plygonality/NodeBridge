"""Structured diagnostics and translation reports.

Translation quality is never silent. Every noteworthy finding is a
:class:`Diagnostic`. Aggregate results become a :class:`TranslationReport`.

Fidelity classifications describe *how* an operation was (or would be)
realized. They are not a compatibility percentage.
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
    """How faithfully an operation can be (or was) translated.

    ``EXACT``
        The target implementation preserves the relevant source semantics.
    ``LOWERED``
        Equivalent behavior is reconstructed using multiple target-native
        operations.
    ``APPROXIMATE``
        The target cannot exactly reproduce the behavior, but a documented
        approximation exists.
    ``CUSTOM_CODE``
        Native graph nodes alone are insufficient; host-native code such as
        VEX, Python, or expressions is generated.
    ``BAKED``
        Some procedural behavior cannot survive translation and must be
        evaluated or frozen.
    ``UNSUPPORTED``
        No defensible translation exists.

    Milestone 1 aliases: ``EQUIVALENT`` → ``LOWERED``, ``APPROXIMATED`` /
    ``PARTIAL`` → ``APPROXIMATE``.
    """

    EXACT = "exact"
    LOWERED = "lowered"
    APPROXIMATE = "approximate"
    CUSTOM_CODE = "custom_code"
    BAKED = "baked"
    UNSUPPORTED = "unsupported"
    # Milestone 1 compatibility aliases (same values as the canonical members).
    EQUIVALENT = "lowered"
    APPROXIMATED = "approximate"
    PARTIAL = "approximate"


PRIMARY_STATUSES: tuple[TranslationStatus, ...] = (
    TranslationStatus.EXACT,
    TranslationStatus.LOWERED,
    TranslationStatus.APPROXIMATE,
    TranslationStatus.CUSTOM_CODE,
    TranslationStatus.BAKED,
    TranslationStatus.UNSUPPORTED,
)


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
    recipe: str = ""
    generated_code_kind: str = ""


@dataclass
class GeneratedCode:
    """Host-native code emitted for one operation. Never executed by IR load."""

    kind: str
    language: str
    source: str
    node_id: str = ""
    operation: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "kind": self.kind,
            "language": self.language,
            "source": self.source,
        }
        if self.node_id:
            payload["node_id"] = self.node_id
        if self.operation:
            payload["operation"] = self.operation
        return payload


@dataclass
class TranslationReport:
    """Compatibility / translation summary for one graph and one target."""

    source_application: str
    source_system: str
    target: str
    nodes_analysed: int = 0
    outcomes: list[OperationOutcome] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    generated_code: list[GeneratedCode] = field(default_factory=list)
    target_system: str = ""

    def counts(self) -> dict[TranslationStatus, int]:
        """Number of outcomes in each canonical :class:`TranslationStatus`."""
        counter: Counter[str] = Counter(outcome.status.value for outcome in self.outcomes)
        return {status: counter.get(status.value, 0) for status in PRIMARY_STATUSES}

    def add_outcome(self, outcome: OperationOutcome) -> None:
        self.outcomes.append(outcome)
        self.nodes_analysed = len(self.outcomes)

    def add_diagnostic(self, diagnostic: Diagnostic) -> None:
        self.diagnostics.append(diagnostic)

    def add_generated_code(self, code: GeneratedCode) -> None:
        self.generated_code.append(code)

    def errors(self) -> list[Diagnostic]:
        return [
            item
            for item in self.diagnostics
            if item.severity is DiagnosticSeverity.ERROR
        ]

    def format_text(self) -> str:
        """Human-readable report. No invented compatibility percentage."""
        counts = self.counts()
        source_line = f"{self.source_application} {self.source_system}".strip()
        target_line = self.target
        if self.target_system:
            target_line = f"{self.target} {self.target_system}".strip()
        lines = [
            "NodeBridge Translation Report",
            "=============================",
            "Translation:",
            f"    {source_line}",
            f"    → {target_line}",
            "",
            "Operations:",
            f"    {self.nodes_analysed} total",
            f"    {counts[TranslationStatus.EXACT]} EXACT",
            f"    {counts[TranslationStatus.LOWERED]} LOWERED",
            f"    {counts[TranslationStatus.APPROXIMATE]} APPROXIMATE",
            f"    {counts[TranslationStatus.CUSTOM_CODE]} CUSTOM_CODE",
            f"    {counts[TranslationStatus.BAKED]} BAKED",
            f"    {counts[TranslationStatus.UNSUPPORTED]} UNSUPPORTED",
        ]

        def _section(title: str, statuses: tuple[TranslationStatus, ...]) -> None:
            matching = [
                outcome
                for outcome in self.outcomes
                if outcome.status in statuses
            ]
            if not matching:
                return
            lines.append("")
            lines.append(f"{title}:")
            for outcome in matching:
                label = outcome.source_type or outcome.operation
                suffix = f" — {outcome.note}" if outcome.note else ""
                lines.append(f"- {label}{suffix}")

        warnings = [
            item
            for item in self.diagnostics
            if item.severity is DiagnosticSeverity.WARNING
        ]
        if warnings:
            lines.append("")
            lines.append("Warnings:")
            for item in warnings:
                lines.append(f"- {item.message}")

        _section("Unsupported", (TranslationStatus.UNSUPPORTED,))
        _section(
            "Approximations",
            (TranslationStatus.APPROXIMATE, TranslationStatus.APPROXIMATED),
        )
        _section("Lowered", (TranslationStatus.LOWERED,))
        _section("Custom code", (TranslationStatus.CUSTOM_CODE,))
        _section("Baked", (TranslationStatus.BAKED,))

        if self.generated_code:
            lines.append("")
            lines.append("Generated host code:")
            for item in self.generated_code:
                origin = item.node_id or item.operation or item.kind
                lines.append(f"- {item.language} ({origin})")
                for code_line in item.source.strip().splitlines() or [item.source]:
                    lines.append(f"    {code_line}")

        return "\n".join(lines) + "\n"

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready representation. No compatibility percentage field."""
        counts = self.counts()
        return {
            "source": {
                "application": self.source_application,
                "system": self.source_system,
            },
            "target": self.target,
            "target_system": self.target_system,
            "nodes_analysed": self.nodes_analysed,
            "counts": {status.value: counts[status] for status in PRIMARY_STATUSES},
            "outcomes": [
                {
                    "node_id": outcome.node_id,
                    "operation": outcome.operation,
                    "status": outcome.status.value,
                    "note": outcome.note,
                    "source_type": outcome.source_type,
                    "recipe": outcome.recipe,
                    "generated_code_kind": outcome.generated_code_kind,
                }
                for outcome in self.outcomes
            ],
            "diagnostics": [item.as_dict() for item in self.diagnostics],
            "generated_code": [item.as_dict() for item in self.generated_code],
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
