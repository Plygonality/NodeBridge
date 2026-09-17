"""Translation planning.

Before generating a target graph, NodeBridge determines how each semantic
operation will be realized given the target host's capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nodebridge.core.capabilities import CapabilitySet
from nodebridge.core.diagnostics import (
    Diagnostic,
    DiagnosticSeverity,
    OperationOutcome,
    TranslationReport,
    TranslationStatus,
)
from nodebridge.core.graph import IRGraph
from nodebridge.core.operations import DEFAULT_OPERATION_REGISTRY, OperationRegistry
from nodebridge.hosts.contract import HostPlugin, Implementation
from nodebridge.hosts.registry import get_host


@dataclass
class PlannedOperation:
    """How one IR node will be realized on the target host."""

    node_id: str
    operation: str
    fidelity: TranslationStatus
    strategy: str
    recipe: str = ""
    note: str = ""
    generated_code_kind: str = ""
    available: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "operation": self.operation,
            "fidelity": self.fidelity.value,
            "strategy": self.strategy,
            "recipe": self.recipe,
            "note": self.note,
            "generated_code_kind": self.generated_code_kind,
            "available": self.available,
        }


@dataclass
class TranslationPlan:
    """Deterministic plan for one IR graph toward one host."""

    source_host: str
    target_host: str
    target_system: str
    operations: list[PlannedOperation] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    missing_capabilities: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_host": self.source_host,
            "target_host": self.target_host,
            "target_system": self.target_system,
            "operations": [item.as_dict() for item in self.operations],
            "diagnostics": [item.as_dict() for item in self.diagnostics],
            "missing_capabilities": list(self.missing_capabilities),
        }

    def to_report(self, graph: IRGraph) -> TranslationReport:
        report = TranslationReport(
            source_application=self.source_host or graph.provenance.application or "unknown",
            source_system=graph.provenance.graph_system or graph.system.value,
            target=self.target_host,
            target_system=self.target_system,
        )
        for item in self.operations:
            node = graph.nodes.get(item.node_id)
            source_type = node.metadata.provenance.original_type if node else ""
            report.add_outcome(
                OperationOutcome(
                    node_id=item.node_id,
                    operation=item.operation,
                    status=item.fidelity,
                    note=item.note,
                    source_type=source_type,
                    recipe=item.recipe,
                    generated_code_kind=item.generated_code_kind,
                )
            )
        for diagnostic in self.diagnostics:
            report.add_diagnostic(diagnostic)
        return report


def plan_translation(
    graph: IRGraph,
    target: str | HostPlugin,
    *,
    operations: OperationRegistry | None = None,
) -> TranslationPlan:
    """Construct a translation plan without generating a native graph."""
    host = target if not isinstance(target, str) else get_host(target)
    catalog = operations or DEFAULT_OPERATION_REGISTRY
    plan = TranslationPlan(
        source_host=graph.provenance.application or "unknown",
        target_host=host.id,
        target_system=host.graph_systems[0] if host.graph_systems else "",
    )
    required = CapabilitySet()
    try:
        order = graph.topological_order()
    except ValueError:
        order = sorted(graph.nodes)
    for node_id in order:
        node = graph.nodes[node_id]
        spec = catalog.get(node.operation)
        if spec is not None:
            for capability in spec.required_capabilities:
                required.add(capability)
        implementation: Implementation = host.implementation_for(node.operation)
        strategy = _strategy(implementation)
        planned = PlannedOperation(
            node_id=node.id,
            operation=node.operation,
            fidelity=implementation.fidelity,
            strategy=strategy,
            recipe=implementation.recipe,
            note=implementation.note,
            generated_code_kind=implementation.code_kind,
            available=implementation.available,
        )
        plan.operations.append(planned)
        if implementation.fidelity is not TranslationStatus.EXACT:
            severity = (
                DiagnosticSeverity.ERROR
                if implementation.fidelity is TranslationStatus.UNSUPPORTED
                else DiagnosticSeverity.WARNING
            )
            plan.diagnostics.append(
                Diagnostic(
                    code="NB-P001",
                    message=(
                        f"{node.operation} → {host.id}: {implementation.fidelity.value}"
                        + (f" ({implementation.note})" if implementation.note else "")
                    ),
                    severity=severity,
                    node_id=node.id,
                    operation=node.operation,
                    details={"strategy": strategy, "recipe": implementation.recipe},
                )
            )
        if spec is None:
            plan.diagnostics.append(
                Diagnostic(
                    code="NB-W002",
                    message=f"Unknown operation {node.operation!r}",
                    severity=DiagnosticSeverity.WARNING,
                    node_id=node.id,
                    operation=node.operation,
                )
            )
    missing = host.capabilities.missing(required) if hasattr(host.capabilities, "missing") else []
    plan.missing_capabilities = [item.value for item in missing]
    for capability in plan.missing_capabilities:
        plan.diagnostics.append(
            Diagnostic(
                code="NB-P002",
                message=f"Target {host.id} does not declare capability {capability!r}",
                severity=DiagnosticSeverity.WARNING,
                details={"capability": capability},
            )
        )
    for child in graph.graphs.values():
        child_plan = plan_translation(child, host, operations=catalog)
        plan.operations.extend(child_plan.operations)
        plan.diagnostics.extend(child_plan.diagnostics)
    return plan


def _strategy(implementation: Implementation) -> str:
    if implementation.fidelity is TranslationStatus.EXACT:
        return "exact"
    if implementation.fidelity is TranslationStatus.LOWERED:
        return "lower"
    if implementation.fidelity is TranslationStatus.APPROXIMATE:
        return "approximate"
    if implementation.fidelity is TranslationStatus.CUSTOM_CODE:
        return "custom_code"
    if implementation.fidelity is TranslationStatus.BAKED:
        return "bake"
    return "unsupported"
