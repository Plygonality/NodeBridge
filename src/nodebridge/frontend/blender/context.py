"""Infer which Blender node tree the user is looking at.

The function uses attribute access so tests can pass a stand-in context.
It does not import ``bpy``.
"""

from __future__ import annotations

from typing import Any


def infer_source(context: Any) -> tuple[str, Any | None, str]:
    """Return ``(system, tree, label)``.

    Geometry Nodes editor, Shader Editor, and Compositor are recognized.
    If no editor tree is active, the active object's Geometry Nodes
    modifier is used.
    """
    space = getattr(context, "space_data", None)
    tree_type = str(getattr(space, "tree_type", "") or "") if space is not None else ""
    node_tree = getattr(space, "node_tree", None) if space is not None else None
    if tree_type == "GeometryNodeTree" and node_tree is not None:
        return "geometry_nodes", node_tree, str(getattr(node_tree, "name", "Geometry Nodes"))
    if tree_type == "ShaderNodeTree" and node_tree is not None:
        return "shader", node_tree, str(getattr(node_tree, "name", "Material"))
    if tree_type == "CompositorNodeTree":
        scene = getattr(context, "scene", None)
        tree = node_tree or getattr(scene, "node_tree", None)
        if tree is not None:
            return "compositor", tree, str(getattr(tree, "name", "Compositor"))
    obj = getattr(context, "active_object", None)
    if obj is None:
        obj = getattr(context, "object", None)
    if obj is not None:
        for modifier in getattr(obj, "modifiers", []) or []:
            if str(getattr(modifier, "type", "") or "") != "NODES":
                continue
            group = getattr(modifier, "node_group", None)
            if group is not None:
                label = str(getattr(group, "name", None) or getattr(modifier, "name", "Geometry Nodes"))
                return "geometry_nodes", group, label
    return "geometry_nodes", None, ""
