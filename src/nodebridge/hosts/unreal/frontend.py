"""Unreal PCG frontend."""

from __future__ import annotations

from typing import Any

from nodebridge.core.exceptions import FrontendError
from nodebridge.hosts.extract import extract_native
from nodebridge.hosts.native import NativeGraph
from nodebridge.hosts.unreal.mappings import resolve_unreal_node
from nodebridge.ir.schema import IRDocument


class UnrealFrontend:
    """Inspect a PCG graph (or NativeGraph fixture) and emit IR."""

    application = "unreal"

    def extract(self, source: Any) -> IRDocument:
        native = coerce_unreal_source(source)
        return extract_native(
            native,
            resolve=resolve_unreal_node,
            application="unreal",
            graph_system="pcg",
        )


def coerce_unreal_source(source: Any) -> NativeGraph:
    if isinstance(source, NativeGraph):
        return source
    if isinstance(source, dict):
        if "graph" in source and "ir_version" in source:
            raise FrontendError(
                "Unreal frontend expected a native PCG graph, not a NodeBridge IR document"
            )
        return NativeGraph.from_dict(source)
    from nodebridge.hosts.unreal.runtime import native_from_unreal

    try:
        return native_from_unreal(source)
    except FrontendError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FrontendError(
            "Unreal frontend could not inspect the provided source. "
            "Pass a NativeGraph fixture when Unreal Python is unavailable."
        ) from exc
