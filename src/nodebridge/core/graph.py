"""IR graphs: nodes, connections, nested groups, and exposed interfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from nodebridge.core.ids import IdFactory, require_id
from nodebridge.core.link import IRConnection
from nodebridge.core.metadata import Metadata, Provenance
from nodebridge.core.node import IRNode, IRParameter
from nodebridge.core.socket import IRSocket, SocketDirection
from nodebridge.core.types import DataType, TypeRef
from nodebridge.core.values import JSONValue


class GraphSystem(str, Enum):
    """Kind of procedural graph, independent of the host application."""

    GEOMETRY = "geometry"
    SHADER = "shader"
    COMPOSITOR = "compositor"
    UNKNOWN = "unknown"


@dataclass
class GraphInterface:
    """Exposed inputs and outputs of a graph (group sockets, modifier props)."""

    inputs: dict[str, IRSocket] = field(default_factory=dict)
    outputs: dict[str, IRSocket] = field(default_factory=dict)

    def add(self, socket: IRSocket) -> IRSocket:
        """Add an exposed socket to the matching side of the interface."""
        target = (
            self.inputs
            if socket.direction is SocketDirection.INPUT
            else self.outputs
        )
        if socket.id in target:
            raise ValueError(f"Interface already has socket {socket.id!r}")
        target[socket.id] = socket
        return socket


@dataclass
class IRGraph:
    """A directed procedural graph in NodeBridge IR form.

    Nested groups live in :attr:`graphs`. A group-call node points at a
    nested graph through :attr:`IRNode.nested_graph_id`.
    """

    id: str
    name: str
    system: GraphSystem = GraphSystem.UNKNOWN
    nodes: dict[str, IRNode] = field(default_factory=dict)
    connections: list[IRConnection] = field(default_factory=list)
    graphs: dict[str, IRGraph] = field(default_factory=dict)
    interface: GraphInterface = field(default_factory=GraphInterface)
    metadata: Metadata = field(default_factory=Metadata)
    provenance: Provenance = field(default_factory=Provenance)

    def __post_init__(self) -> None:
        require_id(self.id, what="graph id")
        if not self.name:
            raise ValueError("Graph name must be non-empty")
        if not isinstance(self.system, GraphSystem):
            self.system = GraphSystem(self.system)
        self.nodes = dict(self.nodes)
        self.connections = list(self.connections)
        self.graphs = dict(self.graphs)

    def add_node(self, node: IRNode) -> IRNode:
        """Insert *node*. Node IDs must be unique within this graph."""
        if node.id in self.nodes:
            raise ValueError(f"Graph {self.id!r} already has node {node.id!r}")
        self.nodes[node.id] = node
        return node

    def add_connection(self, connection: IRConnection) -> IRConnection:
        """Insert *connection*. Connection IDs must be unique within this graph."""
        if any(existing.id == connection.id for existing in self.connections):
            raise ValueError(
                f"Graph {self.id!r} already has connection {connection.id!r}"
            )
        self.connections.append(connection)
        return connection

    def add_graph(self, graph: IRGraph) -> IRGraph:
        """Register a nested graph (typically a reusable group)."""
        if graph.id in self.graphs:
            raise ValueError(f"Graph {self.id!r} already has nested graph {graph.id!r}")
        self.graphs[graph.id] = graph
        return graph

    def get_node(self, node_id: str) -> IRNode:
        """Return a node by ID or raise ``KeyError``."""
        return self.nodes[node_id]

    def incoming(
        self, node_id: str, socket_id: str | None = None
    ) -> list[IRConnection]:
        """Connections that land on *node_id*, optionally on one socket."""
        result: list[IRConnection] = []
        for connection in self.connections:
            if connection.target_node != node_id:
                continue
            if socket_id is None or connection.target_socket == socket_id:
                result.append(connection)
        return result

    def outgoing(
        self, node_id: str, socket_id: str | None = None
    ) -> list[IRConnection]:
        """Connections that leave *node_id*, optionally from one socket."""
        result: list[IRConnection] = []
        for connection in self.connections:
            if connection.source_node != node_id:
                continue
            if socket_id is None or connection.source_socket == socket_id:
                result.append(connection)
        return result

    def topological_order(self) -> list[str]:
        """Return node IDs in data-flow order.

        Raises ``ValueError`` if the graph contains a cycle.
        Isolated nodes appear before nodes they do not depend on, ordered
        by ID for determinism.
        """
        incoming_count = {node_id: 0 for node_id in self.nodes}
        adjacency: dict[str, list[str]] = {node_id: [] for node_id in self.nodes}
        for connection in self.connections:
            if (
                connection.source_node not in incoming_count
                or connection.target_node not in incoming_count
            ):
                continue
            adjacency[connection.source_node].append(connection.target_node)
            incoming_count[connection.target_node] += 1

        ready = sorted(
            node_id for node_id, count in incoming_count.items() if count == 0
        )
        ordered: list[str] = []
        while ready:
            node_id = ready.pop(0)
            ordered.append(node_id)
            for successor in sorted(adjacency[node_id]):
                incoming_count[successor] -= 1
                if incoming_count[successor] == 0:
                    ready.append(successor)
                    ready.sort()
        if len(ordered) != len(self.nodes):
            raise ValueError(f"Graph {self.id!r} contains a cycle")
        return ordered

    def all_graphs(self) -> list[IRGraph]:
        """This graph followed by every nested graph, depth-first, by ID."""
        result = [self]
        for graph_id in sorted(self.graphs):
            result.extend(self.graphs[graph_id].all_graphs())
        return result


@dataclass
class GraphBuilder:
    """Deterministic helper for constructing IR graphs in tests and adapters."""

    name: str
    system: GraphSystem = GraphSystem.GEOMETRY
    graph_id: str | None = None
    ids: IdFactory = field(default_factory=IdFactory)
    provenance: Provenance = field(default_factory=Provenance)

    def __post_init__(self) -> None:
        if self.graph_id is None:
            self.graph_id = self.ids.next("graph")
        self.graph = IRGraph(
            id=self.graph_id,
            name=self.name,
            system=self.system,
            provenance=self.provenance,
        )

    def node(
        self,
        operation: str,
        *,
        node_id: str | None = None,
        nested_graph_id: str | None = None,
    ) -> IRNode:
        """Create and register a node."""
        node = IRNode(
            id=node_id or self.ids.next("node"),
            operation=operation,
            nested_graph_id=nested_graph_id,
        )
        self.graph.add_node(node)
        return node

    def input(
        self,
        node: IRNode,
        name: str,
        data_type: str | DataType | TypeRef,
        *,
        default: JSONValue = None,
        socket_id: str | None = None,
    ) -> IRSocket:
        """Add an input socket to *node*."""
        socket = IRSocket.input(
            id=socket_id or self.ids.next("socket"),
            name=name,
            data_type=data_type,
            default=default,
        )
        node.add_socket(socket)
        return socket

    def output(
        self,
        node: IRNode,
        name: str,
        data_type: str | DataType | TypeRef,
        *,
        socket_id: str | None = None,
    ) -> IRSocket:
        """Add an output socket to *node*."""
        socket = IRSocket.output(
            id=socket_id or self.ids.next("socket"),
            name=name,
            data_type=data_type,
        )
        node.add_socket(socket)
        return socket

    def parameter(
        self,
        node: IRNode,
        name: str,
        value: JSONValue,
        data_type: str | DataType | TypeRef = DataType.STRING,
    ) -> IRParameter:
        """Set a parameter on *node*."""
        return node.set_parameter(name, value, data_type)

    def connect(
        self,
        source_node: IRNode | str,
        source_socket: IRSocket | str,
        target_node: IRNode | str,
        target_socket: IRSocket | str,
        *,
        connection_id: str | None = None,
    ) -> IRConnection:
        """Wire two sockets together."""
        connection = IRConnection(
            id=connection_id or self.ids.next("connection"),
            source_node=_node_id(source_node),
            source_socket=_socket_id(source_socket),
            target_node=_node_id(target_node),
            target_socket=_socket_id(target_socket),
        )
        self.graph.add_connection(connection)
        return connection

    def expose(
        self,
        name: str,
        data_type: str | DataType | TypeRef,
        direction: SocketDirection,
        *,
        default: JSONValue = None,
        socket_id: str | None = None,
    ) -> IRSocket:
        """Add an exposed graph-interface socket."""
        if direction is SocketDirection.INPUT:
            socket = IRSocket.input(
                id=socket_id or self.ids.next("socket"),
                name=name,
                data_type=data_type,
                default=default,
            )
        else:
            socket = IRSocket.output(
                id=socket_id or self.ids.next("socket"),
                name=name,
                data_type=data_type,
            )
        self.graph.interface.add(socket)
        return socket


def _node_id(value: IRNode | str) -> str:
    return value.id if isinstance(value, IRNode) else value


def _socket_id(value: IRSocket | str) -> str:
    return value.id if isinstance(value, IRSocket) else value
