"""IR cloning via serialization so passes never mutate the caller's graph."""

from __future__ import annotations

from nodebridge.core.graph import IRGraph
from nodebridge.ir.deserializer import loads
from nodebridge.ir.serializer import dumps


def clone_graph(graph: IRGraph) -> IRGraph:
    """Return a deep copy of *graph* with the same ids and values."""
    return loads(dumps(graph)).graph
