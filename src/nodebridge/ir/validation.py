"""Structural and semantic validation of IR graphs.

Validation produces :class:`Diagnostic` objects. Callers may collect them
or raise :class:`ValidationError` when any error-severity finding exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nodebridge.core.diagnostics import Diagnostic, DiagnosticSeverity
from nodebridge.core.exceptions import ValidationError
from nodebridge.core.graph import IRGraph
from nodebridge.core.ids import is_valid_id
from nodebridge.core.node import IRNode
from nodebridge.core.operations import DEFAULT_OPERATION_REGISTRY, OperationRegistry
from nodebridge.core.socket import SocketDirection
from nodebridge.core.types import TypeCompatibility, compare_types
from nodebridge.core.values import value_matches_type


@dataclass
class ValidationResult:
    """Collected diagnostics from one validation pass."""

    diagnostics: list[Diagnostic] = field(default_factory=list)

    def add(self, diagnostic: Diagnostic) -> None:
        self.diagnostics.append(diagnostic)

    @property
    def ok(self) -> bool:
        return not any(
            item.severity is DiagnosticSeverity.ERROR for item in self.diagnostics
        )

    def errors(self) -> list[Diagnostic]:
        return [
            item
            for item in self.diagnostics
            if item.severity is DiagnosticSeverity.ERROR
        ]

    def raise_if_invalid(self) -> None:
        """Raise :class:`ValidationError` if any error diagnostics exist."""
        errors = self.errors()
        if not errors:
            return
        summary = "; ".join(item.message for item in errors[:5])
        extra = "" if len(errors) <= 5 else f" (and {len(errors) - 5} more)"
        raise ValidationError(f"IR validation failed: {summary}{extra}")


def validate_graph(
    graph: IRGraph,
    *,
    operations: OperationRegistry | None = None,
    raise_on_error: bool = False,
) -> ValidationResult:
    """Validate *graph* and every nested graph."""
    result = ValidationResult()
    registry = operations or DEFAULT_OPERATION_REGISTRY
    _validate_graph_tree(graph, result, registry, ancestors=())
    if raise_on_error:
        result.raise_if_invalid()
    return result


def _validate_graph_tree(
    graph: IRGraph,
    result: ValidationResult,
    registry: OperationRegistry,
    ancestors: tuple[str, ...],
) -> None:
    if graph.id in ancestors:
        result.add(
            Diagnostic(
                code="NB-E006",
                message=f"Nested graph cycle involving {graph.id!r}",
                severity=DiagnosticSeverity.ERROR,
                details={"cycle": list(ancestors) + [graph.id]},
            )
        )
        return
    _validate_one_graph(graph, result, registry)
    next_ancestors = ancestors + (graph.id,)
    for child in graph.graphs.values():
        _validate_graph_tree(child, result, registry, next_ancestors)


def _validate_one_graph(
    graph: IRGraph,
    result: ValidationResult,
    registry: OperationRegistry,
) -> None:
    if not is_valid_id(graph.id):
        result.add(
            Diagnostic(
                code="NB-E008",
                message=f"Invalid graph id {graph.id!r}",
                severity=DiagnosticSeverity.ERROR,
            )
        )
    node_ids = set(graph.nodes)
    connection_ids: set[str] = set()

    for node in graph.nodes.values():
        _validate_node(node, result, registry, graph)

    for connection in graph.connections:
        if connection.id in connection_ids:
            result.add(
                Diagnostic(
                    code="NB-E007",
                    message=f"Duplicate connection id {connection.id!r}",
                    severity=DiagnosticSeverity.ERROR,
                    connection_id=connection.id,
                )
            )
        connection_ids.add(connection.id)
        _validate_connection(graph, connection, node_ids, result)

    _validate_cycles(graph, result)
    _validate_nested_references(graph, result)


def _validate_node(
    node: IRNode,
    result: ValidationResult,
    registry: OperationRegistry,
    graph: IRGraph,
) -> None:
    if not node.operation:
        result.add(
            Diagnostic(
                code="NB-E004",
                message=f"Node {node.id!r} has an empty operation",
                severity=DiagnosticSeverity.ERROR,
                node_id=node.id,
            )
        )
    elif not registry.contains(node.operation):
        result.add(
            Diagnostic(
                code="NB-W002",
                message=f"Unknown operation {node.operation!r} on node {node.id!r}",
                severity=DiagnosticSeverity.WARNING,
                node_id=node.id,
                operation=node.operation,
            )
        )

    seen_socket_ids: set[str] = set()
    for socket in list(node.inputs.values()) + list(node.outputs.values()):
        if socket.id in seen_socket_ids:
            result.add(
                Diagnostic(
                    code="NB-E009",
                    message=f"Duplicate socket id {socket.id!r} on node {node.id!r}",
                    severity=DiagnosticSeverity.ERROR,
                    node_id=node.id,
                    socket_id=socket.id,
                )
            )
        seen_socket_ids.add(socket.id)
        if not value_matches_type(socket.default, socket.data_type):
            result.add(
                Diagnostic(
                    code="NB-W005",
                    message=(
                        f"Default value on {node.id}.{socket.name} "
                        f"does not match type {socket.data_type}"
                    ),
                    severity=DiagnosticSeverity.WARNING,
                    node_id=node.id,
                    socket_id=socket.id,
                )
            )

    if node.nested_graph_id and node.nested_graph_id not in graph.graphs:
        result.add(
            Diagnostic(
                code="NB-E010",
                message=(
                    f"Node {node.id!r} references missing nested graph "
                    f"{node.nested_graph_id!r}"
                ),
                severity=DiagnosticSeverity.ERROR,
                node_id=node.id,
                operation=node.operation,
            )
        )


def _validate_connection(
    graph: IRGraph,
    connection: object,
    node_ids: set[str],
    result: ValidationResult,
) -> None:
    from nodebridge.core.link import IRConnection

    assert isinstance(connection, IRConnection)
    if connection.source_node not in node_ids:
        result.add(
            Diagnostic(
                code="NB-E002",
                message=(
                    f"Connection {connection.id!r} source node "
                    f"{connection.source_node!r} does not exist"
                ),
                severity=DiagnosticSeverity.ERROR,
                connection_id=connection.id,
            )
        )
        return
    if connection.target_node not in node_ids:
        result.add(
            Diagnostic(
                code="NB-E002",
                message=(
                    f"Connection {connection.id!r} target node "
                    f"{connection.target_node!r} does not exist"
                ),
                severity=DiagnosticSeverity.ERROR,
                connection_id=connection.id,
            )
        )
        return

    source_node = graph.nodes[connection.source_node]
    target_node = graph.nodes[connection.target_node]
    try:
        source_socket = source_node.socket(connection.source_socket)
    except KeyError:
        result.add(
            Diagnostic(
                code="NB-E002",
                message=(
                    f"Connection {connection.id!r} source socket "
                    f"{connection.source_socket!r} does not exist on "
                    f"{connection.source_node!r}"
                ),
                severity=DiagnosticSeverity.ERROR,
                connection_id=connection.id,
                node_id=connection.source_node,
            )
        )
        return
    try:
        target_socket = target_node.socket(connection.target_socket)
    except KeyError:
        result.add(
            Diagnostic(
                code="NB-E002",
                message=(
                    f"Connection {connection.id!r} target socket "
                    f"{connection.target_socket!r} does not exist on "
                    f"{connection.target_node!r}"
                ),
                severity=DiagnosticSeverity.ERROR,
                connection_id=connection.id,
                node_id=connection.target_node,
            )
        )
        return

    if source_socket.direction is not SocketDirection.OUTPUT:
        result.add(
            Diagnostic(
                code="NB-E003",
                message=(
                    f"Connection {connection.id!r} does not start at an output socket"
                ),
                severity=DiagnosticSeverity.ERROR,
                connection_id=connection.id,
                socket_id=source_socket.id,
            )
        )
    if target_socket.direction is not SocketDirection.INPUT:
        result.add(
            Diagnostic(
                code="NB-E003",
                message=(
                    f"Connection {connection.id!r} does not land on an input socket"
                ),
                severity=DiagnosticSeverity.ERROR,
                connection_id=connection.id,
                socket_id=target_socket.id,
            )
        )

    incoming = graph.incoming(connection.target_node, connection.target_socket)
    if len(incoming) > 1:
        result.add(
            Diagnostic(
                code="NB-W004",
                message=(
                    f"Input {connection.target_node}.{target_socket.name} "
                    f"has {len(incoming)} incoming connections"
                ),
                severity=DiagnosticSeverity.WARNING,
                connection_id=connection.id,
                node_id=connection.target_node,
                socket_id=target_socket.id,
            )
        )

    compatibility = compare_types(source_socket.data_type, target_socket.data_type)
    if compatibility is TypeCompatibility.INCOMPATIBLE:
        result.add(
            Diagnostic(
                code="NB-W001",
                message=(
                    f"Type mismatch on connection {connection.id}: "
                    f"{source_socket.data_type} → {target_socket.data_type}"
                ),
                severity=DiagnosticSeverity.WARNING,
                connection_id=connection.id,
                details={
                    "source_type": source_socket.data_type.name,
                    "target_type": target_socket.data_type.name,
                    "compatibility": compatibility.value,
                },
            )
        )
    elif compatibility is TypeCompatibility.CONVERTIBLE:
        result.add(
            Diagnostic(
                code="NB-I001",
                message=(
                    f"Implicit conversion may be required on {connection.id}: "
                    f"{source_socket.data_type} → {target_socket.data_type}"
                ),
                severity=DiagnosticSeverity.INFO,
                connection_id=connection.id,
                details={"compatibility": compatibility.value},
            )
        )


def _validate_cycles(graph: IRGraph, result: ValidationResult) -> None:
    try:
        graph.topological_order()
    except ValueError:
        result.add(
            Diagnostic(
                code="NB-W003",
                message=f"Graph {graph.id!r} contains a directed cycle",
                severity=DiagnosticSeverity.WARNING,
            )
        )


def _validate_nested_references(graph: IRGraph, result: ValidationResult) -> None:
    for node in graph.nodes.values():
        if node.nested_graph_id and node.operation != "graph.group":
            result.add(
                Diagnostic(
                    code="NB-W006",
                    message=(
                        f"Node {node.id!r} has nested_graph_id but operation "
                        f"{node.operation!r} is not graph.group"
                    ),
                    severity=DiagnosticSeverity.WARNING,
                    node_id=node.id,
                    operation=node.operation,
                )
            )
