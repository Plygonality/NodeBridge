"""High-level export façade.

Milestone 1 can write IR JSON. Target-script generation is later.
"""

from __future__ import annotations

from pathlib import Path

from nodebridge.core.exceptions import BackendError
from nodebridge.core.graph import IRGraph
from nodebridge.ir.schema import IRDocument
from nodebridge.ir.serializer import dump


def export_ir(document: IRDocument | IRGraph, destination: str | Path) -> Path:
    """Serialize *document* to *destination* as versioned JSON."""
    path = Path(destination)
    dump(document, path)
    return path


def export_target_script(
    document: IRDocument | IRGraph,
    target: str,
    destination: str | Path,
) -> Path:
    """Generate a host script. Not implemented in Milestone 1."""
    raise BackendError(
        f"Target export for {target!r} is not implemented in Milestone 1. "
        "Use export_ir() to write a .nodebridge.json document."
    )
