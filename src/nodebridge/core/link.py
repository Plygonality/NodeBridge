"""IR connections: explicit socket-to-socket data-flow edges."""

from __future__ import annotations

from dataclasses import dataclass, field

from nodebridge.core.ids import require_id
from nodebridge.core.metadata import Metadata


@dataclass
class IRConnection:
    """A directed edge from one node's output socket to another's input socket."""

    id: str
    source_node: str
    source_socket: str
    target_node: str
    target_socket: str
    metadata: Metadata = field(default_factory=Metadata)

    def __post_init__(self) -> None:
        require_id(self.id, what="connection id")
        require_id(self.source_node, what="source_node")
        require_id(self.source_socket, what="source_socket")
        require_id(self.target_node, what="target_node")
        require_id(self.target_socket, what="target_socket")

    @property
    def source(self) -> tuple[str, str]:
        """``(node_id, socket_id)`` of the producing endpoint."""
        return self.source_node, self.source_socket

    @property
    def target(self) -> tuple[str, str]:
        """``(node_id, socket_id)`` of the consuming endpoint."""
        return self.target_node, self.target_socket
