"""Human-readable translation reports.

The report is text. It is not a second code generator and it does not hide
unsupported operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nodebridge.compiler.analyzer import GraphAnalysis
from nodebridge.ir.graph import NodeTree
from nodebridge.ir.semantic import SemanticGraph
from nodebridge.translation.confidence import Confidence, TranslationRecord


@dataclass
class Diagnostic:
    """One finding that should survive into the report."""

    severity: str
    message: str
    operation_id: str = ""
    node_id: str = ""


@dataclass
class Report:
    """Counts and the text a user can copy beside the generated script."""

    source_label: str
    target_label: str
    node_count: int
    operation_count: int
    counts: dict[str, int] = field(default_factory=dict)
    text: str = ""
    diagnostics: list[Diagnostic] = field(default_factory=list)


_TARGET_LABELS = {
    "houdini": "Houdini",
    "unreal": "Unreal Engine 5",
}


def build_report(
    tree: NodeTree,
    analysis: GraphAnalysis,
    semantic: SemanticGraph,
    records: list[TranslationRecord],
    *,
    target: str,
    script_issues: list[str] | None = None,
) -> Report:
    """Assemble the translation report for one compile."""

    counts = {item.value: 0 for item in Confidence}
    for record in records:
        counts[record.confidence.value] = counts.get(record.confidence.value, 0) + 1
    diagnostics = _diagnostics(analysis, records, script_issues or [])
    system = _system_label(tree.system.value)
    source_label = f"{system} / {tree.name}"
    target_label = _TARGET_LABELS.get(target, target)
    lines = [
        "NodeBridge translation report",
        "",
        f"Source:",
        source_label,
        "",
        f"Target:",
        target_label,
        "",
        f"{len(tree.nodes)} source nodes",
        f"{len(records)} semantic operations",
        "",
        f"EXACT: {counts[Confidence.EXACT.value]}",
        f"EQUIVALENT: {counts[Confidence.EQUIVALENT.value]}",
        f"APPROXIMATE: {counts[Confidence.APPROXIMATE.value]}",
        f"UNSUPPORTED: {counts[Confidence.UNSUPPORTED.value]}",
        "",
    ]
    if analysis.dead_nodes:
        lines.append("Dead nodes (not on a path to an output):")
        lines.extend(f"  {node_id}" for node_id in analysis.dead_nodes)
        lines.append("")
    if analysis.cycles:
        lines.append("Cycles:")
        for cycle in analysis.cycles:
            lines.append("  " + " -> ".join(cycle))
        lines.append("")
    if analysis.muted_nodes:
        lines.append("Muted nodes are treated as wires and are not operations:")
        lines.extend(f"  {node_id}" for node_id in analysis.muted_nodes)
        lines.append("")
    unsupported = [record for record in records if record.confidence is Confidence.UNSUPPORTED]
    if unsupported:
        lines.append("Unsupported:")
        for record in unsupported:
            source = ", ".join(record.source_types) or record.operation
            lines.append(source if source == record.operation else f"{source} ({record.operation_name})")
            lines.append("Reason:")
            lines.append(record.classification.explanation)
            if record.classification.fallback:
                lines.append(f"Fallback: {record.classification.fallback}")
            lines.append("")
    approximate = [record for record in records if record.confidence is Confidence.APPROXIMATE]
    if approximate:
        lines.append("Approximation:")
        lines.extend(_record_notes(approximate))
    limited = [
        record
        for record in records
        if record.confidence is not Confidence.APPROXIMATE and record.classification.limitations
    ]
    if limited:
        lines.append("Limitations:")
        lines.extend(_record_notes(limited))
    if semantic.metadata.get("rewrites"):
        lines.append("Rewrite rules considered: " + ", ".join(semantic.metadata["rewrites"]))
        lines.append("")
    if script_issues:
        lines.append("Script checks:")
        lines.extend(f"  {issue}" for issue in script_issues)
        lines.append("")
    lines.append(
        "Exact means the target should follow the source closely. "
        "Equivalent preserves the procedural intention and may differ in samples or topology. "
        "Approximate is a similar result, not the full source behavior. "
        "NodeBridge does not claim vertex-identical or pixel-identical output unless a translation is exact and this report lists no numerical limitation."
    )
    return Report(
        source_label=source_label,
        target_label=target_label,
        node_count=len(tree.nodes),
        operation_count=len(records),
        counts=counts,
        text="\n".join(lines).rstrip() + "\n",
        diagnostics=diagnostics,
    )


def _record_notes(records: list[TranslationRecord]) -> list[str]:
    lines: list[str] = []
    for record in records:
        lines.append(f"{record.operation_name} ({record.operation})")
        lines.append(record.classification.explanation)
        for limitation in record.classification.limitations:
            lines.append(limitation)
        lines.append("")
    return lines


def _diagnostics(analysis: GraphAnalysis, records: list[TranslationRecord], script_issues: list[str]) -> list[Diagnostic]:
    items = [Diagnostic("error", message) for message in analysis.errors]
    items.extend(Diagnostic("warning", f"Dead node {node_id}.", node_id=node_id) for node_id in analysis.dead_nodes)
    for record in records:
        if record.confidence is Confidence.UNSUPPORTED:
            items.append(Diagnostic("error", record.classification.explanation, operation_id=record.operation_id))
        elif record.confidence is Confidence.APPROXIMATE:
            items.append(Diagnostic("warning", record.classification.explanation, operation_id=record.operation_id))
        elif not record.classification.emitted:
            items.append(
                Diagnostic(
                    "warning",
                    record.classification.fallback or "Omitted by translation strictness.",
                    operation_id=record.operation_id,
                )
            )
    items.extend(Diagnostic("error", issue) for issue in script_issues)
    return items


def _system_label(system: str) -> str:
    return {
        "geometry_nodes": "Geometry Nodes",
        "shader": "Shader",
        "compositor": "Compositor",
    }.get(system, system)
