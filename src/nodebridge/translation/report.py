"""Human-readable translation report used by the add-on and the CLI."""

from __future__ import annotations

from nodebridge.core.diagnostics import TranslationReport
from nodebridge.translation.confidence import Confidence, confidence_for, summarize_confidence

_STOCHASTIC = {
    "points.distribute",
    "random.float",
    "random.vector",
    "random.integer",
    "procedural.noise",
    "procedural.voronoi",
    "selection.spatial_noise",
}


def public_confidence(status: object, operation: str = "") -> Confidence:
    """Public class, with stochastic operations never advertised as exact."""
    confidence = confidence_for(status)  # type: ignore[arg-type]
    if operation in _STOCHASTIC and confidence is Confidence.EXACT:
        return Confidence.EQUIVALENT
    return confidence


def format_translation_report(
    report: TranslationReport,
    *,
    source_nodes: int | None = None,
    source_name: str = "",
) -> str:
    """Report in the four public confidence classes."""
    counts = {item: 0 for item in Confidence}
    for outcome in report.outcomes:
        counts[public_confidence(outcome.status, outcome.operation)] += 1
    source = source_name or f"{report.source_application} {report.source_system}".strip()
    target = report.target
    if report.target_system:
        target = f"{report.target} ({report.target_system})"
    lines = [
        "NodeBridge Translation Report",
        "=============================",
        f"Source: {source}",
        f"Target: {target}",
        "",
        f"{source_nodes if source_nodes is not None else report.nodes_analysed} source nodes",
        f"{report.nodes_analysed} semantic operations",
        "",
        f"EXACT: {counts[Confidence.EXACT]}",
        f"EQUIVALENT: {counts[Confidence.EQUIVALENT]}",
        f"APPROXIMATE: {counts[Confidence.APPROXIMATE]}",
        f"UNSUPPORTED: {counts[Confidence.UNSUPPORTED]}",
        "",
        "The expected result is a semantically equivalent procedural system.",
        "It is not a promise of identical vertices, samples, or pixels.",
    ]
    unsupported = [
        outcome
        for outcome in report.outcomes
        if public_confidence(outcome.status, outcome.operation) is Confidence.UNSUPPORTED
    ]
    approximate = [
        outcome
        for outcome in report.outcomes
        if public_confidence(outcome.status, outcome.operation) is Confidence.APPROXIMATE
    ]
    equivalent = [
        outcome
        for outcome in report.outcomes
        if public_confidence(outcome.status, outcome.operation) is Confidence.EQUIVALENT
    ]
    if unsupported:
        lines.extend(["", "Unsupported:"])
        for outcome in unsupported:
            label = outcome.source_type or outcome.operation
            lines.append(f"    {label}")
            lines.append(f"    Reason: {outcome.note or 'No NodeBridge translation is registered.'}")
    if approximate:
        lines.extend(["", "Approximation:"])
        for outcome in approximate:
            lines.append(f"    {outcome.source_type or outcome.operation}")
            if outcome.note:
                lines.append(f"    {outcome.note}")
    if equivalent:
        lines.extend(["", "Equivalent:"])
        for outcome in equivalent:
            lines.append(f"    {outcome.source_type or outcome.operation}")
            note = outcome.note
            if outcome.operation in _STOCHASTIC and "random" not in note.lower() and "noise" not in note.lower():
                note = (note + " " if note else "") + "Target random samples may differ."
            if note:
                lines.append(f"    {note}")
    if report.diagnostics:
        lines.extend(["", "Diagnostics:"])
        for diagnostic in report.diagnostics:
            lines.append(f"    [{diagnostic.severity.value}] {diagnostic.message}")
    lines.append("")
    return "\n".join(lines)


def confidence_counts(report: TranslationReport) -> dict[str, int]:
    """String-keyed counts for UI properties."""
    summary = summarize_confidence(report)
    # Recompute with the stochastic adjustment.
    counts = {item.value: 0 for item in Confidence}
    for outcome in report.outcomes:
        counts[public_confidence(outcome.status, outcome.operation).value] += 1
    del summary
    return counts
