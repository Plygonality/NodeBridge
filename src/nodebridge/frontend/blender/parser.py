"""Parse Blender node trees into graph IR.

The parser accepts live ``bpy`` node trees and duck-typed stand-ins with
``nodes`` and ``links``. It does not import ``bpy``. Nested node groups are
parsed recursively and kept as child trees.
"""

from __future__ import annotations

from typing import Any

from nodebridge.frontend.base import SourceFrontend
from nodebridge.ir.graph_ir import GraphEdge, GraphNode, GraphSocket, NodeParameter, NodeTree

_GROUP_TYPES = {
    "GeometryNodeGroup",
    "ShaderNodeGroup",
    "CompositorNodeGroup",
    "NodeGroup",
}
_PARAM_ATTRS = (
    "operation",
    "data_type",
    "domain",
    "mode",
    "blend_type",
    "distribute_method",
    "use_clamp",
    "interpolation_type",
    "clamp_result",
    "noise_dimensions",
    "musgrave_type",
    "component",
)
_REFERENCE_ATTRS = ("object", "collection", "material", "image")
_SYSTEM_BY_TREE = {
    "GeometryNodeTree": "geometry_nodes",
    "ShaderNodeTree": "shader",
    "CompositorNodeTree": "compositor",
}


class BlenderFrontend:
    """:class:`SourceFrontend` for Blender node trees."""

    application = "blender"

    def parse(self, source: Any, *, system: str | None = None) -> NodeTree:
        return parse_node_tree(source, system=system)


def parse_node_tree(tree: Any, *, system: str | None = None, _seen: set[int] | None = None) -> NodeTree:
    """Parse one node tree and any nested groups."""
    nodes_attr = getattr(tree, "nodes", None)
    links_attr = getattr(tree, "links", None)
    if nodes_attr is None or links_attr is None:
        raise ValueError("Blender source has no nodes/links collections")
    seen = set() if _seen is None else _seen
    identity = id(tree)
    tree_type = str(getattr(tree, "bl_idname", "") or "")
    resolved = system or _SYSTEM_BY_TREE.get(tree_type, "geometry_nodes")
    name = str(getattr(tree, "name", None) or "NodeTree")
    tree_id = _identifier(name, fallback="tree")
    if identity in seen:
        return NodeTree(id=tree_id, name=name, system=resolved, metadata={"recursive": True})
    seen.add(identity)

    node_tree = NodeTree(id=tree_id, name=name, system=resolved)
    node_tree.interface_inputs, node_tree.interface_outputs = _interface(tree)
    index = 0
    for node in nodes_attr:
        index += 1
        parsed = _node(node, index)
        if parsed is None:
            continue
        if parsed.type_name in _GROUP_TYPES:
            child_source = getattr(node, "node_tree", None)
            if child_source is not None and id(child_source) not in seen:
                child = parse_node_tree(child_source, _seen=seen)
                node_tree.groups[child.id] = child
                parsed.nested_tree_id = child.id
                parsed.parameters.append(NodeParameter("nested_graph_id", child.id, "string"))
        node_tree.nodes[parsed.id] = parsed

    edge_index = 0
    for link in links_attr:
        edge_index += 1
        edge = _edge(link, edge_index, node_tree)
        if edge is not None:
            node_tree.edges.append(edge)
    return node_tree


def _node(node: Any, index: int) -> GraphNode | None:
    type_name = str(getattr(node, "bl_idname", "") or getattr(node, "type", "") or "")
    if not type_name:
        return None
    raw_name = str(getattr(node, "name", "") or f"Node_{index}")
    node_id = _identifier(raw_name, fallback=f"node_{index}")
    location = getattr(node, "location", None)
    parsed_location = None
    if location is not None and len(location) >= 2:
        parsed_location = (float(location[0]), float(location[1]))
    graph_node = GraphNode(
        id=node_id,
        type_name=type_name,
        name=raw_name,
        label=str(getattr(node, "label", "") or ""),
        inputs=_sockets(getattr(node, "inputs", []), "input"),
        outputs=_sockets(getattr(node, "outputs", []), "output"),
        parameters=_parameters(node),
        location=parsed_location,
        muted=bool(getattr(node, "mute", False)),
    )
    return graph_node


