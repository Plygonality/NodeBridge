"""Blender frontend: native node tree to graph IR to semantic IR."""

from __future__ import annotations

from typing import Any

from nodebridge.frontend.blender.lower import lower_tree
from nodebridge.frontend.blender.parser import parse_blender_tree, system_for_tree_id
from nodebridge.ir.graph import GraphSystem, NodeTree
from nodebridge.ir.semantic import SemanticGraph


class BlenderFrontend:
    """Read Geometry Nodes, shader nodes, and compositor nodes."""

    id = "blender"

    def parse(self, source: Any, *, system: GraphSystem | None = None) -> NodeTree:
        return parse_blender_tree(source, system=system)

    def lower(self, tree: NodeTree) -> SemanticGraph:
        return lower_tree(tree)

    def system_for(self, bl_idname: str | None) -> GraphSystem | None:
        return system_for_tree_id(bl_idname)
