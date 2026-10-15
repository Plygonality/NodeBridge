"""Source frontend contract.

A frontend reads a native graph and lowers it to semantic IR. Blender is the
first frontend. A later Houdini or Unreal frontend would implement the same
methods and register a new id. The compiler does not import a DCC to do that.
"""

from __future__ import annotations

from typing import Any, Protocol

from nodebridge.ir.graph import GraphSystem, NodeTree
from nodebridge.ir.semantic import SemanticGraph


class SourceFrontend(Protocol):
    """Parse a native graph and lower the graph IR to semantic operations."""

    id: str

    def parse(self, source: Any, *, system: GraphSystem | None = None) -> NodeTree:
        """Read ``source`` into graph IR."""

    def lower(self, tree: NodeTree) -> SemanticGraph:
        """Turn graph IR into semantic IR."""
