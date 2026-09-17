"""Host-neutral native graph description.

A :class:`NativeGraph` is what a frontend consumes and a backend produces.
It is not the semantic IR: node ``type`` values are host-native identifiers
such as ``GeometryNodeTransform`` or ``scatter``.

Native graphs are JSON-serializable fixtures. They never contain executable
code. Loading a native graph does not run host SDKs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nodebridge.core.values import JSONValue, normalize_value


@dataclass
class NativeSocket:
    """A named port on a native host node."""

    name: str
    data_type: str = "unknown"
    default: JSONValue = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Native socket name must be non-empty")
        self.default = normalize_value(self.default)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name, "data_type": self.data_type}
        if self.default is not None:
            payload["default"] = self.default
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NativeSocket:
        return cls(
            name=str(data["name"]),
            data_type=str(data.get("data_type") or "unknown"),
            default=data.get("default"),
        )


@dataclass
class NativeNode:
    """One host-native node in a construction plan or extracted graph."""

    id: str
    type: str
    name: str = ""
    inputs: list[NativeSocket] = field(default_factory=list)
    outputs: list[NativeSocket] = field(default_factory=list)
    parameters: dict[str, JSONValue] = field(default_factory=dict)
    position: tuple[float, float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Native node id must be non-empty")
        if not self.type:
            raise ValueError(f"Native node {self.id!r} is missing a type")
        self.parameters = {
            str(key): normalize_value(value) for key, value in self.parameters.items()
        }

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "inputs": [socket.as_dict() for socket in self.inputs],
            "outputs": [socket.as_dict() for socket in self.outputs],
            "parameters": dict(self.parameters),
            "metadata": dict(self.metadata),
        }
        if self.position is not None:
            payload["position"] = list(self.position)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NativeNode:
        position = data.get("position")
        parsed_position: tuple[float, float] | None = None
        if isinstance(position, (list, tuple)) and len(position) == 2:
            parsed_position = (float(position[0]), float(position[1]))
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            name=str(data.get("name") or ""),
            inputs=[NativeSocket.from_dict(item) for item in data.get("inputs") or []],
            outputs=[NativeSocket.from_dict(item) for item in data.get("outputs") or []],
            parameters=dict(data.get("parameters") or {}),
            position=parsed_position,
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class NativeLink:
    """A directed connection between native nodes."""

    source_node: str
    source_socket: str
    target_node: str
    target_socket: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_node": self.source_node,
            "source_socket": self.source_socket,
            "target_node": self.target_node,
            "target_socket": self.target_socket,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NativeLink:
        return cls(
            source_node=str(data["source_node"]),
            source_socket=str(data["source_socket"]),
            target_node=str(data["target_node"]),
            target_socket=str(data["target_socket"]),
        )


@dataclass
class NativeGraph:
    """Host-native graph used as a frontend source or backend construction plan."""

    host: str
    system: str
    name: str
    nodes: list[NativeNode] = field(default_factory=list)
    links: list[NativeLink] = field(default_factory=list)
    interface_inputs: list[NativeSocket] = field(default_factory=list)
    interface_outputs: list[NativeSocket] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def node_map(self) -> dict[str, NativeNode]:
        return {node.id: node for node in self.nodes}

    def as_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "system": self.system,
            "name": self.name,
            "nodes": [node.as_dict() for node in self.nodes],
            "links": [link.as_dict() for link in self.links],
            "interface_inputs": [socket.as_dict() for socket in self.interface_inputs],
            "interface_outputs": [socket.as_dict() for socket in self.interface_outputs],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NativeGraph:
        if not isinstance(data, dict):
            raise ValueError("Native graph must be a JSON object")
        return cls(
            host=str(data.get("host") or ""),
            system=str(data.get("system") or ""),
            name=str(data.get("name") or "untitled"),
            nodes=[NativeNode.from_dict(item) for item in data.get("nodes") or []],
            links=[NativeLink.from_dict(item) for item in data.get("links") or []],
            interface_inputs=[
                NativeSocket.from_dict(item) for item in data.get("interface_inputs") or []
            ],
            interface_outputs=[
                NativeSocket.from_dict(item) for item in data.get("interface_outputs") or []
            ],
            metadata=dict(data.get("metadata") or {}),
        )

    def incoming(self, node_id: str, socket: str | None = None) -> list[NativeLink]:
        result: list[NativeLink] = []
        for link in self.links:
            if link.target_node != node_id:
                continue
            if socket is None or link.target_socket == socket:
                result.append(link)
        return result

    def outgoing(self, node_id: str, socket: str | None = None) -> list[NativeLink]:
        result: list[NativeLink] = []
        for link in self.links:
            if link.source_node != node_id:
                continue
            if socket is None or link.source_socket == socket:
                result.append(link)
        return result
