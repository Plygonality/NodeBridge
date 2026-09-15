"""Compatibility analysis (Milestone 4).

Walk an IR graph and classify every operation against a target without
generating code. Milestone 1 exposes the report types so later work can
fill them in.
"""

from __future__ import annotations

from nodebridge.core.diagnostics import (
    OperationOutcome,
    TranslationReport,
    TranslationStatus,
)
from nodebridge.core.graph import IRGraph
from nodebridge.core.operations import DEFAULT_OPERATION_REGISTRY, OperationRegistry
from nodebridge.translators.registry import TranslationRegistry


def analyse_compatibility(
    graph: IRGraph,
    target: str,
    *,
    translations: TranslationRegistry | None = None,
    operations: OperationRegistry | None = None,
) -> TranslationReport:
    """Produce a structured compatibility report for *graph* → *target*.

    Without registered translations every known operation is marked
    ``UNSUPPORTED`` so the result cannot be mistaken for a silent success.
    """
    catalog = translations
    ops = operations or DEFAULT_OPERATION_REGISTRY
    report = TranslationReport(
        source_application=graph.provenance.application or "unknown",
        source_system=graph.system.value,
        target=target,
    )
    for node in graph.nodes.values():
        handler = catalog.lookup(node.operation, target) if catalog else None
        if handler is None:
            status = TranslationStatus.UNSUPPORTED
            note = "No translation registered"
        else:
            status = handler.status
            note = handler.kind
        source_type = node.metadata.provenance.original_type
        report.add_outcome(
            OperationOutcome(
                node_id=node.id,
                operation=node.operation,
                status=status,
                note=note,
                source_type=source_type,
            )
        )
        if not ops.contains(node.operation):
            from nodebridge.core.diagnostics import Diagnostic, DiagnosticSeverity

            report.add_diagnostic(
                Diagnostic(
                    code="NB-W002",
                    message=f"Unknown operation {node.operation!r}",
                    severity=DiagnosticSeverity.WARNING,
                    node_id=node.id,
                    operation=node.operation,
                )
            )
    for child in graph.graphs.values():
        child_report = analyse_compatibility(
            child, target, translations=catalog, operations=ops
        )
        report.outcomes.extend(child_report.outcomes)
        report.diagnostics.extend(child_report.diagnostics)
        report.nodes_analysed = len(report.outcomes)
    return report
