"""Houdini SOP backend.

Produces an editable SOP construction plan. Generated hou scripts are text;
they are never executed by loading IR.
"""

from __future__ import annotations

from nodebridge.backends.base import GraphFragment, TargetConnectionSpec, TargetNodeSpec
from nodebridge.core.capabilities import CapabilitySet
from nodebridge.core.diagnostics import TranslationStatus
from nodebridge.core.graph import IRGraph
from nodebridge.core.metadata import SourceMapping
from nodebridge.core.node import IRNode
from nodebridge.hosts.assemble import assemble_native
from nodebridge.hosts.contract import Implementation, LoweringFragment
from nodebridge.hosts.houdini.capabilities import houdini_capabilities
from nodebridge.hosts.houdini.codegen import emit_houdini_script
from nodebridge.hosts.houdini.contexts import COP_RECIPES, SHADER_RECIPES
from nodebridge.hosts.houdini.mappings import HOUDINI_RECIPES, PRIMITIVE_BACKEND_TYPES
from nodebridge.hosts.native import NativeGraph
from nodebridge.hosts.recipes import unsupported_fragment


class HoudiniBackend:
    """Translate IR geometry graphs into Houdini SOP networks."""

    name = "houdini"

    def __init__(self) -> None:
        self.capabilities: CapabilitySet = houdini_capabilities()

    def implementation_for(self, operation: str) -> Implementation:
        recipe = HOUDINI_RECIPES.get(operation)
        if recipe is None:
            return Implementation(
                operation=operation,
                fidelity=TranslationStatus.UNSUPPORTED,
                available=False,
                note="No Houdini SOP mapping is registered",
            )
        return recipe.implementation()

    def lower_node(self, node: IRNode) -> LoweringFragment:
        recipe = _recipe_for(node)
        if recipe is None:
            return unsupported_fragment(node, note="No Houdini SOP mapping is registered")
        fragment = recipe.apply(node)
        if node.operation == "geometry.primitive" and fragment.nodes:
            kind = "cube"
            if "primitive" in node.parameters:
                kind = str(node.parameters["primitive"].value)
            fragment.nodes[0].type = PRIMITIVE_BACKEND_TYPES.get(kind, "box")
            fragment.recipe = fragment.nodes[0].type
        if node.operation == "geometry.curve_primitive" and fragment.nodes:
            kind = "circle"
            if "primitive" in node.parameters:
                kind = str(node.parameters["primitive"].value)
            fragment.nodes[0].type = {"circle": "circle", "line": "line"}.get(kind, "circle")
            fragment.recipe = fragment.nodes[0].type
        return fragment

    def translate_node(self, node: IRNode) -> GraphFragment:
        fragment = self.lower_node(node)
        return GraphFragment(
            nodes=[
                TargetNodeSpec(id=item.id, kind=item.type, parameters=dict(item.parameters))
                for item in fragment.nodes
            ],
            connections=[
                TargetConnectionSpec(
                    source_node=link.source_node,
                    source_socket=link.source_socket,
                    target_node=link.target_node,
                    target_socket=link.target_socket,
                )
                for link in fragment.links
            ],
            status=fragment.fidelity,
            mapping=SourceMapping(
                ir_node_id=node.id,
                target_nodes=[item.id for item in fragment.nodes],
            ),
        )

    def build(self, graph: IRGraph) -> NativeGraph:
        native, _report = assemble_native(graph, self, host_id="houdini", system="sop")
        return native

    def generate(self, graph: IRGraph) -> str:
        native = self.build(graph)
        options = graph.metadata.extra.get("nodebridge_options") or {}
        native.metadata["options"] = dict(options) if isinstance(options, dict) else {}
        return emit_houdini_script(native, graph)


def _recipe_for(node: IRNode):
    system = node.metadata.provenance.graph_system
    if system in {"shader", "shader_nodes"} or node.operation.startswith(("shader.", "color.", "texture.")):
        recipe = SHADER_RECIPES.get(node.operation)
        if recipe is not None:
            return recipe
    if system in {"compositor", "compositor_nodes"} or node.operation.startswith("compositor."):
        recipe = COP_RECIPES.get(node.operation)
        if recipe is not None:
            return recipe
    return HOUDINI_RECIPES.get(node.operation)
