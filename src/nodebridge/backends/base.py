"""Target-backend contract.

Backends consume IR (optionally after rewrite) and produce native graph
*fragments* — one IR operation may become many target nodes. They are
the only modules allowed to import host SDKs such as ``hou``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from nodebridge.core.capabilities import CapabilitySet, TargetCapability
from nodebridge.core.diagnostics import Diagnostic, TranslationStatus
from nodebridge.core.exceptions import BackendError
from nodebridge.core.graph import IRGraph
from nodebridge.core.metadata import SourceMapping
from nodebridge.core.node import IRNode


@dataclass
class TargetNodeSpec:
    """Description of one generated host node.

    ``kind`` is a backend-local type name (for example a future SOP type).
    It is *not* an IR operation.
    """

    id: str
    kind: str
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TargetConnectionSpec:
    """Wiring between generated host nodes."""

    source_node: str
    source_socket: str
    target_node: str
    target_socket: str


@dataclass
class GraphFragment:
    """One-to-many translation result for a single IR node."""

    nodes: list[TargetNodeSpec] = field(default_factory=list)
    connections: list[TargetConnectionSpec] = field(default_factory=list)
    status: TranslationStatus = TranslationStatus.UNSUPPORTED
    diagnostics: list[Diagnostic] = field(default_factory=list)
    mapping: SourceMapping = field(default_factory=SourceMapping)


class TargetBackend(Protocol):
    """Generate a native procedural system from an IR graph."""

    name: str
    capabilities: CapabilitySet

    def translate_node(self, node: IRNode) -> GraphFragment:
        """Lower one IR node to a fragment of target nodes."""
        ...

    def generate(self, graph: IRGraph) -> str:
        """Return executable host-application script text."""
        ...


class UnimplementedBackend:
    """Placeholder used until a concrete backend is implemented."""

    name = "unimplemented"
    capabilities = CapabilitySet([TargetCapability.UNKNOWN])

    def translate_node(self, node: IRNode) -> GraphFragment:
        return GraphFragment(
            status=TranslationStatus.UNSUPPORTED,
            mapping=SourceMapping(ir_node_id=node.id),
        )

    def generate(self, graph: IRGraph) -> str:
        raise BackendError(
            f"{self.__class__.__name__} is not implemented. Use a concrete host backend."
        )
