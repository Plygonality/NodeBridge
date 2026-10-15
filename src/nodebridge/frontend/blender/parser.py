"""Blender ``bpy`` node tree -> Graph IR.

The parser reads real Blender data (verified on Blender 4.2 LTS and 4.5
LTS) but never imports ``bpy`` itself: it only uses attributes of the
objects it is given, so the compiler stays importable outside Blender.

Captured per tree: nodes, sockets (identifier, name, type, subtype,
default, enabled state), links (with Blender's validity / mute flags),
node properties (enums, numbers, ID references, color ramps), mute
internal links, group tree references (recursively), the group interface
and, for Geometry Nodes modifiers, the modifier's current input values.
"""

from __future__ import annotations

from typing import Any, Iterable

from ...ir.graph import GraphDocument, GraphEdge, GraphNode, GraphSocket, InterfaceSocket, NodeTree, TreeKind
from ...ir.types import blender_interface_type, blender_socket_type

TREE_KINDS = {
    "GeometryNodeTree": TreeKind.GEOMETRY,
    "ShaderNodeTree": TreeKind.SHADER,
    "CompositorNodeTree": TreeKind.COMPOSITOR,
}

BASE_NODE_PROPERTIES = {
    "rna_type", "type", "location", "location_absolute", "width", "width_hidden", "height", "dimensions", "name",
    "label", "inputs", "outputs", "internal_links", "parent", "warning_propagation", "use_custom_color", "color",
    "color_tag", "select", "show_options", "show_preview", "hide", "mute", "show_texture", "bl_idname", "bl_label",
    "bl_description", "bl_icon", "bl_static_type", "bl_width_default", "bl_width_min", "bl_width_max",
    "bl_height_default", "bl_height_min", "bl_height_max", "texture_mapping", "color_mapping", "image_user",
    "paired_output", "active_item", "active_index", "inspection_index", "repeat_items", "state_items",
    "capture_items", "bake_items", "enum_items", "format_items",
}
SKIP_INPUT_IDENTIFIERS = {"__extend__"}


def tree_kind(tree: Any) -> TreeKind:
    bl_idname = getattr(tree, "bl_idname", "")
    if bl_idname not in TREE_KINDS:
        raise ValueError(f"Unsupported node tree type {bl_idname!r}")
    return TREE_KINDS[bl_idname]


