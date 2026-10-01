"""Graph rewrite rules.

A rule matches a semantic pattern and replaces it with a smaller semantic
pattern. Rules are independent of any DCC. Backends only see the rewritten
operations.

Rules must not fire when an intermediate node has extra consumers. That
keeps shared subgraphs intact.
"""

from __future__ import annotations

from dataclasses import dataclass

from nodebridge.compiler.clone import clone_graph
from nodebridge.core.graph import IRGraph
from nodebridge.core.link import IRConnection
from nodebridge.core.node import IRNode
from nodebridge.core.socket import IRSocket
from nodebridge.core.types import DataType


@dataclass
class RewriteRecord:
    """One successful application of a rule."""

    rule: str
    removed: tuple[str, ...]
    created: str
    note: str


class CollapseReroutePass:
    """Delete ``graph.reroute`` nodes and reconnect their neighbors."""

    name = "collapse_reroute"

    def apply(self, graph: IRGraph) -> IRGraph:
        current = clone_graph(graph)
        for node in list(current.nodes.values()):
            if node.operation != "graph.reroute":
                continue
            incoming = current.incoming(node.id)
            outgoing = current.outgoing(node.id)
            if len(incoming) != 1:
                continue
            source = incoming[0]
            for link in outgoing:
                current.add_connection(
                    IRConnection(
                        id=f"{link.id}__bypass",
                        source_node=source.source_node,
                        source_socket=source.source_socket,
                        target_node=link.target_node,
                        target_socket=link.target_socket,
                    )
                )
            _remove(current, node.id)
        return current


class SpatialNoiseMaskPass:
    """Fuse position → noise → map range → compare into ``selection.spatial_noise``.

    The fused operation means "a spatial noise field used as a mask". The
    noise implementation is still host-specific and is classified by the
    backend, not by this rule.
    """

    name = "spatial_noise_mask"

    def apply(self, graph: IRGraph) -> IRGraph:
        current = clone_graph(graph)
        compares = [node for node in current.nodes.values() if node.operation == "selection.compare"]
        for compare in compares:
            chain = _noise_chain(current, compare)
            if chain is None:
                continue
            noise, map_range = chain
            if not _exclusive(current, noise) or not _exclusive(current, map_range):
                continue
            fused = IRNode(id=f"{compare.id}__mask", operation="selection.spatial_noise")
            fused.metadata.provenance = compare.metadata.provenance
            fused.metadata.history = list(compare.metadata.history)
            fused.add_socket(IRSocket.input(f"{fused.id}_vector", "vector", DataType.VECTOR3))
            fused.add_socket(IRSocket.output(f"{fused.id}_result", "result", DataType.BOOLEAN))
            for name in ("scale", "detail", "roughness", "seed"):
                if name in noise.parameters:
                    fused.set_parameter(name, noise.parameters[name].value)
            current.add_node(fused)
            for link in current.incoming(noise.id):
                if link.target_socket == _socket_id(noise, "vector") or _socket_name(noise, link.target_socket) == "vector":
                    current.add_connection(
                        IRConnection(
                            id=f"{link.id}__mask",
                            source_node=link.source_node,
                            source_socket=link.source_socket,
                            target_node=fused.id,
                            target_socket=f"{fused.id}_vector",
                        )
                    )
            for link in list(current.outgoing(compare.id)):
                current.add_connection(
                    IRConnection(
                        id=f"{link.id}__mask",
                        source_node=fused.id,
                        source_socket=f"{fused.id}_result",
                        target_node=link.target_node,
                        target_socket=link.target_socket,
                    )
                )
            _remove(current, compare.id)
            _remove(current, map_range.id)
            _remove(current, noise.id)
        return current


class FuseInstanceTransformPass:
    """Fold Rotate Instances / Scale Instances into the preceding Instance operation.

    Blender often authors instance placement as three nodes. The semantic
    form is one ``geometry.instance`` with rotation and scale inputs.
    """

    name = "fuse_instance_transform"

    def apply(self, graph: IRGraph) -> IRGraph:
        current = clone_graph(graph)
        changed = True
        while changed:
            changed = False
            for node in list(current.nodes.values()):
                if node.operation not in {"geometry.rotate_instances", "geometry.scale_instances"}:
                    continue
                if not _exclusive(current, node):
                    continue
                incoming = current.incoming(node.id)
                geometry_link = _link_named(current, incoming, "geometry")
                if geometry_link is None:
                    continue
                producer = current.nodes.get(geometry_link.source_node)
                if producer is None or producer.operation != "geometry.instance":
                    continue
                field_name = "rotation" if node.operation == "geometry.rotate_instances" else "scale"
                field_link = _link_named(current, incoming, field_name)
                _ensure_input(producer, field_name, DataType.VECTOR3)
                if field_link is not None:
                    current.add_connection(
                        IRConnection(
                            id=f"{field_link.id}__fused",
                            source_node=field_link.source_node,
                            source_socket=field_link.source_socket,
                            target_node=producer.id,
                            target_socket=_socket_id(producer, field_name),
                        )
                    )
                for link in list(current.outgoing(node.id)):
                    current.add_connection(
                        IRConnection(
                            id=f"{link.id}__fused",
                            source_node=producer.id,
                            source_socket=_socket_id(producer, "instances"),
                            target_node=link.target_node,
                            target_socket=link.target_socket,
                        )
                    )
                _remove(current, node.id)
                changed = True
                break
        return current


def apply_rewrite_rules(graph: IRGraph) -> IRGraph:
    """Run the default semantic rewrite pipeline."""
    current = graph
    for rule in (CollapseReroutePass(), SpatialNoiseMaskPass(), FuseInstanceTransformPass()):
        current = rule.apply(current)
    return current


def _noise_chain(graph: IRGraph, compare: IRNode) -> tuple[IRNode, IRNode] | None:
    incoming = graph.incoming(compare.id)
    if len(incoming) < 1:
        return None
    map_range = None
    for link in incoming:
        producer = graph.nodes.get(link.source_node)
        if producer is not None and producer.operation == "math.map_range":
            map_range = producer
            break
    if map_range is None:
        return None
    noise = None
    for link in graph.incoming(map_range.id):
        producer = graph.nodes.get(link.source_node)
        if producer is not None and producer.operation == "procedural.noise":
            noise = producer
            break
    if noise is None:
        return None
    return noise, map_range


def _exclusive(graph: IRGraph, node: IRNode) -> bool:
    targets = {link.target_node for link in graph.outgoing(node.id)}
    return len(targets) <= 1


def _remove(graph: IRGraph, node_id: str) -> None:
    graph.connections = [
        link
        for link in graph.connections
        if link.source_node != node_id and link.target_node != node_id
    ]
    graph.nodes.pop(node_id, None)


def _socket_id(node: IRNode, name: str) -> str:
    for pool in (node.inputs, node.outputs):
        for socket in pool.values():
            if socket.name == name:
                return socket.id
    raise KeyError(name)


def _socket_name(node: IRNode, socket_id: str) -> str:
    try:
        return node.socket(socket_id).name
    except KeyError:
        return ""


def _link_named(graph: IRGraph, links: list[IRConnection], name: str) -> IRConnection | None:
    for link in links:
        node = graph.nodes.get(link.target_node)
        if node is None:
            continue
        try:
            if node.socket(link.target_socket).name == name:
                return link
        except KeyError:
            continue
    return None


def _ensure_input(node: IRNode, name: str, data_type: DataType) -> None:
    try:
        node.socket_by_name(name)
    except KeyError:
        node.add_socket(IRSocket.input(f"{node.id}_{name}", name, data_type))
