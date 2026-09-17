"""Houdini SOP frontend."""

from __future__ import annotations

from typing import Any

from nodebridge.core.exceptions import FrontendError
from nodebridge.hosts.extract import extract_native
from nodebridge.hosts.houdini.mappings import resolve_houdini_node
from nodebridge.hosts.native import NativeGraph
from nodebridge.ir.schema import IRDocument


class HoudiniFrontend:
    """Inspect a SOP network (or NativeGraph fixture) and emit IR."""

    application = "houdini"

    def extract(self, source: Any) -> IRDocument:
        native = coerce_houdini_source(source)
        return extract_native(
            native,
            resolve=resolve_houdini_node,
            application="houdini",
            graph_system="sop",
        )


def coerce_houdini_source(source: Any) -> NativeGraph:
    if isinstance(source, NativeGraph):
        return source
    if isinstance(source, dict):
        if "graph" in source and "ir_version" in source:
            raise FrontendError(
                "Houdini frontend expected a native SOP graph, not a NodeBridge IR document"
            )
        return NativeGraph.from_dict(source)
    from nodebridge.hosts.houdini.runtime import native_from_hou

    try:
        return native_from_hou(source)
    except FrontendError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FrontendError(
            "Houdini frontend could not inspect the provided source. "
            "Pass a NativeGraph fixture when hou is unavailable."
        ) from exc
