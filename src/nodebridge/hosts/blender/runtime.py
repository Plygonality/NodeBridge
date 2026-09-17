"""Optional bpy bridge. Never imported by core or the compiler.

Uses importlib so the rest of NodeBridge stays installable without Blender.
Duck-typed objects with ``nodes`` / ``links`` / ``bl_idname`` are accepted
so tests can exercise extraction without bpy.
"""

from __future__ import annotations

import importlib
from typing import Any

from nodebridge.core.exceptions import FrontendError, BackendError
from nodebridge.hosts.native import NativeGraph, NativeLink, NativeNode, NativeSocket


def load_bpy() -> Any:
    """Import bpy if the Blender Python API is available."""
    try:
        return importlib.import_module("bpy")
    except ImportError as exc:
        raise FrontendError("bpy is not available in this Python environment") from exc



def native_from_bpy(tree: Any) -> NativeGraph:
    """Inspect a Geometry Node tree or a duck-typed stand-in."""
    nodes_attr = getattr(tree, "nodes", None)
    links_attr = getattr(tree, "links", None)
    if nodes_attr is None or links_attr is None:
        raise FrontendError("Blender source has no nodes/links collections")
    native_nodes: list[NativeNode] = []
    for node in nodes_attr:
        bl_idname = str(getattr(node, "bl_idname", "") or getattr(node, "type", "") or "")
        if not bl_idname:
            continue
        identifier = str(getattr(node, "name", None) or getattr(node, "identifier", "") or bl_idname)
        location = getattr(node, "location", None)
        position = None
        if location is not None and len(location) >= 2:
            position = (float(location[0]), float(location[1]))
        native_nodes.append(
            NativeNode(
                id=_safe(identifier),
                type=bl_idname,
                name=str(getattr(node, "label", "") or identifier),
                inputs=_sockets(getattr(node, "inputs", [])),
                outputs=_sockets(getattr(node, "outputs", [])),
                parameters=_parameters(node),
                position=position,
            )
        )
    native_links: list[NativeLink] = []
    for link in links_attr:
        from_node = getattr(link, "from_node", None)
        to_node = getattr(link, "to_node", None)
        from_socket = getattr(link, "from_socket", None)
        to_socket = getattr(link, "to_socket", None)
        if from_node is None or to_node is None:
            continue
        native_links.append(
            NativeLink(
                source_node=_safe(str(getattr(from_node, "name", "unknown"))),
                source_socket=str(getattr(from_socket, "name", "Geometry")),
                target_node=_safe(str(getattr(to_node, "name", "unknown"))),
                target_socket=str(getattr(to_socket, "name", "Geometry")),
            )
        )
    name = str(getattr(tree, "name", "Geometry Nodes"))
    return NativeGraph(
        host="blender",
        system="geometry_nodes",
        name=name,
        nodes=native_nodes,
        links=native_links,
    )


def apply_native_with_bpy(native: NativeGraph, tree: Any | None = None) -> Any:
    """Create Geometry Nodes on an existing or new bpy node tree.

    This is an explicit execution stage. Loading IR never calls it.
    """
    bpy = load_bpy()
    if tree is None:
        tree = bpy.data.node_groups.new(native.name or "NodeBridge", "GeometryNodeTree")
        if hasattr(tree, "interface"):
            pass
    raise BackendError(
        "Live bpy graph mutation is available only inside Blender. "
        "Use BlenderBackend.build() for a construction plan, or "
        "BlenderBackend.generate() for a bpy script."
    )


def _sockets(items: Any) -> list[NativeSocket]:
    result: list[NativeSocket] = []
    for item in items:
        name = str(getattr(item, "name", "") or "")
        if not name:
            continue
        default = getattr(item, "default_value", None)
        if hasattr(default, "__iter__") and not isinstance(default, (str, bytes)):
            try:
                default = [float(component) for component in default]
            except (TypeError, ValueError):
                default = None
        identifier = str(getattr(item, "bl_idname", "") or getattr(item, "type", "unknown"))
        result.append(NativeSocket(name=name, data_type=identifier, default=default))
    return result


def _parameters(node: Any) -> dict[str, Any]:
    skip = {
        "name",
        "label",
        "location",
        "inputs",
        "outputs",
        "bl_idname",
        "type",
        "select",
        "dimensions",
        "width",
        "height",
        "internal_links",
    }
    values: dict[str, Any] = {}
    for attr in ("operation", "data_type", "domain", "mode", "use_clamp", "density", "seed"):
        if hasattr(node, attr):
            value = getattr(node, attr)
            if _is_jsonish(value):
                values[attr] = value
    for attr in dir(node):
        if attr.startswith("_") or attr in skip or attr in values:
            continue
        if attr in {"bl_rna", "rna_type", "id_data"}:
            continue
        try:
            value = getattr(node, attr)
        except Exception:  # noqa: BLE001
            continue
        if callable(value) or not _is_jsonish(value):
            continue
        if attr in {"hide", "mute", "show_texture"}:
            continue
    return values


def _is_jsonish(value: Any) -> bool:
    return value is None or isinstance(value, (bool, int, float, str, list, tuple, dict))


def _safe(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "_.-" else "_" for ch in value)
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"n_{cleaned}"
    return cleaned
