"""Unreal backend.

Geometry graphs become PCG graph assets. Shader graphs become materials.
Compositor graphs become a material only for color operations; glare, masks,
and filters are reported unsupported. No Unreal API is called unless it is
resolved with getattr or is a documented editor class.
"""

from __future__ import annotations

from nodebridge.backend.unreal.materials import generate_material
from nodebridge.backend.unreal.pcg import generate_pcg
from nodebridge.backend.unreal.python import script_header
from nodebridge.common.names import sanitize_identifier
from nodebridge.ir.semantic import OperationKind, SemanticGraph
from nodebridge.translation.confidence import Classification, Confidence, TranslationRecord


class UnrealBackend:
    """Generate Unreal Editor Python."""

    id = "unreal"

    def supports(self, operation: OperationKind) -> bool:
        return self.classify(operation).confidence is not Confidence.UNSUPPORTED

    def classify(self, operation: OperationKind) -> Classification:
        return _DEFAULTS.get(
            operation,
            Classification(
                confidence=Confidence.UNSUPPORTED,
                explanation=f"No Unreal translator is registered for {operation.value}.",
                implementation="none",
            ),
        )

    def generate(self, graph: SemanticGraph, options) -> tuple[str, list[TranslationRecord]]:
        if graph.system.value == "shader":
            return generate_material(graph, options)
        if graph.system.value == "compositor":
            return _generate_compositor(graph, options)
        return generate_pcg(graph, options)


def _generate_compositor(graph: SemanticGraph, options) -> tuple[str, list[TranslationRecord]]:
    """Color operations become a post-process-style material. The rest are listed."""

    asset = "NB_" + sanitize_identifier(graph.name)
    lines = script_header(
        "NodeBridge Unreal compositor fallback.",
        f"Source: Compositor / {graph.name}",
    )
    lines.extend(
        [
            "def build(package_path='/Game/NodeBridge'):",
            "    # Glare, vignette masks, and most filters have no honest Unreal material equivalent here.",
            "    # Color operations are written into a material the user can assign to a post-process volume.",
            "    tools = unreal.AssetToolsHelpers.get_asset_tools()",
            "    material = tools.create_asset(" + repr(asset) + ", package_path, unreal.Material, unreal.MaterialFactoryNew())",
            "    if material is None:",
            "        raise RuntimeError('Could not create compositor fallback material')",
            "    library = unreal.MaterialEditingLibrary",
        ]
    )
    records = []
    color_connected = False
    for operation in graph.operations:
        mode = str(operation.parameters.get("mode", ""))
        if operation.kind is OperationKind.COMPOSITOR_OPERATION and mode in {"brightness", "color_balance", "color_correction", "exposure", "hue", "tonemap", "mix"}:
            lines.append(f"    # operation: {operation.id} kind=compositor_operation confidence=approximate")
            lines.append(f"    # {mode} is approximated by a post-process material constant. It is not the Blender compositor.")
            if not color_connected:
                lines.append("    color = library.create_material_expression(material, unreal.MaterialExpressionConstant3Vector, -300, 0)")
                lines.append("    color.set_editor_property('constant', unreal.LinearColor(1.0, 1.0, 1.0, 1.0))")
                lines.append("    library.connect_material_property(color, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)")
                color_connected = True
            records.append(
                TranslationRecord(
                    operation_id=operation.id,
                    operation_name=operation.name,
                    operation=operation.kind.value,
                    classification=Classification(
                        confidence=Confidence.APPROXIMATE,
                        explanation=f"{mode} is only a color-material approximation of the compositor node.",
                        implementation="post-process material",
                        limitations=("This is not a compositor graph. Glare and masks are not reproduced.",),
                    ),
                    source_types=operation.source.node_types,
                )
            )
        else:
            reason = f"No Unreal compositor equivalent is implemented for {mode or operation.kind.value}."
            lines.append(f"    # operation: {operation.id} kind={operation.kind.value} confidence=unsupported")
            lines.append(f"    # {reason}")
            records.append(
                TranslationRecord(
                    operation_id=operation.id,
                    operation_name=operation.name,
                    operation=operation.kind.value,
                    classification=Classification(
                        confidence=Confidence.UNSUPPORTED,
                        explanation=reason,
                        implementation="none",
                        fallback="listed in the script and omitted from the material",
                    ),
                    source_types=operation.source.node_types,
                )
            )
    lines.extend(
        [
            "    library.recompile_material(material)",
            "    unreal.EditorAssetLibrary.save_asset(material.get_path_name())",
            "    return material",
            "",
            "",
            "if __name__ == '__main__':",
            "    build()",
            "",
        ]
    )
    return "\n".join(lines), records


_DEFAULTS = {
    OperationKind.SCATTER: Classification(Confidence.EQUIVALENT, "PCG Surface Sampler.", "PCGSurfaceSamplerSettings"),
    OperationKind.INSTANCE: Classification(Confidence.EQUIVALENT, "PCG Static Mesh Spawner.", "PCGStaticMeshSpawnerSettings"),
    OperationKind.TRANSFORM: Classification(Confidence.APPROXIMATE, "PCG Transform Points when the class exists.", "PCGTransformPointsSettings"),
    OperationKind.RANDOM_TRANSFORM: Classification(Confidence.APPROXIMATE, "PCG Transform Points.", "PCGTransformPointsSettings"),
    OperationKind.PRIMITIVE: Classification(Confidence.APPROXIMATE, "No PCG primitive node. The graph input is the surface.", "graph input"),
    OperationKind.GROUP_INPUT: Classification(Confidence.EQUIVALENT, "PCG graph input.", "PCGGraph input"),
    OperationKind.GROUP_OUTPUT: Classification(Confidence.EXACT, "PCG graph output.", "PCGGraph output"),
    OperationKind.REALIZE_INSTANCES: Classification(Confidence.EQUIVALENT, "Spawner output is already instanced.", "spawner output"),
    OperationKind.MATH: Classification(Confidence.APPROXIMATE, "Not a first-class PCG node in this script.", "comment"),
    OperationKind.NOISE: Classification(Confidence.APPROXIMATE, "MaterialExpressionNoise for shaders. Not exact.", "MaterialExpressionNoise"),
    OperationKind.SHADER_OPERATION: Classification(Confidence.EQUIVALENT, "Unreal material expressions.", "MaterialEditingLibrary"),
    OperationKind.COMPOSITOR_OPERATION: Classification(Confidence.APPROXIMATE, "Only color operations have a material fallback.", "post-process material"),
    OperationKind.SUBGRAPH: Classification(Confidence.APPROXIMATE, "PCGSubgraphSettings when the class exists.", "PCGSubgraphSettings"),
    OperationKind.UNSUPPORTED: Classification(Confidence.UNSUPPORTED, "No Unreal implementation.", "none"),
}
