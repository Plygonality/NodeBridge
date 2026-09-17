"""Compatibility analysis.

When a translation registry is supplied, classify from registered handlers.
Otherwise consult the target host plugin via the compiler planner so
unregistered operations cannot silently succeed.
"""

from __future__ import annotations

from nodebridge.compiler.planning import plan_translation
from nodebridge.core.diagnostics import (
    Diagnostic,
    DiagnosticSeverity,
    OperationOutcome,
    TranslationReport,
    TranslationStatus,
)
from nodebridge.core.graph import IRGraph
from nodebridge.core.operations import DEFAULT_OPERATION_REGISTRY, OperationRegistry
from nodebridge.hosts.registry import DEFAULT_HOST_REGISTRY
from nodebridge.translators.registry import TranslationRegistry


def analyse_compatibility(
    graph: IRGraph,
    target: str,
    *,
    translations: TranslationRegistry | None = None,
    operations: OperationRegistry | None = None,
) -> TranslationReport:
    """Produce a structured compatibility report for *graph* → *target*."""
    if translations is not None:
        return _analyse_from_registry(graph, target, translations, operations)
    if DEFAULT_HOST_REGISTRY.contains(target):
        return plan_translation(graph, target, operations=operations).to_report(graph)
    return _analyse_from_registry(graph, target, translations, operations)


def _analyse_from_registry(
    graph: IRGraph,
    target: str,
    catalog: TranslationRegistry | None,
    operations: OperationRegistry | None,
) -> TranslationReport:
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
        child_report = _analyse_from_registry(child, target, catalog, ops)
        report.outcomes.extend(child_report.outcomes)
        report.diagnostics.extend(child_report.diagnostics)
        report.nodes_analysed = len(report.outcomes)
    return report
