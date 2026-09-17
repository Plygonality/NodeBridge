"""Geometry Nodes extraction helpers."""

from nodebridge.hosts.blender.frontend import BlenderFrontend
from nodebridge.hosts.native import NativeGraph
from nodebridge.ir.schema import IRDocument


def extract_geometry_nodes(source: object) -> IRDocument:
    """Extract Geometry Nodes from a NativeGraph, dict, or duck-typed tree."""
    if not isinstance(source, (NativeGraph, dict)) and not hasattr(source, "nodes"):
        from nodebridge.core.exceptions import AdapterError

        raise AdapterError("Geometry Nodes extraction requires a native graph or bpy tree")
    return BlenderFrontend().extract(source)
