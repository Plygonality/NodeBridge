"""Graph IR: a faithful, DCC-independent copy of a source node tree.

The Graph IR preserves *structure*: nodes, sockets, links, parameters,
defaults, interfaces and nested groups. It does not interpret meaning;
that is the job of the Semantic IR. Editor positions are kept only as
optional metadata and are never used for ordering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterator

from .types import DataType


class TreeKind(str, Enum):
    GEOMETRY = "geometry"
    SHADER = "shader"
    COMPOSITOR = "compositor"

    @property
    def label(self) -> str:
        return {"geometry": "Geometry Nodes", "shader": "Shader", "compositor": "Compositor"}[self.value]


@dataclass
class GraphSocket:
    identifier: str
    name: str
    data_type: DataType
    is_output: bool = False
    subtype: str = ""
    default: Any = None
    enabled: bool = True
    linked: bool = False

    def as_dict(self) -> dict:
        data = {"identifier": self.identifier, "name": self.name, "type": self.data_type.value}
        if self.subtype:
            data["subtype"] = self.subtype
        if self.default is not None:
            data["default"] = self.default
        if not self.enabled:
            data["enabled"] = False
        if self.linked:
            data["linked"] = True
        return data

    @classmethod
    def from_dict(cls, data: dict, is_output: bool) -> "GraphSocket":
        return cls(
            identifier=data["identifier"],
            name=data.get("name", data["identifier"]),
            data_type=DataType(data.get("type", "any")),
            is_output=is_output,
            subtype=data.get("subtype", ""),
            default=data.get("default"),
            enabled=data.get("enabled", True),
            linked=data.get("linked", False),
        )


@dataclass
class GraphNode:
    id: str
    type: str
    name: str = ""
    label: str = ""
    inputs: list[GraphSocket] = field(default_factory=list)
    outputs: list[GraphSocket] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    muted: bool = False
    group_tree: str | None = None
    internal_links: list[tuple[str, str]] = field(default_factory=list)
    location: tuple[float, float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return self.label or self.name or self.id

    def input(self, identifier: str) -> GraphSocket | None:
        return next((s for s in self.inputs if s.identifier == identifier), None)

    def output(self, identifier: str) -> GraphSocket | None:
        return next((s for s in self.outputs if s.identifier == identifier), None)

    def find_input(self, name: str, *, enabled_only: bool = True) -> GraphSocket | None:
        """First socket matching ``name`` (preferring enabled), then identifier."""
        return _find(self.inputs, name, enabled_only)

    def find_output(self, name: str, *, enabled_only: bool = True) -> GraphSocket | None:
        return _find(self.outputs, name, enabled_only)

    def as_dict(self) -> dict:
        data: dict[str, Any] = {"id": self.id, "type": self.type}
        if self.name and self.name != self.id:
            data["name"] = self.name
        if self.label:
            data["label"] = self.label
        data["inputs"] = [s.as_dict() for s in self.inputs]
        data["outputs"] = [s.as_dict() for s in self.outputs]
        if self.parameters:
            data["parameters"] = self.parameters
        if self.muted:
            data["muted"] = True
        if self.group_tree:
            data["group_tree"] = self.group_tree
        if self.internal_links:
            data["internal_links"] = [list(pair) for pair in self.internal_links]
        if self.location is not None:
            data["location"] = list(self.location)
        if self.metadata:
            data["metadata"] = self.metadata
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "GraphNode":
        return cls(
            id=data["id"],
            type=data["type"],
            name=data.get("name", data["id"]),
            label=data.get("label", ""),
            inputs=[GraphSocket.from_dict(s, False) for s in data.get("inputs", [])],
            outputs=[GraphSocket.from_dict(s, True) for s in data.get("outputs", [])],
            parameters=dict(data.get("parameters", {})),
            muted=data.get("muted", False),
            group_tree=data.get("group_tree"),
            internal_links=[tuple(pair) for pair in data.get("internal_links", [])],  # type: ignore[misc]
            location=tuple(data["location"]) if data.get("location") else None,  # type: ignore[arg-type]
            metadata=dict(data.get("metadata", {})),
        )


def _find(sockets: list[GraphSocket], name: str, enabled_only: bool) -> GraphSocket | None:
    candidates = [s for s in sockets if s.name == name]
    if enabled_only:
        enabled = [s for s in candidates if s.enabled]
        if enabled:
            return enabled[0]
    if candidates:
        return candidates[0]
    return next((s for s in sockets if s.identifier == name), None)


@dataclass(frozen=True)
class GraphEdge:
    from_node: str
    from_socket: str
    to_node: str
    to_socket: str
    muted: bool = False
    valid: bool = True

    def as_dict(self) -> dict:
        data = {"from": [self.from_node, self.from_socket], "to": [self.to_node, self.to_socket]}
        if self.muted:
            data["muted"] = True
        if not self.valid:
            data["valid"] = False
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "GraphEdge":
        return cls(data["from"][0], data["from"][1], data["to"][0], data["to"][1], data.get("muted", False), data.get("valid", True))


@dataclass
class InterfaceSocket:
    """A user-facing control or geometry input/output of a tree or group."""

    identifier: str
    name: str
    in_out: str  # "INPUT" | "OUTPUT"
    data_type: DataType
    subtype: str = ""
    default: Any = None
    min_value: float | None = None
    max_value: float | None = None
    description: str = ""
    value: Any = None  # modifier / instance override, if known

    @property
    def current(self) -> Any:
        return self.default if self.value is None else self.value

    def as_dict(self) -> dict:
        data = {
            "identifier": self.identifier,
            "name": self.name,
            "in_out": self.in_out,
            "type": self.data_type.value,
        }
        for key in ("subtype", "default", "min_value", "max_value", "description", "value"):
            value = getattr(self, key)
            if value not in (None, ""):
                data[key] = value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "InterfaceSocket":
        return cls(
            identifier=data["identifier"],
            name=data.get("name", data["identifier"]),
            in_out=data.get("in_out", "INPUT"),
            data_type=DataType(data.get("type", "any")),
            subtype=data.get("subtype", ""),
            default=data.get("default"),
            min_value=data.get("min_value"),
            max_value=data.get("max_value"),
            description=data.get("description", ""),
            value=data.get("value"),
        )


@dataclass
class NodeTree:
    name: str
    kind: TreeKind
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    interface: list[InterfaceSocket] = field(default_factory=list)
    is_group: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def inputs(self) -> list[InterfaceSocket]:
        return [s for s in self.interface if s.in_out == "INPUT"]

    @property
    def outputs(self) -> list[InterfaceSocket]:
        return [s for s in self.interface if s.in_out == "OUTPUT"]

    def add(self, node: GraphNode) -> GraphNode:
        self.nodes[node.id] = node
        return node

    def link(self, from_node: str, from_socket: str, to_node: str, to_socket: str) -> GraphEdge:
        edge = GraphEdge(from_node, from_socket, to_node, to_socket)
        self.edges.append(edge)
        return edge

    def incoming(self, node_id: str) -> list[GraphEdge]:
        return [e for e in self.edges if e.to_node == node_id]

    def outgoing(self, node_id: str) -> list[GraphEdge]:
        return [e for e in self.edges if e.from_node == node_id]

    def edge_into(self, node_id: str, socket_identifier: str) -> GraphEdge | None:
        return next(
            (e for e in self.edges if e.to_node == node_id and e.to_socket == socket_identifier and e.valid and not e.muted),
            None,
        )

    def iter_nodes(self) -> Iterator[GraphNode]:
        return iter(self.nodes.values())

    def as_dict(self) -> dict:
        data = {
            "name": self.name,
            "kind": self.kind.value,
            "is_group": self.is_group,
            "interface": [s.as_dict() for s in self.interface],
            "nodes": [n.as_dict() for n in self.nodes.values()],
            "edges": [e.as_dict() for e in self.edges],
        }
        if self.metadata:
            data["metadata"] = self.metadata
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "NodeTree":
        tree = cls(
            name=data["name"],
            kind=TreeKind(data.get("kind", "geometry")),
            interface=[InterfaceSocket.from_dict(s) for s in data.get("interface", [])],
            is_group=data.get("is_group", False),
            metadata=dict(data.get("metadata", {})),
        )
        for node in data.get("nodes", []):
            tree.add(GraphNode.from_dict(node))
        tree.edges = [GraphEdge.from_dict(e) for e in data.get("edges", [])]
        return tree


@dataclass
class GraphDocument:
    """A root tree plus every nested group tree it references."""

    root: str
    trees: dict[str, NodeTree] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)

    @property
    def root_tree(self) -> NodeTree:
        return self.trees[self.root]

    def node_count(self, *, recursive: bool = True) -> int:
        if not recursive:
            return len(self.root_tree.nodes)
        return sum(len(tree.nodes) for tree in self.trees.values())
