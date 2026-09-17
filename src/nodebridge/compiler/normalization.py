"""Normalization passes: many-to-one fusion, constant folding, dead nodes.

Normalization rewrites IR into a smaller semantic form before a target
host is consulted. Topology may change; meaning must not.
"""

from __future__ import annotations

from nodebridge.compiler.clone import clone_graph
from nodebridge.core.graph import IRGraph
from nodebridge.core.link import IRConnection
from nodebridge.core.node import IRNode
from nodebridge.core.socket import IRSocket, SocketDirection
from nodebridge.core.types import DataType


class CanonicalizeOperationsPass:
    """Resolve operation aliases to canonical registry names."""

    name = "canonicalize"

    def apply(self, graph: IRGraph) -> IRGraph:
        from nodebridge.core.operations import DEFAULT_OPERATION_REGISTRY

        current = clone_graph(graph)
        for node in current.nodes.values():
            node.operation = DEFAULT_OPERATION_REGISTRY.canonicalize(node.operation)
        for child in current.graphs.values():
            rewritten = self.apply(child)
            current.graphs[child.id] = rewritten
        return current


class FuseClampPass:
    """Fuse min(max(x, lo), hi) or max(min(x, hi), lo) into math.clamp."""

    name = "fuse_clamp"

    def apply(self, graph: IRGraph) -> IRGraph:
        current = clone_graph(graph)
        changed = True
        while changed:
            changed = False
            for node in list(current.nodes.values()):
                if node.operation not in {"math.min", "math.max"}:
                    continue
                fused = _try_fuse_clamp(current, node)
                if fused:
                    changed = True
                    break
        return current


class ConstantFoldPass:
    """Fold math/vector nodes whose inputs are all constants."""

    name = "constant_fold"

    def apply(self, graph: IRGraph) -> IRGraph:
        current = clone_graph(graph)
        for node_id in list(current.topological_order() if _acyclic(current) else current.nodes):
            node = current.nodes.get(node_id)
            if node is None:
                continue
            if current.incoming(node.id):
                continue
            folded = _fold_node(node)
            if folded is None:
                continue
            outgoing = list(current.outgoing(node.id))
            if not outgoing:
                continue
            for connection in outgoing:
                target = current.nodes[connection.target_node]
                try:
                    socket = target.socket(connection.target_socket)
                except KeyError:
                    continue
                socket.default = folded
            _remove_node(current, node.id)
        return current


class DeadNodeElimPass:
    """Remove nodes whose outputs are unused (except graph.output).

    Isolated fragments with no graph.output are left intact so single-operation
    compilation still produces a native plan.
    """

    name = "dead_node_elim"

    def apply(self, graph: IRGraph) -> IRGraph:
        current = clone_graph(graph)
        if not any(node.operation == "graph.output" for node in current.nodes.values()):
            return current
        changed = True
        while changed:
            changed = False
            for node in list(current.nodes.values()):
                if node.operation in {"graph.output", "graph.input"}:
                    continue
                if current.outgoing(node.id):
                    continue
                _remove_node(current, node.id)
                changed = True
        return current


def normalize_graph(graph: IRGraph) -> IRGraph:
    """Run the default normalization pipeline."""
    from nodebridge.core.passes import PassPipeline

    pipeline = PassPipeline(
        [CanonicalizeOperationsPass(), FuseClampPass(), ConstantFoldPass(), DeadNodeElimPass()]
    )
    return pipeline.run(graph)


def _acyclic(graph: IRGraph) -> bool:
    try:
        graph.topological_order()
        return True
    except ValueError:
        return False


