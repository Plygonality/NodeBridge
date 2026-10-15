"""Lower a Blender graph IR tree into semantic operations.

Reroutes and muted nodes are wiring, not operations. Nested groups become
semantic subgraphs. Unknown node types become ``UnsupportedOperation`` and
stay in the graph.
"""

from __future__ import annotations

from typing import Callable

from nodebridge.ir.graph import GraphNode, GraphSystem, NodeTree, SocketDirection
from nodebridge.ir.operations import field_port, geometry_port
from nodebridge.ir.semantic import (
    ExposedParameter,
    Operation,
    OperationKind,
    Port,
    SemanticEdge,
    SemanticGraph,
    SourceRef,
)
from nodebridge.ir.types import DataType

LowerResult = tuple[Operation, dict[tuple[str, str], str]]
LowerFn = Callable[[GraphNode, NodeTree], LowerResult]

LOWERERS: dict[str, LowerFn] = {}

_SKIP = {"NodeReroute", "NodeFrame"}
_EXPLICIT_UNSUPPORTED = {
    "GeometryNodeSimulationInput": "Simulation zones have no NodeBridge semantic translation yet.",
    "GeometryNodeSimulationOutput": "Simulation zones have no NodeBridge semantic translation yet.",
    "GeometryNodeRepeatInput": "Repeat zones have no NodeBridge semantic translation yet.",
    "GeometryNodeRepeatOutput": "Repeat zones have no NodeBridge semantic translation yet.",
}


def register(node_type: str) -> Callable[[LowerFn], LowerFn]:
    def decorate(function: LowerFn) -> LowerFn:
        LOWERERS[node_type] = function
        return function

    return decorate


def source_from(node: GraphNode) -> SourceRef:
    return SourceRef(node_ids=(node.id,), node_types=(node.node_type,), node_names=(node.name,))


def number(node: GraphNode, identifier: str, default: float) -> float:
    socket = node.input(identifier)
    if socket is None or socket.default is None:
        return float(default)
    if isinstance(socket.default, (int, float)):
        return float(socket.default)
    if isinstance(socket.default, (list, tuple)) and socket.default:
        return float(socket.default[0])
    return float(default)


def integer(node: GraphNode, identifier: str, default: int) -> int:
    return int(round(number(node, identifier, default)))


