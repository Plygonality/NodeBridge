"""Parse a Blender node tree into graph IR.

The parser uses attribute access, so the same code reads a live ``bpy``
node tree and a duck-typed fixture. It does not evaluate the node tree and
it does not import ``bpy`` at module import time.
"""

from __future__ import annotations

from typing import Any

from nodebridge.common.names import unique_name
from nodebridge.frontend.blender.sockets import is_field_socket, pythonize, socket_data_type
from nodebridge.ir.graph import (
    GraphEdge,
    GraphNode,
    GraphSocket,
    GraphSystem,
    InterfaceSocket,
    NodeParameter,
    NodeTree,
    SocketDirection,
)
from nodebridge.ir.types import DataType, data_type_from_blender_socket

_PROPERTY_NAMES = (
    "operation",
    "distribute_method",
    "data_type",
    "mode",
    "domain",
    "noise_dimensions",
    "noise_type",
    "blend_type",
    "use_clamp",
    "clamp_result",
    "interpolation_type",
    "fill_type",
    "component",
    "input_type",
    "output_type",
    "mapping",
    "boolean_mode",
    "material_mode",
    "target_element",
    "data_type",
    "scatter_method",
)

_TREE_SYSTEMS = {
    "GeometryNodeTree": GraphSystem.GEOMETRY,
    "ShaderNodeTree": GraphSystem.SHADER,
    "CompositorNodeTree": GraphSystem.COMPOSITOR,
}

_GROUP_TYPES = {"GeometryNodeGroup", "ShaderNodeGroup", "CompositorNodeGroup"}


def system_for_tree_id(bl_idname: str | None) -> GraphSystem | None:
    if bl_idname is None:
        return None
    return _TREE_SYSTEMS.get(bl_idname)


def parse_blender_tree(source: Any, *, system: GraphSystem | None = None, _stack: tuple[int, ...] = ()) -> NodeTree:
    """Parse ``source`` as a node tree or a Geometry Nodes modifier."""

    modifier_name = None
    if _is_modifier(source):
        modifier_name = getattr(source, "name", None)
        group = getattr(source, "node_group", None)
        if group is None:
            raise ValueError("Geometry Nodes modifier has no node group")
        tree = parse_blender_tree(group, system=GraphSystem.GEOMETRY, _stack=_stack)
        _apply_modifier_values(source, tree)
        tree.metadata["modifier"] = modifier_name
        owner = getattr(source, "id_data", None)
        if owner is not None and getattr(owner, "name", None):
            tree.metadata["object"] = owner.name
        return tree

    resolved = system or system_for_tree_id(getattr(source, "bl_idname", None)) or _system_from_nodes(source)
    if resolved is None:
        raise ValueError("Could not tell whether this node tree is geometry, shader, or compositor")

    identity = id(source)
    if identity in _stack:
        return NodeTree(
            id="recursive_group",
            name=str(getattr(source, "name", "Group")),
            system=resolved,
            metadata={"recursive": True},
        )

    used: set[str] = set()
    nodes: list[GraphNode] = []
    id_by_node: dict[int, str] = {}
    for native in list(getattr(source, "nodes", [])):
        node_id = unique_name(str(getattr(native, "name", "node")), used)
        graph_node = _parse_node(native, node_id, resolved, _stack + (identity,))
        nodes.append(graph_node)
        id_by_node[id(native)] = node_id

    edges: list[GraphEdge] = []
    for index, link in enumerate(list(getattr(source, "links", []))):
        from_node = getattr(link, "from_node", None)
        to_node = getattr(link, "to_node", None)
        if from_node is None or to_node is None:
            continue
        if not getattr(link, "is_valid", True):
            continue
        from_id = id_by_node.get(id(from_node))
        to_id = id_by_node.get(id(to_node))
        if from_id is None or to_id is None:
            continue
        edges.append(
            GraphEdge(
                id=f"e{index}",
                from_node=from_id,
                from_socket=_socket_identifier(getattr(link, "from_socket", None)),
                to_node=to_id,
                to_socket=_socket_identifier(getattr(link, "to_socket", None)),
            )
        )

    tree = NodeTree(
        id=unique_name(str(getattr(source, "name", "node_tree")), set()),
        name=str(getattr(source, "name", "Node Tree")),
        system=resolved,
        nodes=nodes,
        edges=edges,
        interface=_parse_interface(source),
        metadata={"source": "blender"},
    )
    if modifier_name:
        tree.metadata["modifier"] = modifier_name
    return tree


def _is_modifier(source: Any) -> bool:
    return getattr(source, "node_group", None) is not None and hasattr(source, "type") and not hasattr(source, "nodes")


def _system_from_nodes(source: Any) -> GraphSystem | None:
    types = {getattr(node, "bl_idname", "") for node in list(getattr(source, "nodes", []))}
    if "ShaderNodeOutputMaterial" in types or "ShaderNodeBsdfPrincipled" in types:
        return GraphSystem.SHADER
    if "CompositorNodeComposite" in types or "CompositorNodeRLayers" in types:
        return GraphSystem.COMPOSITOR
    if types:
        return GraphSystem.GEOMETRY
    return None


