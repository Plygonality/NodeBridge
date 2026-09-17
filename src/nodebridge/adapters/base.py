"""Source-adapter contract.

Adapters extract a host application's node tree into NodeBridge IR.
They are the only modules allowed to import host SDKs such as ``bpy``.
"""

from __future__ import annotations

from typing import Any, Protocol

from nodebridge.core.exceptions import AdapterError
from nodebridge.core.graph import IRGraph
from nodebridge.ir.schema import IRDocument


class SourceAdapter(Protocol):
    """Extract an :class:`IRGraph` from a host application."""

    application: str

    def extract(self, source: Any) -> IRDocument:
        """Inspect *source* and return a versioned IR document."""
        ...


class UnimplementedAdapter:
    """Placeholder used until a concrete adapter is implemented."""

    application = "unknown"

    def extract(self, source: Any) -> IRDocument:
        raise AdapterError(
            f"{self.__class__.__name__} is not implemented. Use a concrete host frontend."
        )


def assert_no_host_imports() -> None:
    """Documentation helper: adapters isolate host imports from core."""
    raise AdapterError("Host SDK imports belong in adapter packages only")