def _sockets(items: Any, direction: str) -> list[GraphSocket]:
    sockets: list[GraphSocket] = []
    for item in items:
        name = str(getattr(item, "name", "") or "")
        if not name:
            continue
        default = getattr(item, "default_value", None)
        if hasattr(default, "name") and not isinstance(default, (str, bytes)):
            default = str(default.name)
        elif hasattr(default, "__iter__") and not isinstance(default, (str, bytes)):
            try:
                default = [float(component) for component in default]
            except (TypeError, ValueError):
                default = None
        elif isinstance(default, (bool, int, float, str)) or default is None:
            pass
        else:
            default = None
        data_type = str(getattr(item, "bl_idname", "") or getattr(item, "type", "") or "unknown")
        sockets.append(GraphSocket(name=name, direction=direction, data_type=data_type, default=default))
    return sockets


def _parameters(node: Any) -> list[NodeParameter]:
    parameters: list[NodeParameter] = []
    for attr in _PARAM_ATTRS:
        if not hasattr(node, attr):
            continue
        value = getattr(node, attr)
        if isinstance(value, (bool, int, float, str)):
            parameters.append(NodeParameter(attr, value))
    for attr in _REFERENCE_ATTRS:
        value = getattr(node, attr, None)
        if value is None:
            continue
        name = getattr(value, "name", None)
        if isinstance(name, str) and name:
            parameters.append(NodeParameter(attr, name, "reference"))
    return parameters


def _interface(tree: Any) -> tuple[list[GraphSocket], list[GraphSocket]]:
    inputs: list[GraphSocket] = []
    outputs: list[GraphSocket] = []
    interface = getattr(tree, "interface", None)
    items = getattr(interface, "items_tree", None) if interface is not None else None
    if items is not None:
        for item in items:
            if str(getattr(item, "item_type", "") or "") not in {"SOCKET", ""}:
                if getattr(item, "socket_type", None) is None and getattr(item, "in_out", None) is None:
                    continue
            if getattr(item, "in_out", None) is None and getattr(item, "socket_type", None) is None:
                continue
            direction = str(getattr(item, "in_out", "") or "")
            socket = GraphSocket(
                name=str(getattr(item, "name", "") or "Socket"),
                direction="input" if direction.upper().startswith("IN") else "output",
                data_type=str(getattr(item, "socket_type", "") or "unknown"),
                default=_plain(getattr(item, "default_value", None)),
            )
            if socket.direction == "input":
                inputs.append(socket)
            else:
                outputs.append(socket)
        if inputs or outputs:
            return inputs, outputs
    for item in getattr(tree, "inputs", []) or []:
        name = str(getattr(item, "name", "") or "")
        if name:
            inputs.append(GraphSocket(name=name, direction="input", data_type=str(getattr(item, "bl_idname", "") or "unknown")))
    for item in getattr(tree, "outputs", []) or []:
        name = str(getattr(item, "name", "") or "")
        if name:
            outputs.append(
                GraphSocket(name=name, direction="output", data_type=str(getattr(item, "bl_idname", "") or "unknown"))
            )
    return inputs, outputs


def _edge(link: Any, index: int, tree: NodeTree) -> GraphEdge | None:
    source = getattr(link, "from_node", None)
    target = getattr(link, "to_node", None)
    source_socket = getattr(link, "from_socket", None)
    target_socket = getattr(link, "to_socket", None)
    if source is None or target is None:
        return None
    source_id = _identifier(str(getattr(source, "name", "") or ""), fallback="")
    target_id = _identifier(str(getattr(target, "name", "") or ""), fallback="")
    if source_id not in tree.nodes or target_id not in tree.nodes:
        return None
    return GraphEdge(
        id=f"edge_{index}",
        source_node=source_id,
        source_socket=str(getattr(source_socket, "name", "") or "Geometry"),
        target_node=target_id,
        target_socket=str(getattr(target_socket, "name", "") or "Geometry"),
    )


def _plain(value: Any) -> Any:
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    if hasattr(value, "__iter__") and not isinstance(value, (str, bytes)):
        try:
            return [float(component) for component in value]
        except (TypeError, ValueError):
            return None
    return None


def _identifier(value: str, *, fallback: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in "_.-" else "_" for character in value)
    cleaned = cleaned.strip("_.-")
    if not cleaned:
        cleaned = fallback
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"n_{cleaned}" if cleaned else fallback
    return cleaned
