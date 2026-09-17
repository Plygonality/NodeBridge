"""Optional Unreal Python bridge.

The PCG Python API is experimental (UE 5.7+). Construction and inspection
are editor-only. This module never runs at import time and uses importlib.
"""

from __future__ import annotations

import importlib
from typing import Any

from nodebridge.core.exceptions import FrontendError
from nodebridge.hosts.native import NativeGraph, NativeLink, NativeNode, NativeSocket


def load_unreal() -> Any:
    try:
        return importlib.import_module("unreal")
    except ImportError as extra:
        raise FrontendError("unreal is not available in this Python environment") from extra


def native_from_unreal(graph: Any) -> NativeGraph:
    """Inspect a PCG graph or a duck-typed stand-in.

    Documented UE 5.7 APIs used when present: ``graph.nodes``,
    ``node.get_settings()``, ``get_input_node()``, ``get_output_node()``.
    Pin-edge traversal is incomplete in the public Python API; links may
    be empty unless the object already exposes them.
    """
    nodes_attr = getattr(graph, "nodes", None)
    if nodes_attr is None:
        raise FrontendError("Unreal source has no nodes collection")
    native_nodes: list[NativeNode] = []
    for node in list(nodes_attr):
        settings = None
        getter = getattr(node, "get_settings", None)
        if callable(getter):
            try:
                settings = getter()
            except Exception:  # noqa: BLE001
                settings = None
        type_name = type(settings).__name__ if settings is not None else str(
            getattr(node, "node_title", None) or getattr(node, "type", "PCGNode")
        )
        identifier = str(getattr(node, "node_title", None) or getattr(node, "name", type_name))
        native_nodes.append(
            NativeNode(
                id=_safe(identifier),
                type=type_name,
                name=identifier,
                inputs=[NativeSocket(name="In")],
                outputs=[NativeSocket(name="Out")],
            )
        )
    name = str(getattr(graph, "get_name", lambda: "PCG")() if callable(getattr(graph, "get_name", None)) else getattr(graph, "name", "PCG"))
    return NativeGraph(
        host="unreal",
        system="pcg",
        name=name,
        nodes=native_nodes,
        links=[],
        metadata={
            "api": "experimental-ue5.7",
            "link_inspection": "limited",
        },
    )


def _safe(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "_.-" else "_" for ch in str(value))
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"n_{cleaned}"
    return cleaned
