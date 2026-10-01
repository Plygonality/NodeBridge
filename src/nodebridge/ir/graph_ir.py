"""DCC-independent graph IR.

This layer preserves structure: nodes, sockets, links, parameters, and
nested groups. It does not decide what the graph *means*. Semantic
operations are produced later by :mod:`nodebridge.compiler.semanticize`.

Source node types (``GeometryNodeDistributePointsOnFaces``, a SOP type, a
PCG settings class) are metadata on :attr:`GraphNode.type_name`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nodebridge.core.values import JSONValue, normalize_value


@dataclass
class GraphSocket:
    """One named socket on a graph node or on a group interface."""

    name: str
    direction: str
    data_type: str = "unknown"
    default: JSONValue = None
    identifier: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Graph socket name must be non-empty")
        if self.direction not in {"input", "output"}:
            raise ValueError(f"Socket direction must be input or output, not {self.direction!r}")
        self.default = normalize_value(self.default)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "direction": self.direction,
            "data_type": self.data_type,
        }
        if self.identifier:
            payload["identifier"] = self.identifier
        if self.default is not None:
            payload["default"] = self.default
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphSocket:
        return cls(
            name=str(data["name"]),
            direction=str(data.get("direction") or "input"),
            data_type=str(data.get("data_type") or "unknown"),
            default=data.get("default"),
            identifier=str(data.get("identifier") or ""),
        )


@dataclass
class NodeParameter:
    """A constant stored on a node rather than on a socket."""

    name: str
    value: JSONValue = None
    data_type: str = "any"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Parameter name must be non-empty")
        self.value = normalize_value(self.value)

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value, "data_type": self.data_type}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NodeParameter:
        return cls(
            name=str(data["name"]),
            value=data.get("value"),
            data_type=str(data.get("data_type") or "any"),
        )


@dataclass
class GraphNode:
    """One node in a source graph. ``type_name`` is source syntax, not meaning."""

    id: str
    type_name: str
    name: str = ""
    label: str = ""
    inputs: list[GraphSocket] = field(default_factory=list)
    outputs: list[GraphSocket] = field(default_factory=list)
    parameters: list[NodeParameter] = field(default_factory=list)
    location: tuple[float, float] | None = None
    muted: bool = False
    nested_tree_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Graph node id must be non-empty")
        if not self.type_name:
            raise ValueError(f"Graph node {self.id!r} is missing a type name")

    def parameter(self, name: str) -> JSONValue:
        for item in self.parameters:
            if item.name == name:
                return item.value
        return None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "type_name": self.type_name,
            "name": self.name,
            "label": self.label,
            "inputs": [socket.as_dict() for socket in self.inputs],
            "outputs": [socket.as_dict() for socket in self.outputs],
            "parameters": [item.as_dict() for item in self.parameters],
            "muted": self.muted,
            "metadata": dict(self.metadata),
        }
        if self.location is not None:
            payload["location"] = list(self.location)
        if self.nested_tree_id:
            payload["nested_tree_id"] = self.nested_tree_id
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphNode:
        location = data.get("location")
        parsed: tuple[float, float] | None = None
        if isinstance(location, (list, tuple)) and len(location) >= 2:
            parsed = (float(location[0]), float(location[1]))
        return cls(
            id=str(data["id"]),
            type_name=str(data["type_name"]),
            name=str(data.get("name") or ""),
            label=str(data.get("label") or ""),
            inputs=[GraphSocket.from_dict(item) for item in data.get("inputs") or []],
            outputs=[GraphSocket.from_dict(item) for item in data.get("outputs") or []],
            parameters=[NodeParameter.from_dict(item) for item in data.get("parameters") or []],
            location=parsed,
            muted=bool(data.get("muted") or False),
            nested_tree_id=data.get("nested_tree_id"),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class GraphEdge:
    """A socket connection. Editor placement is not part of the edge."""

    id: str
    source_node: str
    source_socket: str
    target_node: str
    target_socket: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_node": self.source_node,
            "source_socket": self.source_socket,
            "target_node": self.target_node,
            "target_socket": self.target_socket,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphEdge:
        return cls(
            id=str(data.get("id") or ""),
            source_node=str(data["source_node"]),
            source_socket=str(data["source_socket"]),
            target_node=str(data["target_node"]),
            target_socket=str(data["target_socket"]),
        )


@dataclass
class NodeTree:
    """A node tree and its nested groups.

    ``system`` is ``geometry_nodes``, ``shader``, or ``compositor``.
    Nested groups are stored in :attr:`groups` and referenced by
    :attr:`GraphNode.nested_tree_id`. They are not flattened.
    """

    id: str
    name: str
    system: str
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    interface_inputs: list[GraphSocket] = field(default_factory=list)
    interface_outputs: list[GraphSocket] = field(default_factory=list)
    groups: dict[str, NodeTree] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Node tree id must be non-empty")
        if not self.name:
            raise ValueError("Node tree name must be non-empty")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "system": self.system,
            "nodes": [node.as_dict() for node in self.nodes.values()],
            "edges": [edge.as_dict() for edge in self.edges],
            "interface_inputs": [socket.as_dict() for socket in self.interface_inputs],
            "interface_outputs": [socket.as_dict() for socket in self.interface_outputs],
            "groups": [group.as_dict() for group in self.groups.values()],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NodeTree:
        nodes = [GraphNode.from_dict(item) for item in data.get("nodes") or []]
        groups = [cls.from_dict(item) for item in data.get("groups") or []]
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            system=str(data.get("system") or "geometry_nodes"),
            nodes={node.id: node for node in nodes},
            edges=[GraphEdge.from_dict(item) for item in data.get("edges") or []],
            interface_inputs=[GraphSocket.from_dict(item) for item in data.get("interface_inputs") or []],
            interface_outputs=[
                GraphSocket.from_dict(item) for item in data.get("interface_outputs") or []
            ],
            groups={group.id: group for group in groups},
            metadata=dict(data.get("metadata") or {}),
        )
