"""Optional hou bridge. Never imported by core.

Uses importlib so NodeBridge stays installable without Houdini. Duck-typed
objects with ``children`` / ``type`` / ``inputs`` are accepted in tests.
"""

from __future__ import annotations

import importlib
from typing import Any

from nodebridge.core.exceptions import FrontendError
from nodebridge.hosts.native import NativeGraph, NativeLink, NativeNode, NativeSocket


def load_hou() -> Any:
    try:
        return importlib.import_module("hou")
    except ImportError as exc:
        raise FrontendError("hou is not available in this Python environment") from exc


def native_from_hou(network: Any) -> NativeGraph:
    """Inspect a SOP network or a duck-typed stand-in."""
    children = getattr(network, "children", None)
    if callable(children):
        nodes = list(children())
    elif children is not None:
        nodes = list(children)
    else:
        raise FrontendError("Houdini source has no children() network")
    native_nodes: list[NativeNode] = []
    native_links: list[NativeLink] = []
    for node in nodes:
        node_type = getattr(node, "type", None)
        type_name = str(
            getattr(node_type, "name", lambda: getattr(node, "type_name", "null"))()
            if callable(getattr(node_type, "name", None))
            else getattr(node, "type_name", None) or getattr(node_type, "name", "null")
        )
        identifier = str(getattr(node, "name", lambda: "node")() if callable(getattr(node, "name", None)) else getattr(node, "name", "node"))
        native_nodes.append(
            NativeNode(
                id=_safe(identifier),
                type=type_name,
                name=identifier,
                inputs=[NativeSocket(name="input0")],
                outputs=[NativeSocket(name="output0")],
                parameters=_parameters(node),
            )
        )
        inputs = getattr(node, "inputs", None)
        connected = list(inputs()) if callable(inputs) else list(inputs or [])
        for index, source in enumerate(connected):
            if source is None:
                continue
            source_name = str(
                getattr(source, "name", lambda: "src")()
                if callable(getattr(source, "name", None))
                else getattr(source, "name", "src")
            )
            native_links.append(
                NativeLink(
                    source_node=_safe(source_name),
                    source_socket="output0",
                    target_node=_safe(identifier),
                    target_socket="input0" if index == 0 else f"input{index}",
                )
            )
    name = str(
        getattr(network, "name", lambda: "sop")()
        if callable(getattr(network, "name", None))
        else getattr(network, "name", "sop")
    )
    return NativeGraph(host="houdini", system="sop", name=name, nodes=native_nodes, links=native_links)


def _parameters(node: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    parms = getattr(node, "parms", None)
    items = list(parms()) if callable(parms) else []
    for parm in items:
        name = str(getattr(parm, "name", lambda: "")() if callable(getattr(parm, "name", None)) else getattr(parm, "name", ""))
        eval_fn = getattr(parm, "eval", None)
        value = eval_fn() if callable(eval_fn) else getattr(parm, "value", None)
        if name and _is_jsonish(value):
            values[name] = value
    return values


def _is_jsonish(value: Any) -> bool:
    return value is None or isinstance(value, (bool, int, float, str, list, tuple, dict))


def _safe(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "_.-" else "_" for ch in value)
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"n_{cleaned}"
    return cleaned
