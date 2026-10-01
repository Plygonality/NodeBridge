"""Source frontend contract.

Blender is the only UI source today. A future Houdini or Unreal frontend
implements the same method and returns graph IR, not a target script.
"""

from __future__ import annotations

from typing import Any, Protocol

from nodebridge.ir.graph_ir import NodeTree


class SourceFrontend(Protocol):
    """Read a host graph into DCC-independent graph IR."""

    application: str

    def parse(self, source: Any, *, system: str | None = None) -> NodeTree:
        """Return a :class:`NodeTree`. Do not lower to a target DCC here."""
        ...