def _parse_node(native: Any, node_id: str, system: GraphSystem, stack: tuple[int, ...]) -> GraphNode:
    location = getattr(native, "location", None)
    point = None
    if location is not None:
        try:
            point = (float(location[0]), float(location[1]))
        except (TypeError, IndexError, ValueError):
            point = None
    node_type = str(getattr(native, "bl_idname", "Unknown"))
    nested = None
    if node_type in _GROUP_TYPES and getattr(native, "node_tree", None) is not None:
        nested = parse_blender_tree(native.node_tree, system=system, _stack=stack)
    return GraphNode(
        id=node_id,
        name=str(getattr(native, "name", node_id)),
        node_type=node_type,
        inputs=[_parse_socket(socket, SocketDirection.INPUT) for socket in list(getattr(native, "inputs", []))],
        outputs=[_parse_socket(socket, SocketDirection.OUTPUT) for socket in list(getattr(native, "outputs", []))],
        parameters=_parameters(native),
        location=point,
        mute=bool(getattr(native, "mute", False)),
        label=str(getattr(native, "label", "") or ""),
        nested=nested,
        properties=_properties(native),
    )


def _parse_socket(socket: Any, direction: SocketDirection) -> GraphSocket:
    identifier = _socket_identifier(socket)
    return GraphSocket(
        identifier=identifier,
        name=str(getattr(socket, "name", identifier)),
        direction=direction,
        data_type=socket_data_type(socket),
        default=pythonize(getattr(socket, "default_value", None)),
        is_field=is_field_socket(socket),
        is_multi_input=bool(getattr(socket, "is_multi_input", False)),
        enabled=bool(getattr(socket, "enabled", True)),
    )


def _socket_identifier(socket: Any) -> str:
    if socket is None:
        return ""
    identifier = getattr(socket, "identifier", None) or getattr(socket, "name", "")
    return str(identifier)


def _parameters(native: Any) -> list[NodeParameter]:
    found = []
    for socket in list(getattr(native, "inputs", [])):
        if getattr(socket, "is_linked", False):
            continue
        default = pythonize(getattr(socket, "default_value", None))
        if default is None:
            continue
        identifier = _socket_identifier(socket)
        found.append(
            NodeParameter(
                name=str(getattr(socket, "name", identifier)),
                value=default,
                data_type=socket_data_type(socket),
                identifier=identifier,
            )
        )
    return found


def _properties(native: Any) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for name in _PROPERTY_NAMES:
        if not hasattr(native, name):
            continue
        value = getattr(native, name)
        if isinstance(value, (str, int, float, bool)):
            properties[name] = value
    ramp = getattr(native, "color_ramp", None)
    if ramp is not None and hasattr(ramp, "elements"):
        properties["color_ramp"] = [
            {"position": float(element.position), "color": pythonize(element.color)}
            for element in list(ramp.elements)
        ]
    return properties


def _parse_interface(source: Any) -> list[InterfaceSocket]:
    items = _interface_items(source)
    sockets = []
    for item in items:
        item_type = str(getattr(item, "item_type", "SOCKET")).upper()
        if item_type not in {"SOCKET", ""}:
            continue
        raw_direction = str(getattr(item, "in_out", getattr(item, "direction", "INPUT"))).upper()
        direction = SocketDirection.OUTPUT if raw_direction == "OUTPUT" else SocketDirection.INPUT
        socket_type = str(getattr(item, "socket_type", "") or getattr(item, "bl_socket_idname", "") or "")
        identifier = str(getattr(item, "identifier", "") or getattr(item, "name", "Socket"))
        sockets.append(
            InterfaceSocket(
                identifier=identifier,
                name=str(getattr(item, "name", identifier)),
                direction=direction,
                data_type=data_type_from_blender_socket(socket_type) if socket_type else _declared_type(item),
                default=pythonize(getattr(item, "default_value", None)),
                minimum=pythonize(getattr(item, "min_value", None)),
                maximum=pythonize(getattr(item, "max_value", None)),
                description=str(getattr(item, "description", "") or ""),
            )
        )
    return sockets


def _interface_items(source: Any) -> list[Any]:
    interface = getattr(source, "interface", None)
    if interface is not None and hasattr(interface, "items_tree"):
        return list(interface.items_tree)
    if hasattr(source, "interface_sockets"):
        return list(source.interface_sockets)
    legacy = []
    for socket in list(getattr(source, "inputs", [])):
        setattr_direction(socket, "INPUT")
        legacy.append(socket)
    for socket in list(getattr(source, "outputs", [])):
        setattr_direction(socket, "OUTPUT")
        legacy.append(socket)
    return legacy


def setattr_direction(socket: Any, direction: str) -> None:
    if not hasattr(socket, "in_out"):
        try:
            socket.in_out = direction
        except AttributeError:
            socket.direction = direction


def _declared_type(item: Any) -> DataType:
    declared = getattr(item, "data_type", None)
    if isinstance(declared, DataType):
        return declared
    if isinstance(declared, str):
        try:
            return DataType(declared)
        except ValueError:
            return data_type_from_blender_socket(declared)
    return DataType.ANY


def _apply_modifier_values(modifier: Any, tree: NodeTree) -> None:
    """Copy Geometry Nodes modifier values over the group defaults."""

    for item in tree.interface:
        if item.direction is not SocketDirection.INPUT:
            continue
        value = _modifier_value(modifier, item.identifier)
        if value is None:
            value = _modifier_value(modifier, item.name)
        if value is not None:
            item.default = value


def _modifier_value(modifier: Any, key: str) -> Any:
    getter = getattr(modifier, "get", None)
    if callable(getter):
        try:
            if key in modifier:
                return pythonize(modifier[key])
        except (KeyError, TypeError, AttributeError):
            return None
    return None