def plain(value: Any, depth: int = 0) -> Any:
    """Convert bpy / mathutils values into JSON-friendly Python values."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if _is_id(value):
        result = {"id_type": type(value).__name__, "name": value.name}
        filepath = getattr(value, "filepath", None)
        if isinstance(filepath, str) and filepath:
            result["filepath"] = filepath
        return result
    if depth < 3 and hasattr(value, "__len__") and hasattr(value, "__getitem__"):
        try:
            return [plain(item, depth + 1) for item in value]
        except TypeError:
            return None
    return None


def _is_id(value: Any) -> bool:
    rna = getattr(value, "bl_rna", None)
    if rna is None:
        return False
    base = getattr(rna, "base", None)
    while base is not None:
        if getattr(base, "identifier", "") == "ID":
            return True
        base = getattr(base, "base", None)
    return False


def _socket(socket: Any, is_output: bool) -> GraphSocket:
    bl_idname = getattr(socket, "bl_idname", "")
    subtype = ""
    for marker in ("Distance", "Angle", "Factor", "Percentage", "Translation", "Euler", "Direction", "XYZ", "Velocity", "Time"):
        if marker in bl_idname:
            subtype = marker.upper()
            break
    default = plain(getattr(socket, "default_value", None)) if hasattr(socket, "default_value") else None
    return GraphSocket(
        identifier=socket.identifier,
        name=socket.name,
        data_type=blender_socket_type(getattr(socket, "type", "")),
        is_output=is_output,
        subtype=subtype,
        default=default,
        enabled=bool(getattr(socket, "enabled", True)) and not bool(getattr(socket, "is_unavailable", False)),
        linked=bool(getattr(socket, "is_linked", False)),
    )


def _color_ramp(ramp: Any) -> dict:
    return {
        "interpolation": getattr(ramp, "interpolation", "LINEAR"),
        "color_mode": getattr(ramp, "color_mode", "RGB"),
        "elements": [[round(float(e.position), 6), plain(e.color)] for e in ramp.elements],
    }


def _node_parameters(node: Any) -> dict:
    params: dict[str, Any] = {}
    rna = getattr(node, "bl_rna", None)
    props: Iterable[Any] = rna.properties if rna is not None else ()
    for prop in props:
        key = prop.identifier
        if key in BASE_NODE_PROPERTIES or key.startswith("bl_"):
            continue
        try:
            value = getattr(node, key)
        except Exception:  # noqa: BLE001 - some RNA properties raise in background mode
            continue
        if key == "color_ramp" and value is not None:
            params[key] = _color_ramp(value)
            continue
        if prop.type == "POINTER":
            if _is_id(value):
                params[key] = plain(value)
            elif value is None and key in ("node_tree", "object", "image", "material", "scene", "collection"):
                params[key] = None
            continue
        if prop.type == "COLLECTION":
            continue
        converted = plain(value)
        if converted is not None or value is None:
            params[key] = converted
    if hasattr(node, "is_active_output"):
        params["is_active_output"] = bool(node.is_active_output)
    return params


def parse_tree(tree: Any, *, name: str | None = None, is_group: bool = False) -> NodeTree:
    kind = tree_kind(tree)
    result = NodeTree(name=name or tree.name, kind=kind, is_group=is_group, metadata={"blender_name": tree.name})
    for node in tree.nodes:
        if node.bl_idname == "NodeFrame":
            continue
        group = getattr(node, "node_tree", None) if node.bl_idname.endswith("Group") else None
        params = _node_parameters(node)
        params.pop("node_tree", None)
        result.add(
            GraphNode(
                id=node.name,
                type=node.bl_idname,
                name=node.name,
                label=node.label or "",
                inputs=[_socket(s, False) for s in node.inputs if s.identifier not in SKIP_INPUT_IDENTIFIERS],
                outputs=[_socket(s, True) for s in node.outputs if s.identifier not in SKIP_INPUT_IDENTIFIERS],
                parameters=params,
                muted=bool(getattr(node, "mute", False)),
                group_tree=group.name if group is not None else None,
                internal_links=[(l.from_socket.identifier, l.to_socket.identifier) for l in getattr(node, "internal_links", [])],
                location=(round(float(node.location[0]), 1), round(float(node.location[1]), 1)),
            )
        )
    for link in tree.links:
        if link.from_node.bl_idname == "NodeFrame" or link.to_node.bl_idname == "NodeFrame":
            continue
        if link.to_socket.identifier in SKIP_INPUT_IDENTIFIERS or link.from_socket.identifier in SKIP_INPUT_IDENTIFIERS:
            continue
        result.edges.append(
            GraphEdge(
                link.from_node.name,
                link.from_socket.identifier,
                link.to_node.name,
                link.to_socket.identifier,
                muted=bool(getattr(link, "is_muted", False)),
                valid=bool(getattr(link, "is_valid", True)),
            )
        )
    result.interface = list(_interface(tree))
    return result


def _interface(tree: Any) -> Iterable[InterfaceSocket]:
    interface = getattr(tree, "interface", None)
    if interface is None:
        return
    for item in interface.items_tree:
        if getattr(item, "item_type", "") != "SOCKET":
            continue
        yield InterfaceSocket(
            identifier=item.identifier,
            name=item.name,
            in_out=item.in_out,
            data_type=blender_interface_type(getattr(item, "socket_type", "") or getattr(item, "bl_socket_idname", "")),
            subtype=str(getattr(item, "subtype", "") or "").replace("NONE", ""),
            default=plain(getattr(item, "default_value", None)) if hasattr(item, "default_value") else None,
            min_value=plain(getattr(item, "min_value", None)) if hasattr(item, "min_value") else None,
            max_value=plain(getattr(item, "max_value", None)) if hasattr(item, "max_value") else None,
            description=getattr(item, "description", "") or "",
        )


def _collect_groups(tree: Any, found: dict[str, Any]) -> None:
    for node in tree.nodes:
        group = getattr(node, "node_tree", None) if node.bl_idname.endswith("Group") else None
        if group is not None and group.name not in found:
            found[group.name] = group
            _collect_groups(group, found)


def parse_document(tree: Any, *, root_name: str | None = None, source: dict | None = None, modifier: Any = None) -> GraphDocument:
    """Parse ``tree`` and every node group it uses, recursively."""
    root_name = root_name or tree.name
    root = parse_tree(tree, name=root_name, is_group=False)
    groups: dict[str, Any] = {}
    _collect_groups(tree, groups)
    document = GraphDocument(root=root_name, trees={root_name: root}, source=dict(source or {}))
    for name, group in groups.items():
        if name == root_name:
            continue
        document.trees[name] = parse_tree(group, name=name, is_group=True)
    if modifier is not None:
        apply_modifier_values(root, modifier)
    document.source.setdefault("tree_kind", root.kind.value)
    document.source.setdefault("tree", tree.name)
    return document


def apply_modifier_values(tree: NodeTree, modifier: Any) -> None:
    """Record a Geometry Nodes modifier's current inputs as interface values."""
    for socket in tree.inputs:
        try:
            value = modifier[socket.identifier]
        except (KeyError, TypeError):
            continue
        socket.value = plain(value)
