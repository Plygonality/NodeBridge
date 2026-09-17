"""Blender Geometry Nodes frontend.

Extracts a native Geometry Nodes description into canonical IR. Live ``bpy``
inspection lives in :mod:`nodebridge.hosts.blender.runtime` and is optional.
"""

from __future__ import annotations

from typing import Any

from nodebridge.core.exceptions import FrontendError
from nodebridge.hosts.blender.mappings import resolve_blender_node
from nodebridge.hosts.extract import extract_native
from nodebridge.hosts.native import NativeGraph
from nodebridge.ir.schema import IRDocument


class BlenderFrontend:
    """Inspect Geometry Nodes (or a NativeGraph fixture) and emit IR."""

    application = "blender"

    def extract(self, source: Any) -> IRDocument:
        """Accept a :class:`NativeGraph`, a dict, or a duck-typed bpy tree."""
        native = coerce_blender_source(source)
        return extract_native(
            native,
            resolve=resolve_blender_node,
            application="blender",
            graph_system="geometry_nodes",
        )


def coerce_blender_source(source: Any) -> NativeGraph:
    """Normalize supported Blender frontend inputs to a NativeGraph."""
    if isinstance(source, NativeGraph):
        return source
    if isinstance(source, dict):
        if "graph" in source and "ir_version" in source:
            raise FrontendError(
                "Blender frontend expected a native Geometry Nodes graph, "
                "not a NodeBridge IR document"
            )
        return NativeGraph.from_dict(source)
    from nodebridge.hosts.blender.runtime import native_from_bpy

    try:
        return native_from_bpy(source)
    except FrontendError:
        raise
    except Exception as exc:  # noqa: BLE001 — host boundary
        raise FrontendError(
            "Blender frontend could not inspect the provided source. "
            "Pass a NativeGraph fixture when bpy is unavailable."
        ) from exc
