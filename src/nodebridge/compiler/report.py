"""Human-readable translation report."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..translation.confidence import Classification, Confidence
from .diagnostics import Diagnostic, Severity

EQUIVALENCE_NOTE = (
    "NodeBridge reproduces procedural intent. Unless an operation is EXACT, expect a semantically "
    "equivalent system, not vertex- or pixel-identical output."
)


@dataclass
class ReportEntry:
    graph: str
    op_id: str
    kind: str
    name: str
    source_types: list[str]
    classification: Classification
    blocked: bool = False
    suggestion: str = ""

    def as_dict(self) -> dict:
        data = {
            "graph": self.graph,
            "op": self.op_id,
            "kind": self.kind,
            "name": self.name,
            "source_types": self.source_types,
            **self.classification.as_dict(),
        }
        if self.blocked:
            data["blocked_by_strictness"] = True
        if self.suggestion:
            data["fallback_suggestion"] = self.suggestion
        return data


@dataclass
class TranslationReport:
    source_kind: str
    source_name: str
    source_application: str
    target: str
    target_label: str
    node_count: int
    entries: list[ReportEntry] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    strictness: str = ""

    @property
    def operation_count(self) -> int:
        return len(self.entries)

    def count(self, confidence: Confidence) -> int:
        return sum(1 for e in self.entries if e.classification.confidence == confidence)

    @property
    def counts(self) -> dict[str, int]:
        return {c.value: self.count(c) for c in Confidence}

    @property
    def blocked(self) -> list[ReportEntry]:
        return [e for e in self.entries if e.blocked]

    def warnings(self) -> list[str]:
        """Short warnings for UI lists: name / backend / classification / reason."""
        result = []
        for entry in self.entries:
            c = entry.classification
            if c.confidence in (Confidence.EXACT,):
                continue
            reason = c.limitations[0] if c.limitations else c.explanation
            result.append(f"{entry.name} | {c.confidence.label} | {reason}")
        for d in self.diagnostics:
            if d.severity in (Severity.WARNING, Severity.ERROR) and not d.code.startswith("lift.unsupported"):
                result.append(f"{d.severity.value.title()} | {d.message}")
        return result

    def as_dict(self) -> dict:
        return {
            "source": {"kind": self.source_kind, "name": self.source_name, "application": self.source_application},
            "target": {"id": self.target, "label": self.target_label},
            "source_nodes": self.node_count,
            "operations": self.operation_count,
            "counts": self.counts,
            "strictness": self.strictness,
            "entries": [e.as_dict() for e in self.entries],
            "diagnostics": [d.as_dict() for d in self.diagnostics],
        }

    def to_text(self) -> str:
        lines = ["NodeBridge Translation Report", "=============================", ""]
        lines.append("Source:")
        lines.append(f"    {self.source_kind} / {self.source_name}" + (f"  ({self.source_application})" if self.source_application else ""))
        lines.append("Target:")
        lines.append(f"    {self.target_label}")
        lines.append("")
        lines.append(f"{self.node_count} source nodes")
        lines.append(f"{self.operation_count} semantic operations")
        lines.append("")
        for confidence in Confidence:
            lines.append(f"{confidence.symbol} {confidence.value + ':':<13} {self.count(confidence)}")
        if self.blocked:
            lines.append(f"  Blocked by strictness ({self.strictness}): {len(self.blocked)}")
        lines.append("")
        lines.append("Operations:")
        width = max((len(e.name) for e in self.entries), default=10)
        for entry in self.entries:
            c = entry.classification
            flag = "  [blocked]" if entry.blocked else ""
            lines.append(f"  {c.confidence.symbol} {c.confidence.value:<11} {entry.name:<{width}}  {entry.kind:<20} -> {c.implementation}{flag}")
        for confidence, title in ((Confidence.UNSUPPORTED, "Unsupported"), (Confidence.APPROXIMATE, "Approximations"), (Confidence.EQUIVALENT, "Equivalent (intent preserved, details differ)")):
            group = [e for e in self.entries if e.classification.confidence == confidence]
            if not group:
                continue
            lines.append("")
            lines.append(f"{title}:")
            for entry in group:
                c = entry.classification
                lines.append(f"  {entry.name} ({', '.join(entry.source_types) or entry.kind})")
                if c.explanation:
                    lines.append(f"    Reason: {c.explanation}")
                for limitation in c.limitations:
                    lines.append(f"    - {limitation}")
                if c.fallback and confidence != Confidence.EQUIVALENT:
                    lines.append(f"    Fallback: {c.fallback}")
                if entry.suggestion:
                    lines.append(f"    Suggestion (not applied): {entry.suggestion}")
        notes = [d for d in self.diagnostics if d.severity != Severity.INFO]
        infos = [d for d in self.diagnostics if d.severity == Severity.INFO and d.code in ("rewrite.applied", "subgraph.inlined", "graph.dead_node", "graph.muted_node")]
        if notes:
            lines.append("")
            lines.append("Warnings:")
            lines.extend(f"  - {d.message}" for d in notes)
        if infos:
            lines.append("")
            lines.append("Compiler notes:")
            lines.extend(f"  - {d.message}" for d in infos)
        lines.append("")
        lines.append(EQUIVALENCE_NOTE)
        return "\n".join(lines) + "\n"
