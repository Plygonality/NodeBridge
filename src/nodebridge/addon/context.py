"""Find the Blender node tree the user is looking at.

This module does not import ``bpy``. Callers pass a context object.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceSelection:
    """The tree or modifier NodeBridge should compile, plus a label for the panel."""

    source: Any
    system: str
    label: str
    detail: str


def resolve_source(context: Any, mode: str = "auto") -> SourceSelection:
    """Infer Geometry Nodes, a shader, or the compositor from the current context."""

    wanted = (mode or "auto").lower()
    editor = _editor_tree(context)
    if editor is not None and (wanted == "auto" or wanted == editor[1]):
        return editor[0]

    if wanted in {"auto", "geometry_nodes"}:
        modifier = _geometry_modifier(context)
        if modifier is not None:
            group = modifier.node_group
            owner = getattr(getattr(context, "object", None) or getattr(context, "active_object", None), "name", "Object")
            return SourceSelection(modifier, "geometry_nodes", "Geometry Nodes", f"{owner} / {getattr(group, 'name', modifier.name)}")

    if wanted in {"auto", "shader"}:
        material = _material_tree(context)
        if material is not None:
            return material

    if wanted in {"auto", "compositor"}:
        compositor = _compositor_tree(context)
        if compositor is not None:
            return compositor

    if editor is not None and wanted == "auto":
        return editor[0]
    return SourceSelection(None, "", "No node tree", "Open a Geometry Nodes, Shader, or Compositor editor, or select an object with a Geometry Nodes modifier.")


def _editor_tree(context: Any) -> tuple[SourceSelection, str] | None:
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) not in {None, "NODE_EDITOR"} and not hasattr(space, "tree_type"):
        return None
    tree_type = getattr(space, "tree_type", None)
    tree = getattr(space, "edit_tree", None) or getattr(space, "node_tree", None)
    if tree is None or not tree_type:
        return None
    system = {
        "GeometryNodeTree": "geometry_nodes",
        "ShaderNodeTree": "shader",
        "CompositorNodeTree": "compositor",
    }.get(tree_type)
    if system is None:
        return None
    label = {
        "geometry_nodes": "Geometry Nodes",
        "shader": "Shader",
        "compositor": "Compositor",
    }[system]
    return SourceSelection(tree, system, label, getattr(tree, "name", label)), system


def _geometry_modifier(context: Any):
    obj = getattr(context, "object", None) or getattr(context, "active_object", None)
    for modifier in list(getattr(obj, "modifiers", []) or []):
        if getattr(modifier, "type", None) == "NODES" and getattr(modifier, "node_group", None) is not None:
            return modifier
    return None


def _material_tree(context: Any) -> SourceSelection | None:
    obj = getattr(context, "object", None) or getattr(context, "active_object", None)
    material = getattr(obj, "active_material", None)
    tree = getattr(material, "node_tree", None)
    if tree is None:
        return None
    return SourceSelection(tree, "shader", "Shader", getattr(material, "name", getattr(tree, "name", "Material")))


def _compositor_tree(context: Any) -> SourceSelection | None:
    scene = getattr(context, "scene", None)
    tree = getattr(scene, "compositing_node_group", None) or getattr(scene, "node_tree", None)
    if tree is None:
        return None
    return SourceSelection(tree, "compositor", "Compositor", getattr(tree, "name", "Compositor"))
