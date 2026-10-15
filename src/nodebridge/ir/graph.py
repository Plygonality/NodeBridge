"""Graph IR.

This representation preserves the source graph: nodes, sockets, links, and
nested groups. It does not say what the graph means. A Blender node type is
stored as source metadata, not as the identity of the operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from nodebridge.ir.types import DataType


class GraphSystem(str, Enum):
    GEOMETRY = "geometry_nodes"
    SHADER = "shader"
    COMPOSITOR = "compositor"


class SocketDirection(str, Enum):
    INPUT = "input"
    OUTPUT = "output"


JSONValue = Any


@dataclass
class NodeParameter:
    """A constant stored on a source node, separate from a linked socket."""

    name: str
    value: JSONValue = None
    data_type: DataType = DataType.ANY
    exposed: bool = False
    identifier: str = ""


@dataclass
class GraphSocket:
    """One input or output on a source node."""

    identifier: str
    name: str
    direction: SocketDirection
    data_type: DataType = DataType.ANY
    default: JSONValue = None
    is_field: bool = False
    is_multi_input: bool = False
    enabled: bool = True
    metadata: dict[str, JSONValue] = field(default_factory=dict)


@dataclass
class GraphNode:
    """One source node. ``node_type`` is the DCC type, kept as metadata."""

    id: str
    name: str
    node_type: str
    inputs: list[GraphSocket] = field(default_factory=list)
    outputs: list[GraphSocket] = field(default_factory=list)
    parameters: list[NodeParameter] = field(default_factory=list)
    location: tuple[float, float] | None = None
    mute: bool = False
    label: str = ""
    nested: NodeTree | None = None
    properties: dict[str, JSONValue] = field(default_factory=dict)
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def input(self, identifier: str) -> GraphSocket | None:
        for socket in self.inputs:
            if socket.identifier == identifier or socket.name == identifier:
                return socket
        return None

    def output(self, identifier: str) -> GraphSocket | None:
        for socket in self.outputs:
            if socket.identifier == identifier or socket.name == identifier:
                return socket
        return None

    def parameter(self, name: str, default: JSONValue = None) -> JSONValue:
        socket = self.input(name)
        if socket is not None and socket.default is not None:
            return socket.default
        for item in self.parameters:
            if item.name == name or item.identifier == name:
                return item.value
        if name in self.properties:
            return self.properties[name]
        return default


@dataclass
class GraphEdge:
    """A socket connection. Endpoints are ids and socket identifiers."""

    id: str
    from_node: str
    from_socket: str
    to_node: str
    to_socket: str


@dataclass
class InterfaceSocket:
    """A user-facing parameter on a node group."""

    identifier: str
    name: str
    direction: SocketDirection
    data_type: DataType = DataType.ANY
    default: JSONValue = None
    minimum: JSONValue = None
    maximum: JSONValue = None
    description: str = ""
    is_field: bool = False


@dataclass
class NodeTree:
    """A complete source node tree, including nested groups."""

    id: str
    name: str
    system: GraphSystem
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    interface: list[InterfaceSocket] = field(default_factory=list)
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def node(self, node_id: str) -> GraphNode | None:
        for item in self.nodes:
            if item.id == node_id:
                return item
        return None

    def edges_to(self, node_id: str, socket: str | None = None) -> list[GraphEdge]:
        found = []
        for edge in self.edges:
            if edge.to_node != node_id:
                continue
            if socket is not None and edge.to_socket != socket:
                continue
            found.append(edge)
        return found

    def edges_from(self, node_id: str) -> list[GraphEdge]:
        return [edge for edge in self.edges if edge.from_node == node_id]
