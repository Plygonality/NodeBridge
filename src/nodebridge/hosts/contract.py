"""Host plugin contract.

Adding a DCC should mean implementing this contract and registering the
host. Core compiler modules must not grow ``if host == ...`` branches.

Each host may provide a frontend (native → IR), a backend (IR → native),
or both.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from nodebridge.core.capabilities import CapabilitySet
from nodebridge.core.diagnostics import TranslationStatus
from nodebridge.core.graph import IRGraph
from nodebridge.core.node import IRNode
from nodebridge.hosts.native import NativeGraph, NativeLink, NativeNode
from nodebridge.ir.schema import IRDocument


@dataclass(frozen=True)
class Implementation:
    """How a host realizes one semantic operation."""

    operation: str
    fidelity: TranslationStatus
    recipe: str = ""
    note: str = ""
    code_kind: str = ""
    code: str = ""
    available: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "fidelity": self.fidelity.value,
            "recipe": self.recipe,
            "note": self.note,
            "code_kind": self.code_kind,
            "available": self.available,
        }


class HostFrontend(Protocol):
    """Extract canonical IR from a host-native graph."""

    application: str

    def extract(self, source: Any) -> IRDocument:
        """Inspect *source* (NativeGraph, dict, or host object) and emit IR."""
        ...


class HostBackend(Protocol):
    """Generate a host-native construction plan from canonical IR."""

    name: str
    capabilities: CapabilitySet

    def implementation_for(self, operation: str) -> Implementation:
        """Describe how *operation* would be realized."""
        ...

    def lower_node(self, node: IRNode) -> "LoweringFragment":
        """Lower one IR node to a native fragment (one-to-many allowed)."""
        ...

    def build(self, graph: IRGraph) -> NativeGraph:
        """Assemble a native construction plan for *graph*."""
        ...

    def generate(self, graph: IRGraph) -> str:
        """Return host-script text. Loading IR must never execute this."""
        ...


@dataclass
class LoweringFragment:
    """One IR operation realized as zero or more native nodes."""

    nodes: list[NativeNode] = field(default_factory=list)
    links: list[NativeLink] = field(default_factory=list)
    inputs: dict[str, tuple[str, str]] = field(default_factory=dict)
    outputs: dict[str, tuple[str, str]] = field(default_factory=dict)
    fidelity: TranslationStatus = TranslationStatus.UNSUPPORTED
    note: str = ""
    recipe: str = ""
    code_kind: str = ""
    code: str = ""


class HostPlugin(Protocol):
    """Registered DCC or engine integration."""

    id: str
    display_name: str
    versions: tuple[str, ...]
    graph_systems: tuple[str, ...]
    capabilities: CapabilitySet
    frontend: HostFrontend
    backend: HostBackend

    def implementation_for(self, operation: str) -> Implementation:
        """Ask whether this host can implement *operation*, and how."""
        ...
