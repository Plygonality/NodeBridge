"""Assemble a native graph from per-operation lowering fragments.

Used by every host backend so wiring and provenance stay consistent.
"""

from __future__ import annotations

from nodebridge.core.diagnostics import (
    Diagnostic,
    DiagnosticSeverity,
    GeneratedCode,
    OperationOutcome,
    TranslationReport,
    TranslationStatus,
)
from nodebridge.core.graph import IRGraph
from nodebridge.core.metadata import TranslationEvent
from nodebridge.hosts.contract import HostBackend, LoweringFragment
from nodebridge.hosts.native import NativeGraph, NativeLink, NativeSocket
from nodebridge.hosts.recipes import unsupported_fragment


def assemble_native(
    graph: IRGraph,
    backend: HostBackend,
    *,
    host_id: str,
    system: str,
) -> tuple[NativeGraph, TranslationReport]:
    """Lower every IR node and reconnect fragments using IR data flow."""
    report = TranslationReport(
        source_application=graph.provenance.application or "unknown",
        source_system=graph.provenance.graph_system or graph.system.value,
        target=host_id,
        target_system=system,
    )
    native = NativeGraph(host=host_id, system=system, name=graph.name)
    fragments: dict[str, LoweringFragment] = {}

    try:
        order = graph.topological_order()
    except ValueError:
        order = sorted(graph.nodes)

    for node_id in order:
        node = graph.nodes[node_id]
        fragment = backend.lower_node(node)
        if fragment.fidelity is TranslationStatus.UNSUPPORTED and not fragment.nodes:
            fragment = unsupported_fragment(node)
        fragments[node_id] = fragment
        native.nodes.extend(fragment.nodes)
        native.links.extend(fragment.links)
        source_type = node.metadata.provenance.original_type
        report.add_outcome(
            OperationOutcome(
                node_id=node.id,
                operation=node.operation,
                status=fragment.fidelity,
                note=fragment.note,
                source_type=source_type,
                recipe=fragment.recipe,
                generated_code_kind=fragment.code_kind,
            )
        )
        if fragment.fidelity is not TranslationStatus.EXACT:
            severity = (
                DiagnosticSeverity.ERROR
                if fragment.fidelity is TranslationStatus.UNSUPPORTED
                else DiagnosticSeverity.WARNING
            )
            report.add_diagnostic(
                Diagnostic(
                    code=_code_for(fragment.fidelity),
                    message=_message_for(node.operation, fragment),
                    severity=severity,
                    node_id=node.id,
                    operation=node.operation,
                    details={"fidelity": fragment.fidelity.value, "recipe": fragment.recipe},
                )
            )
        if fragment.code:
            report.add_generated_code(
                GeneratedCode(
                    kind=fragment.code_kind or "code",
                    language=fragment.code_kind or "text",
                    source=fragment.code,
                    node_id=node.id,
                    operation=node.operation,
                )
            )
        node.metadata.history.append(
            TranslationEvent(
                stage="lower",
                host=host_id,
                fidelity=fragment.fidelity.value,
                note=fragment.note,
                native_type=fragment.recipe,
            )
        )

    for connection in graph.connections:
        source_fragment = fragments.get(connection.source_node)
        target_fragment = fragments.get(connection.target_node)
        if source_fragment is None or target_fragment is None:
            continue
        source_node = graph.nodes[connection.source_node]
        target_node = graph.nodes[connection.target_node]
        try:
            source_name = source_node.socket(connection.source_socket).name
        except KeyError:
            continue
        try:
            target_name = target_node.socket(connection.target_socket).name
        except KeyError:
            continue
        source_port = _lookup_port(source_fragment, source_name, outputs=True)
        target_port = _lookup_port(target_fragment, target_name, outputs=False)
        if source_port is None or target_port is None:
            continue
        native.links.append(
            NativeLink(
                source_node=source_port[0],
                source_socket=source_port[1],
                target_node=target_port[0],
                target_socket=target_port[1],
            )
        )

    for socket in graph.interface.inputs.values():
        native.interface_inputs.append(
            NativeSocket(name=socket.name, data_type=socket.data_type.name, default=socket.default)
        )
    for socket in graph.interface.outputs.values():
        native.interface_outputs.append(
            NativeSocket(name=socket.name, data_type=socket.data_type.name)
        )
    native.metadata = {
        "ir_graph_id": graph.id,
        "source_application": graph.provenance.application,
        "source_system": graph.provenance.graph_system,
    }
    return native, report


def _lookup_port(
    fragment: LoweringFragment, name: str, *, outputs: bool
) -> tuple[str, str] | None:
    table = fragment.outputs if outputs else fragment.inputs
    if name in table:
        return table[name]
    lowered = name.lower()
    for key, value in table.items():
        if key.lower() == lowered:
            return value
    if len(table) == 1:
        return next(iter(table.values()))
    if fragment.nodes:
        node = fragment.nodes[-1] if outputs else fragment.nodes[0]
        sockets = node.outputs if outputs else node.inputs
        if sockets:
            return node.id, sockets[0].name
        return node.id, name
    return None


def _code_for(status: TranslationStatus) -> str:
    return {
        TranslationStatus.LOWERED: "NB-T001",
        TranslationStatus.APPROXIMATE: "NB-T002",
        TranslationStatus.CUSTOM_CODE: "NB-T003",
        TranslationStatus.BAKED: "NB-T004",
        TranslationStatus.UNSUPPORTED: "NB-T005",
    }.get(status, "NB-T000")


def _message_for(operation: str, fragment: LoweringFragment) -> str:
    labels = {
        TranslationStatus.LOWERED: "lowered into a native fragment",
        TranslationStatus.APPROXIMATE: "approximated",
        TranslationStatus.CUSTOM_CODE: "requires generated host code",
        TranslationStatus.BAKED: "cannot remain procedural and would be baked",
        TranslationStatus.UNSUPPORTED: "has no defensible translation",
    }
    label = labels.get(fragment.fidelity, fragment.fidelity.value)
    note = f" ({fragment.note})" if fragment.note else ""
    return f"Operation {operation!r} {label}{note}"
