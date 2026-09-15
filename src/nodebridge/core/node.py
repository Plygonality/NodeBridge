"""IR nodes: semantic operations with sockets and parameters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nodebridge.core.ids import require_id
from nodebridge.core.metadata import Metadata
from nodebridge.core.socket import IRSocket, SocketDirection
from nodebridge.core.types import DataType, TypeRef
from nodebridge.core.values import JSONValue, normalize_value


@dataclass
class IRParameter:
    """A typed constant that is not a socket (operation mode, enum, flag)."""

    name: str
    data_type: TypeRef
    value: JSONValue = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Parameter name must be non-empty")
        if not isinstance(self.data_type, TypeRef):
            self.data_type = TypeRef.of(self.data_type)
        self.value = normalize_value(self.value)


@dataclass
class IRNode:
    """A single semantic operation in an IR graph.

    ``operation`` is a dotted identifier such as ``geometry.transform``.
    It is *not* a source-application node type. Source type names belong
    in :attr:`metadata`.
    """

    id: str
    operation: str
    inputs: dict[str, IRSocket] = field(default_factory=dict)
    outputs: dict[str, IRSocket] = field(default_factory=dict)
    parameters: dict[str, IRParameter] = field(default_factory=dict)
    metadata: Metadata = field(default_factory=Metadata)
    nested_graph_id: str | None = None

    def __post_init__(self) -> None:
        require_id(self.id, what="node id")
        if not self.operation:
            raise ValueError(f"Node {self.id!r} is missing an operation")
        self.inputs = dict(self.inputs)
        self.outputs = dict(self.outputs)
        self.parameters = dict(self.parameters)
        if self.metadata.mapping.ir_node_id == "":
            self.metadata.mapping.ir_node_id = self.id

    def socket(self, socket_id: str) -> IRSocket:
        """Return an input or output socket by ID."""
        if socket_id in self.inputs:
            return self.inputs[socket_id]
        if socket_id in self.outputs:
            return self.outputs[socket_id]
        raise KeyError(f"Node {self.id!r} has no socket {socket_id!r}")

    def socket_by_name(
        self, name: str, direction: SocketDirection | None = None
    ) -> IRSocket:
        """Return the first socket with *name*, optionally filtered by direction."""
        pools: list[dict[str, IRSocket]] = []
        if direction is None or direction is SocketDirection.INPUT:
            pools.append(self.inputs)
        if direction is None or direction is SocketDirection.OUTPUT:
            pools.append(self.outputs)
        for pool in pools:
            for socket in pool.values():
                if socket.name == name:
                    return socket
        raise KeyError(f"Node {self.id!r} has no socket named {name!r}")

    def add_socket(self, socket: IRSocket) -> IRSocket:
        """Attach *socket* to this node. IDs must be unique across both sides."""
        if socket.id in self.inputs or socket.id in self.outputs:
            raise ValueError(
                f"Node {self.id!r} already has a socket {socket.id!r}"
            )
        target = (
            self.inputs
            if socket.direction is SocketDirection.INPUT
            else self.outputs
        )
        target[socket.id] = socket
        return socket

    def set_parameter(
        self,
        name: str,
        value: JSONValue,
        data_type: str | DataType | TypeRef = DataType.STRING,
    ) -> IRParameter:
        """Create or replace a parameter on this node."""
        parameter = IRParameter(name=name, data_type=TypeRef.of(data_type), value=value)
        self.parameters[name] = parameter
        return parameter
