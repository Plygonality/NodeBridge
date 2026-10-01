"""Unreal PCG backend.

Primary output is a construction plan. Generated Unreal Python uses the
documented UE 5.7 experimental API (``add_node_of_type``, ``add_edge``)
and is not executed by IR load. Runtime application requires the editor.
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
from nodebridge.hosts.native import NativeGraph
from nodebridge.hosts.recipes import NodeTemplate, Recipe, unsupported_fragment
from nodebridge.core.graph import GraphSystem
from nodebridge.hosts.unreal.capabilities import unreal_capabilities
from nodebridge.hosts.unreal.mappings import SETTINGS_CLASSES, UNREAL_RECIPES
from nodebridge.hosts.unreal.material_script import emit_unreal_compositor, emit_unreal_material
from nodebridge.ir.versioning import PACKAGE_VERSION


class UnrealBackend:
    """Translate IR graphs into Unreal PCG construction plans."""

    name = "unreal"

    def __init__(self) -> None:
        self.capabilities: CapabilitySet = unreal_capabilities()

    def implementation_for(self, operation: str) -> Implementation:
        recipe = UNREAL_RECIPES.get(operation)
        if recipe is None:
            return Implementation(
                operation=operation,
                fidelity=TranslationStatus.UNSUPPORTED,
                available=False,
                note=(
                    "No Unreal PCG mapping is registered. Math/vector ops are "
                    "not first-class PCG nodes in the current Python API."
                ),
            )
        return recipe.implementation()

    def lower_node(self, node: IRNode) -> LoweringFragment:
        system = node.metadata.provenance.graph_system
        if system in {"shader", "shader_nodes"} or node.operation.startswith(("shader.", "color.", "texture.")):
            recipe = _SHADER_NOTES.get(node.operation)
            if recipe is not None:
                return recipe.apply(node)
        if system in {"compositor", "compositor_nodes"} or node.operation.startswith("compositor."):
            return unsupported_fragment(
                node,
                note=(
                    "Unreal Editor Python has no Blender-style compositor graph. "
                    "NodeBridge does not invent a post-process material for this operation."
                ),
            )
        recipe = UNREAL_RECIPES.get(node.operation)
        if recipe is None:
            return unsupported_fragment(
                node,
                note=(
                    "No Unreal PCG mapping is registered. Do not invent a "
                    "Material or Blueprint substitute silently."
                ),
            )
        return recipe.apply(node)

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
        native, _report = assemble_native(graph, self, host_id="unreal", system="pcg")
        native.metadata["api"] = "experimental-ue5.7"
        native.metadata["runtime"] = "editor-only"
        return native

    def generate(self, graph: IRGraph) -> str:
        if graph.system is GraphSystem.SHADER:
            return emit_unreal_material(graph)
        if graph.system is GraphSystem.COMPOSITOR:
            return emit_unreal_compositor(graph)
        return emit_unreal_script(self.build(graph))


def _shader_recipe(operation: str, native_type: str, *, fidelity: TranslationStatus, note: str) -> Recipe:
    return Recipe(
        operation=operation,
        fidelity=fidelity,
        nodes=(NodeTemplate(local_id="expr", native_type=native_type, inputs=("In",), outputs=("Out",)),),
        note=note,
    )


_SHADER_NOTES = {
    "shader.principled_surface": _shader_recipe(
        "shader.principled_surface",
        "MaterialExpressionMakeMaterialAttributes",
        fidelity=TranslationStatus.APPROXIMATE,
        note="Material attributes approximate Principled BSDF. They are not the same closure.",
    ),
    "shader.output": _shader_recipe(
        "shader.output",
        "Material",
        fidelity=TranslationStatus.EXACT,
        note="Material output connects to the Material root.",
    ),
    "procedural.noise": _shader_recipe(
        "procedural.noise",
        "MaterialExpressionNoise",
        fidelity=TranslationStatus.LOWERED,
        note="Unreal noise is not Blender's Noise Texture.",
    ),
    "procedural.voronoi": _shader_recipe(
        "procedural.voronoi",
        "MaterialExpressionNoise",
        fidelity=TranslationStatus.APPROXIMATE,
        note="Voronoi is approximated with MaterialExpressionNoise.",
    ),
    "color.mix": _shader_recipe(
        "color.mix",
        "MaterialExpressionLinearInterpolate",
        fidelity=TranslationStatus.LOWERED,
        note="Mix is a linear interpolate.",
    ),
    "color.ramp": _shader_recipe(
        "color.ramp",
        "MaterialExpressionLinearInterpolate",
        fidelity=TranslationStatus.APPROXIMATE,
        note="A color ramp is not reproduced. A lerp stands in for a two-stop blend.",
    ),
    "texture.sample": _shader_recipe(
        "texture.sample",
        "MaterialExpressionTextureSample",
        fidelity=TranslationStatus.LOWERED,
        note="Image texture becomes a texture sample. The asset is not imported.",
    ),
    "shader.texcoord": _shader_recipe(
        "shader.texcoord",
        "MaterialExpressionTextureCoordinate",
        fidelity=TranslationStatus.LOWERED,
        note="UV V is flipped for Unreal materials when deterministic UV conversion is requested.",
    ),
    "shader.normal": _shader_recipe(
        "shader.normal",
        "MaterialExpressionNormalMap",
        fidelity=TranslationStatus.APPROXIMATE,
        note="Normal Map approximates bump and normal-map nodes.",
    ),
    "math.add": _shader_recipe("math.add", "MaterialExpressionAdd", fidelity=TranslationStatus.EXACT, note="Add expression."),
    "math.multiply": _shader_recipe(
        "math.multiply", "MaterialExpressionMultiply", fidelity=TranslationStatus.EXACT, note="Multiply expression."
    ),
    "math.subtract": _shader_recipe(
        "math.subtract", "MaterialExpressionSubtract", fidelity=TranslationStatus.EXACT, note="Subtract expression."
    ),
}


def emit_unreal_script(native: NativeGraph) -> str:
    """Editor Python that creates a PCG graph asset.

    ``PCGGraph.add_node_of_type`` and ``add_edge`` are editor APIs. The
    script checks that they exist and raises if they do not. Pin labels are
    the ones NodeBridge recorded; a wrong label must not be papered over.
    """
    asset = "".join(character if character.isalnum() or character == "_" else "_" for character in native.name) or "NB_PCG"
    lines = [
        f"# Generated by NodeBridge {PACKAGE_VERSION}",
        "# Unreal Editor Python — PCG",
        f"# Source: {native.name}",
        "#",
        "# Paste into the Unreal Editor Python console or a Python asset.",
        "# Requires the Editor Python Script Plugin and the PCG plugin.",
        "# This creates a PCG graph asset. It does not import baked geometry.",
        "# Surface Sampler and Static Mesh Spawner do not reproduce Blender's",
        "# random sequence or packed instances exactly.",
        "# add_node_of_type / add_edge are editor-only and version-sensitive.",
        "# Loading a .nodebridge.json file does not execute this script.",
        "import unreal",
        "",
        "def build(asset_name=None, package_path='/Game/NodeBridge'):",
        f"    asset_name = asset_name or {asset!r}",
        "    if not hasattr(unreal, 'PCGGraphFactory'):",
        "        raise RuntimeError(",
        "            'unreal.PCGGraphFactory is not available. Enable the PCG plugin. '",
        "            'NodeBridge will not call an undocumented factory.'",
        "        )",
        "    tools = unreal.AssetToolsHelpers.get_asset_tools()",
        "    graph = tools.create_asset(asset_name, package_path, unreal.PCGGraph, unreal.PCGGraphFactory())",
        "    if not hasattr(graph, 'add_node_of_type'):",
        "        raise RuntimeError(",
        "            'PCGGraph.add_node_of_type is not available in this Unreal Editor build. '",
        "            'NodeBridge does not guess a private graph API.'",
        "        )",
        "    created = {}",
        "    input_node = graph.get_input_node()",
        "    output_node = graph.get_output_node()",
        "    created['input'] = input_node",
        "    created['output'] = output_node",
    ]
    x = 200
    for node in native.nodes:
        operation = node.metadata.get("operation") or node.type
        note = node.metadata.get("note") or ""
        fidelity = str(node.metadata.get("fidelity") or "")
        if node.type in {"Input", "Output", "PCGGraphInput", "PCGGraphOutput"}:
            key = "input" if "input" in node.type.lower() or node.type == "Input" else "output"
            lines.append(f"    created[{node.id!r}] = created[{key!r}]")
            continue
        settings = SETTINGS_CLASSES.get(node.type)
        if settings is None or fidelity == "unsupported" or node.type == "nodebridge.unsupported":
            lines.append(f"    # UNSUPPORTED: {operation}")
            if note:
                lines.append(f"    # {note}")
            lines.append(f"    created[{node.id!r}] = None")
            continue
        if fidelity and fidelity != "exact":
            lines.append(f"    # {fidelity.upper()}: {operation}. {note}".rstrip())
        lines.append(f"    node, settings = graph.add_node_of_type({settings})")
        lines.append(f"    node.set_node_position({x}, 0)")
        for key, value in node.parameters.items():
            if key in {"role", "label", "snippet"}:
                continue
            lines.append("    try:")
            lines.append(f"        settings.set_editor_property({key!r}, {value!r})")
            lines.append("    except Exception as exc:")
            lines.append(f"        unreal.log_warning('NodeBridge could not set {key} on {operation}: ' + str(exc))")
        lines.append(f"    created[{node.id!r}] = node")
        x += 220
    for link in native.links:
        lines.append(
            f"    if created.get({link.source_node!r}) is not None and "
            f"created.get({link.target_node!r}) is not None:"
        )
        lines.append(
            f"        graph.add_edge(created[{link.source_node!r}], {link.source_socket!r}, "
            f"created[{link.target_node!r}], {link.target_socket!r})"
        )
    lines += [
        "    unreal.EditorAssetLibrary.save_loaded_asset(graph)",
        "    return graph",
        "",
        "if __name__ == '__main__':",
        "    build()",
        "",
    ]
    return "\n".join(lines)
