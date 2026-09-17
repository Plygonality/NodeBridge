"""High-level export façade."""

from __future__ import annotations

from pathlib import Path

from nodebridge.compiler.pipeline import compile_graph
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
    """Generate a host script. Explicit stage — never runs on IR load."""
    graph = document.graph if isinstance(document, IRDocument) else document
    result = compile_graph(graph, target, generate=True)
    path = Path(destination)
    path.write_text(result.generated_code, encoding="utf-8")
    return path
