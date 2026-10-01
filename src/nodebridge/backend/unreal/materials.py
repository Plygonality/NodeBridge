"""Unreal material scripts for shader graphs."""

from __future__ import annotations

from nodebridge.backend.unreal.python import script_header
from nodebridge.common.names import sanitize_identifier
from nodebridge.ir.semantic import OperationKind, SemanticGraph
from nodebridge.translation.confidence import Classification, Confidence, TranslationRecord


def generate_material(graph: SemanticGraph, options) -> tuple[str, list[TranslationRecord]]:
    asset = "NB_" + sanitize_identifier(graph.name)
    lines = script_header("NodeBridge Unreal material.", f"Source: Shader / {graph.name}")
    lines.extend(
        [
            "def build(package_path='/Game/NodeBridge'):",
            "    tools = unreal.AssetToolsHelpers.get_asset_tools()",
            "    factory = unreal.MaterialFactoryNew()",
            f"    material = tools.create_asset({asset!r}, package_path, unreal.Material, factory)",
            "    if material is None:",
            f"        raise RuntimeError('Could not create material {asset}')",
            "    library = unreal.MaterialEditingLibrary",
        ]
    )
    records = []
    for operation in graph.operations:
        if operation.kind is OperationKind.SHADER_OPERATION and operation.parameters.get("mode") == "principled":
            color = operation.parameters.get("base_color", (0.8, 0.8, 0.8))
            if not isinstance(color, (list, tuple)):
                color = (0.8, 0.8, 0.8)
            color = tuple(float(channel) for channel in list(color)[:3])
            roughness = float(operation.parameters.get("roughness", 0.5) or 0.5)
            metallic = float(operation.parameters.get("metallic", 0.0) or 0.0)
            lines.extend(
                [
                    f"    # operation: {operation.id} kind=shader_operation confidence=equivalent",
                    "    color_expr = library.create_material_expression(material, unreal.MaterialExpressionConstant3Vector, -400, 0)",
                    f"    color_expr.set_editor_property('constant', unreal.LinearColor({color[0]!r}, {color[1]!r}, {color[2]!r}, 1.0))",
                    "    library.connect_material_property(color_expr, '', unreal.MaterialProperty.MP_BASE_COLOR)",
                    "    rough_expr = library.create_material_expression(material, unreal.MaterialExpressionScalarParameter, -400, 180)",
                    "    rough_expr.set_editor_property('parameter_name', 'Roughness')",
                    f"    rough_expr.set_editor_property('default_value', {roughness!r})",
                    "    library.connect_material_property(rough_expr, '', unreal.MaterialProperty.MP_ROUGHNESS)",
                    "    metal_expr = library.create_material_expression(material, unreal.MaterialExpressionScalarParameter, -400, 320)",
                    "    metal_expr.set_editor_property('parameter_name', 'Metallic')",
                    f"    metal_expr.set_editor_property('default_value', {metallic!r})",
                    "    library.connect_material_property(metal_expr, '', unreal.MaterialProperty.MP_METALLIC)",
                ]
            )
            records.append(_record(operation, Confidence.EQUIVALENT, "MaterialExpression", "Principled base color, roughness, and metallic become material expressions and parameters."))
        elif operation.kind is OperationKind.NOISE:
            scale = float(operation.parameters.get("scale", 5.0) or 5.0)
            lines.extend(
                [
                    f"    # operation: {operation.id} kind=noise confidence=approximate",
                    "    noise_expr = library.create_material_expression(material, unreal.MaterialExpressionNoise, -700, 0)",
                    f"    _try_set(noise_expr, 'scale', {scale!r})",
                    "    library.connect_material_property(noise_expr, '', unreal.MaterialProperty.MP_BASE_COLOR)",
                ]
            )
            records.append(_record(operation, Confidence.APPROXIMATE, "MaterialExpressionNoise", "Unreal noise is not Blender's noise texture. The pattern will differ."))
        elif operation.kind is OperationKind.COLOR_OPERATION and operation.parameters.get("mode") == "ramp":
            lines.extend(
                [
                    f"    # operation: {operation.id} kind=color_operation confidence=approximate",
                    f"    # Color ramp stops: {operation.parameters.get('stops')!r}",
                    "    lerp_expr = library.create_material_expression(material, unreal.MaterialExpressionLinearInterpolate, -500, 200)",
                ]
            )
            records.append(_record(operation, Confidence.APPROXIMATE, "MaterialExpressionLinearInterpolate", "A color ramp is reduced to a lerp. Extra Blender stops are listed in the comment."))
        elif operation.kind is OperationKind.SHADER_OPERATION and operation.parameters.get("mode") == "material_output":
            lines.append(f"    # operation: {operation.id} kind=shader_operation confidence=exact")
            lines.append("    # Material Output is the material root. Expressions above are connected to material properties.")
            records.append(_record(operation, Confidence.EXACT, "material root", "Material Output is the Unreal material itself."))
        else:
            lines.append(f"    # operation: {operation.id} kind={operation.kind.value} confidence=approximate")
            lines.append(f"    # {operation.name} has no dedicated material expression in this translator.")
            records.append(_record(operation, Confidence.APPROXIMATE, "comment", f"{operation.kind.value} is reported and not given a dedicated expression."))
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


def _record(operation, confidence, implementation, explanation) -> TranslationRecord:
    limitations = ()
    if confidence is Confidence.APPROXIMATE:
        limitations = ("The material will not match Blender's shader pixel for pixel.",)
    return TranslationRecord(
        operation_id=operation.id,
        operation_name=operation.name,
        operation=operation.kind.value,
        classification=Classification(
            confidence=confidence,
            explanation=explanation,
            implementation=implementation,
            limitations=limitations,
        ),
        source_types=operation.source.node_types,
    )