def vector(node: GraphNode, identifier: str, default: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> tuple[float, float, float]:
    socket = node.input(identifier)
    if socket is None or not isinstance(socket.default, (list, tuple)):
        return default
    values = list(socket.default) + [0.0, 0.0, 0.0]
    return (float(values[0]), float(values[1]), float(values[2]))


def text(node: GraphNode, identifier: str, default: str = "") -> str:
    socket = node.input(identifier)
    if socket is None or socket.default is None:
        return default
    return str(socket.default)


def finish(
    node: GraphNode,
    operation: Operation,
    inputs: dict[str, str],
    outputs: dict[str, str],
) -> LowerResult:
    mapping: dict[tuple[str, str], str] = {}
    for identifier, port in inputs.items():
        mapping[("input", identifier)] = port
    for identifier, port in outputs.items():
        mapping[("output", identifier)] = port
    operation.source = source_from(node)
    return operation, mapping


def ensure_lowerers() -> None:
    """Register Blender node lowerers. Safe to call more than once."""

    from nodebridge.frontend.blender import compositor_nodes, geometry_nodes, shader_nodes
    from nodebridge.frontend.blender.node_groups import lower_group

    geometry_nodes.register_all(register)
    shader_nodes.register_all(register)
    compositor_nodes.register_all(register)
    LOWERERS["GeometryNodeGroup"] = lower_group
    LOWERERS["ShaderNodeGroup"] = lower_group
    LOWERERS["CompositorNodeGroup"] = lower_group


def lower_tree(tree: NodeTree) -> SemanticGraph:
    """Lower ``tree`` and any nested groups it already parsed."""

    ensure_lowerers()

    operations: list[Operation] = []
    maps: dict[str, dict[tuple[str, str], str]] = {}
    for node in tree.nodes:
        if node.node_type in _SKIP or node.mute:
            continue
        function = LOWERERS.get(node.node_type)
        if function is None:
            operation, mapping = _unsupported(node, tree)
        else:
            operation, mapping = function(node, tree)
        operation.id = node.id
        if not operation.name:
            operation.name = node.label or node.name
        operations.append(operation)
        maps[node.id] = mapping

    edges = _edges(tree, maps)
    by_id = {operation.id: operation for operation in operations}
    for edge in edges:
        operation = by_id.get(edge.to_operation)
        if operation is None or edge.to_port in operation.inputs:
            continue
        if edge.to_port.startswith("geometry_"):
            operation.inputs[edge.to_port] = geometry_port(edge.to_port)
    graph = SemanticGraph(
        name=tree.name,
        system=tree.system,
        operations=operations,
        edges=edges,
        interface=_interface(tree),
        metadata=dict(tree.metadata),
        source_tree_id=tree.id,
    )
    graph.metadata["muted"] = [node.id for node in tree.nodes if node.mute]
    graph.metadata["source_node_count"] = len(tree.nodes)
    return graph


def _edges(tree: NodeTree, maps: dict[str, dict[tuple[str, str], str]]) -> list[SemanticEdge]:
    edges: list[SemanticEdge] = []
    multi_count: dict[tuple[str, str], int] = {}
    for edge in tree.edges:
        resolved = _resolve(tree, edge.from_node, edge.from_socket)
        if resolved is None:
            continue
        source_id, source_socket = resolved
        if source_id not in maps or edge.to_node not in maps:
            continue
        target = tree.node(edge.to_node)
        target_socket = target.input(edge.to_socket) if target else None
        if target_socket is not None and (target_socket.is_multi_input or _join_socket(target, edge.to_socket)):
            key = (edge.to_node, edge.to_socket)
            index = multi_count.get(key, 0)
            multi_count[key] = index + 1
            to_port = f"geometry_{index}"
            _ensure_merge_port(maps, edge.to_node, to_port)
        else:
            to_port = maps[edge.to_node].get(("input", edge.to_socket), edge.to_socket)
        from_port = maps[source_id].get(("output", source_socket), source_socket)
        edges.append(
            SemanticEdge(
                id=edge.id,
                from_operation=source_id,
                from_port=from_port,
                to_operation=edge.to_node,
                to_port=to_port,
            )
        )
    return edges


def _ensure_merge_port(maps: dict[str, dict[tuple[str, str], str]], node_id: str, port: str) -> None:
    # The operation object is updated by the caller through the graph later.
    # Ports are added in lower_tree after edges are known.
    maps[node_id][("input", port)] = port


def _join_socket(node: GraphNode | None, socket: str) -> bool:
    return node is not None and node.node_type == "GeometryNodeJoinGeometry" and socket in {"Geometry", "geometry"}


def _resolve(tree: NodeTree, node_id: str, socket_id: str, seen: set[str] | None = None) -> tuple[str, str] | None:
    seen = set() if seen is None else seen
    if node_id in seen:
        return None
    seen.add(node_id)
    node = tree.node(node_id)
    if node is None:
        return None
    if node.node_type == "NodeReroute" or node.mute:
        incoming = tree.edges_to(node_id)
        if not incoming:
            return None
        return _resolve(tree, incoming[0].from_node, incoming[0].from_socket, seen)
    return node_id, socket_id


def _interface(tree: NodeTree) -> list[ExposedParameter]:
    exposed = []
    for item in tree.interface:
        if item.direction is not SocketDirection.INPUT:
            continue
        exposed.append(
            ExposedParameter(
                name=item.name,
                identifier=item.identifier,
                data_type=item.data_type,
                default=item.default,
                minimum=item.minimum,
                maximum=item.maximum,
                description=item.description,
            )
        )
    return exposed


def _unsupported(node: GraphNode, tree: NodeTree) -> LowerResult:
    reason = _EXPLICIT_UNSUPPORTED.get(
        node.node_type,
        f"No NodeBridge semantic lowering is implemented for {node.node_type}.",
    )
    inputs = {}
    outputs = {}
    input_names = {}
    output_names = {}
    for socket in node.inputs:
        port = _safe_port(socket.identifier)
        role = "geometry" if socket.data_type in {DataType.GEOMETRY, DataType.MESH, DataType.CURVE, DataType.POINTS, DataType.INSTANCES} else "value"
        inputs[port] = geometry_port(port, socket.data_type) if role == "geometry" else field_port(port, socket.data_type)
        input_names[socket.identifier] = port
    for socket in node.outputs:
        port = _safe_port(socket.identifier)
        role = "geometry" if socket.data_type in {DataType.GEOMETRY, DataType.MESH, DataType.CURVE, DataType.POINTS, DataType.INSTANCES} else "value"
        outputs[port] = geometry_port(port, socket.data_type) if role == "geometry" else field_port(port, socket.data_type)
        output_names[socket.identifier] = port
    operation = Operation(
        id=node.id,
        kind=OperationKind.UNSUPPORTED,
        name=node.label or node.name,
        parameters={"source_type": node.node_type, "reason": reason},
        inputs=inputs,
        outputs=outputs,
        notes=[reason],
    )
    return finish(node, operation, input_names, output_names)


def _safe_port(identifier: str) -> str:
    cleaned = "".join(character if character.isalnum() or character == "_" else "_" for character in identifier.lower())
    return cleaned or "value"


def system_label(system: GraphSystem) -> str:
    return {
        GraphSystem.GEOMETRY: "Geometry Nodes",
        GraphSystem.SHADER: "Shader",
        GraphSystem.COMPOSITOR: "Compositor",
    }[system]