def _try_fuse_clamp(graph: IRGraph, outer: IRNode) -> bool:
    incoming = graph.incoming(outer.id)
    if len(incoming) != 1:
        return False
    inner = graph.nodes.get(incoming[0].source_node)
    if inner is None:
        return False
    pair = {inner.operation, outer.operation}
    if pair != {"math.min", "math.max"}:
        return False
    lo_node, hi_node = (inner, outer) if inner.operation == "math.max" else (outer, inner)
    if lo_node.operation != "math.max" or hi_node.operation != "math.min":
        return False
    clamp = IRNode(id=outer.id, operation="math.clamp", metadata=outer.metadata)
    value_socket = _first_connected_input(graph, inner) or _socket_named(inner, "a")
    if value_socket is None:
        return False
    clamp.add_socket(
        IRSocket.input("clamp_value", "value", DataType.FLOAT, default=value_socket.default)
    )
    lo_default = _unconnected_default(graph, lo_node, "b") or 0.0
    hi_default = _unconnected_default(graph, hi_node, "b") or 1.0
    clamp.add_socket(IRSocket.input("clamp_min", "min", DataType.FLOAT, default=lo_default))
    clamp.add_socket(IRSocket.input("clamp_max", "max", DataType.FLOAT, default=hi_default))
    out_socket = next(iter(outer.outputs.values()), None)
    clamp.add_socket(
        IRSocket.output(
            out_socket.id if out_socket else "clamp_out",
            "value",
            DataType.FLOAT,
        )
    )
    value_link = incoming[0]
    outgoing = list(graph.outgoing(outer.id))
    _remove_node(graph, inner.id)
    graph.nodes[outer.id] = clamp
    source_node = graph.nodes.get(value_link.source_node)
    if source_node is not None:
        graph.add_connection(
            IRConnection(
                id=value_link.id,
                source_node=value_link.source_node,
                source_socket=value_link.source_socket,
                target_node=clamp.id,
                target_socket="clamp_value",
            )
        )
    for connection in outgoing:
        graph.add_connection(
            IRConnection(
                id=connection.id,
                source_node=clamp.id,
                source_socket=next(iter(clamp.outputs)),
                target_node=connection.target_node,
                target_socket=connection.target_socket,
            )
        )
    return True


def _first_connected_input(graph: IRGraph, node: IRNode) -> IRSocket | None:
    incoming = graph.incoming(node.id)
    if not incoming:
        return next(iter(node.inputs.values()), None)
    try:
        return node.socket(incoming[0].target_socket)
    except KeyError:
        return next(iter(node.inputs.values()), None)


def _socket_named(node: IRNode, name: str) -> IRSocket | None:
    try:
        return node.socket_by_name(name, SocketDirection.INPUT)
    except KeyError:
        return next(iter(node.inputs.values()), None)


def _unconnected_default(graph: IRGraph, node: IRNode, name: str) -> object:
    socket = _socket_named(node, name)
    if socket is None:
        return None
    if graph.incoming(node.id, socket.id):
        return None
    return socket.default


def _fold_node(node: IRNode) -> float | list[float] | None:
    values = []
    for socket in node.inputs.values():
        if socket.default is None:
            return None
        values.append(socket.default)
    if node.operation.startswith("math.") and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
        a = float(values[0]) if values else 0.0
        b = float(values[1]) if len(values) > 1 else 0.0
        ops = {
            "math.add": a + b,
            "math.subtract": a - b,
            "math.multiply": a * b,
            "math.divide": a / b if b else 0.0,
            "math.min": min(a, b),
            "math.max": max(a, b),
            "math.power": a ** b,
        }
        if node.operation == "math.clamp":
            value = float(values[0])
            lo = float(values[1]) if len(values) > 1 else 0.0
            hi = float(values[2]) if len(values) > 2 else 1.0
            return max(lo, min(hi, value))
        return ops.get(node.operation)
    if node.operation in {"vector.add", "vector.subtract"} and all(isinstance(v, list) for v in values):
        a = [float(x) for x in values[0]]
        b = [float(x) for x in values[1]] if len(values) > 1 else [0.0, 0.0, 0.0]
        if node.operation == "vector.add":
            return [a[i] + b[i] for i in range(min(len(a), len(b)))]
        return [a[i] - b[i] for i in range(min(len(a), len(b)))]
    return None


def _remove_node(graph: IRGraph, node_id: str) -> None:
    graph.connections = [
        connection
        for connection in graph.connections
        if connection.source_node != node_id and connection.target_node != node_id
    ]
    graph.nodes.pop(node_id, None)
