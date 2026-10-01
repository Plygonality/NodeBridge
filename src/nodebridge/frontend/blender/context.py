"""Resolve what the user wants to translate from Blender's UI context.

* Geometry Node editor -> the edited tree, with the active object's
  Geometry Nodes modifier values
* Shader editor -> the active material's tree
* Compositor -> the scene's compositing tree (4.x ``scene.node_tree``,
  5.x ``scene.compositing_node_group``)

Materials used by Set Material nodes are parsed too, so a Geometry Nodes
translation can include their shading networks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...ir.graph import GraphDocument, TreeKind
from .parser import TREE_KINDS, _collect_groups, parse_document, parse_tree

KIND_BY_SOURCE_TYPE = {"GEOMETRY": TreeKind.GEOMETRY, "SHADER": TreeKind.SHADER, "COMPOSITOR": TreeKind.COMPOSITOR}


@dataclass
class SourceSelection:
    tree: Any
    kind: TreeKind
    root_name: str
    label: str
    owner: str = ""
    modifier: Any = None
    source: dict = field(default_factory=dict)


class SourceNotFound(Exception):
    pass


def scene_compositor_tree(scene: Any) -> Any:
    tree = getattr(scene, "compositing_node_group", None)
    if tree is None:
        tree = getattr(scene, "node_tree", None)
    return tree


def _geometry_modifier(obj: Any, tree: Any = None) -> Any:
    if obj is None:
        return None
    modifiers = [m for m in getattr(obj, "modifiers", []) if m.type == "NODES" and m.node_group is not None]
    if tree is not None:
        matching = [m for m in modifiers if m.node_group == tree]
        if matching:
            active = getattr(obj.modifiers, "active", None)
            return active if active in matching else matching[0]
        return None
    active = getattr(obj.modifiers, "active", None)
    if active is not None and active in modifiers:
        return active
    return modifiers[0] if modifiers else None


def resolve_source(context: Any, source_type: str = "AUTO") -> SourceSelection:
    import bpy

    scene = context.scene
    obj = context.active_object
    space = getattr(context, "space_data", None)
    application = f"Blender {bpy.app.version_string}"
    base = {"application": application, "unit_scale": float(scene.unit_settings.scale_length), "fps": float(scene.render.fps)}

    wanted = KIND_BY_SOURCE_TYPE.get(source_type)
    if wanted is None and space is not None and getattr(space, "type", "") == "NODE_EDITOR":
        wanted = TREE_KINDS.get(getattr(space, "tree_type", ""))
    wanted = wanted or TreeKind.GEOMETRY

    if wanted == TreeKind.GEOMETRY:
        tree = None
        if space is not None and getattr(space, "type", "") == "NODE_EDITOR" and getattr(space, "tree_type", "") == "GeometryNodeTree":
            tree = space.edit_tree or space.node_tree
        modifier = _geometry_modifier(obj, tree)
        if tree is None and modifier is not None:
            tree = modifier.node_group
        if tree is None:
            raise SourceNotFound("No Geometry Nodes tree: open one in the Geometry Node editor or select an object with a Geometry Nodes modifier.")
        source = dict(base, display_name=tree.name)
        if modifier is not None:
            source.update(object=obj.name, modifier=modifier.name, object_dimensions=[round(float(v), 4) for v in obj.dimensions])
        owner = f"{obj.name} > {modifier.name}" if modifier is not None else "(no modifier)"
        return SourceSelection(tree, TreeKind.GEOMETRY, tree.name, tree.name, owner, modifier, source)

    if wanted == TreeKind.SHADER:
        material = obj.active_material if obj is not None else None
        tree = None
        if space is not None and getattr(space, "type", "") == "NODE_EDITOR" and getattr(space, "tree_type", "") == "ShaderNodeTree":
            tree = space.edit_tree or space.node_tree
            if getattr(space, "id", None) is not None and getattr(space.id, "node_tree", None) is not None:
                material = space.id if type(space.id).__name__ == "Material" else material
        if tree is None and material is not None and material.use_nodes:
            tree = material.node_tree
        if tree is None:
            raise SourceNotFound("No shader tree: select an object with a node-based material.")
        name = material.name if material is not None and material.node_tree == tree else tree.name
        source = dict(base, display_name=name, material=name)
        return SourceSelection(tree, TreeKind.SHADER, name, name, f"Material {name}", None, source)

    tree = scene_compositor_tree(scene)
    if tree is None or not getattr(scene, "use_nodes", True):
        raise SourceNotFound("The scene has no compositor tree: enable 'Use Nodes' in the Compositor.")
    if space is not None and getattr(space, "type", "") == "NODE_EDITOR" and getattr(space, "tree_type", "") == "CompositorNodeTree" and space.edit_tree is not None:
        tree = space.edit_tree
    name = f"{scene.name} Compositor" if tree == scene_compositor_tree(scene) else tree.name
    source = dict(base, display_name=name, scene=scene.name)
    return SourceSelection(tree, TreeKind.COMPOSITOR, name, name, f"Scene {scene.name}", None, source)


def build_document(selection: SourceSelection, *, include_materials: bool = True) -> GraphDocument:
    document = parse_document(selection.tree, root_name=selection.root_name, source=selection.source, modifier=selection.modifier)
    if include_materials and selection.kind == TreeKind.GEOMETRY:
        add_referenced_materials(document, selection.tree)
    return document


def add_referenced_materials(document: GraphDocument, tree: Any) -> None:
    """Parse node-based materials assigned by Set Material nodes."""
    trees = [tree]
    groups: dict[str, Any] = {}
    _collect_groups(tree, groups)
    trees.extend(groups.values())
    materials: dict[str, str] = {}
    for current in trees:
        for node in current.nodes:
            if node.bl_idname != "GeometryNodeSetMaterial":
                continue
            socket = node.inputs.get("Material")
            material = getattr(socket, "default_value", None) if socket is not None else None
            if material is None or not material.use_nodes or material.node_tree is None or material.name in materials:
                continue
            tree_name = f"Material:{material.name}"
            document.trees[tree_name] = parse_tree(material.node_tree, name=tree_name)
            document.trees[tree_name].metadata["material"] = material.name
            shader_groups: dict[str, Any] = {}
            _collect_groups(material.node_tree, shader_groups)
            for name, group in shader_groups.items():
                document.trees.setdefault(name, parse_tree(group, name=name, is_group=True))
            materials[material.name] = tree_name
    if materials:
        document.source["materials"] = materials
