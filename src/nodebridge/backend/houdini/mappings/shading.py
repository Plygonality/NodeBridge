"""Houdini material builder output for shader graphs."""

from __future__ import annotations

from nodebridge.common.names import sanitize_identifier
from nodebridge.ir.semantic import OperationKind, SemanticGraph
from nodebridge.translation.confidence import Classification, Confidence, TranslationRecord
from nodebridge.translation.registry import REGISTRY, Translator


def register() -> None:
    if REGISTRY.get(OperationKind.SHADER_OPERATION, "houdini") is None:
        REGISTRY.register(
            Translator(
                operation=OperationKind.SHADER_OPERATION,
                target="houdini",
                confidence=Confidence.EQUIVALENT,
                implementation="materialbuilder / principledshader::2.0",
                explanation="Principled shading becomes a Material Builder. Noise and ramps are approximate because Houdini's shader noise is not Blender's.",
                limitations=("Noise patterns and normal-map conventions are not numerically identical.",),
                function=_sop_shader_gap,
            )
        )


def _sop_shader_gap(operation, build) -> None:
    spec = REGISTRY.get(OperationKind.SHADER_OPERATION, "houdini")
    build.classify(operation, spec, confidence=Confidence.UNSUPPORTED, explanation="Shader operations are not SOP nodes. Translate the shader tree with the shader source type.")
    build.passthrough(operation, "Shader operation inside a geometry graph has no SOP equivalent.")


def generate_material(graph: SemanticGraph, options) -> tuple[str, list[TranslationRecord]]:
    """Create a /mat material builder. Parameter names are set only when the node has them."""

    records: list[TranslationRecord] = []
    lines = [
        '"""NodeBridge Houdini material.',
        "",
        f"Source: Shader / {graph.name}",
        "Target: Houdini Material Builder",
        "",
        "Paste into the Houdini Python Source Editor and run.",
        "Noise and color-ramp patterns are approximate, not pixel-identical.",
        '"""',
        "",
        "import hou",
        "",
        "def _set(node, name, value):",
        "    parm = node.parm(name)",
        "    if parm is not None:",
        "        parm.set(value)",
        "",
        "def _set_tuple(node, name, value):",
        "    parm = node.parmTuple(name)",
        "    if parm is not None:",
        "        parm.set(value)",
        "",
        "def _wire(destination, input_name, source):",
        "    try:",
        "        destination.setNamedInput(input_name, source, 0)",
        "    except hou.OperationFailed:",
        "        destination.setComment((destination.comment() or '') + f\"\\nConnect {source.name()} to {input_name}.\")",
        "",
        "def build(parent=None):",
        "    matnet = parent or hou.node('/mat')",
        "    if matnet is None:",
        "        raise hou.Error('NodeBridge could not find /mat.')",
        f"    builder = matnet.createNode('materialbuilder', {('NB_' + sanitize_identifier(graph.name))!r})",
        "    principled = None",
        "    for child in builder.children():",
        "        if 'principledshader' in child.type().name():",
        "            principled = child",
        "            break",
        "    if principled is None:",
        "        principled = builder.createNode('principledshader::2.0', 'principled')",
    ]
    noise_var = None
    for operation in graph.operations:
        if operation.kind is OperationKind.SHADER_OPERATION and operation.parameters.get("mode") == "principled":
            color = operation.parameters.get("base_color", (0.8, 0.8, 0.8))
            if not isinstance(color, (list, tuple)):
                color = (0.8, 0.8, 0.8)
            lines.append(f"    _set_tuple(principled, 'basecolor', {tuple(float(c) for c in list(color)[:3])!r})")
            lines.append(f"    _set(principled, 'rough', {float(operation.parameters.get('roughness', 0.5) or 0.5)!r})")
            lines.append(f"    _set(principled, 'metallic', {float(operation.parameters.get('metallic', 0.0) or 0.0)!r})")
            records.append(_record(operation, Confidence.EQUIVALENT, "principledshader::2.0", "Principled BSDF parameters are written onto the principled shader inside the material builder."))
        elif operation.kind is OperationKind.NOISE:
            noise_var = "noise_vop"
            lines.append("    noise_vop = builder.createNode('noise', 'noise')")
            lines.append(f"    _set(noise_vop, 'scale', {float(operation.parameters.get('scale', 5.0) or 5.0)!r})")
            lines.append("    _wire(principled, 'basecolor', noise_vop)")
            records.append(_record(operation, Confidence.APPROXIMATE, "noise VOP", "Houdini noise does not reproduce Blender's noise texture."))
        elif operation.kind is OperationKind.COLOR_OPERATION and operation.parameters.get("mode") == "ramp":
            stops = operation.parameters.get("stops") or []
            lines.append(f"    # Color ramp stops from Blender: {stops!r}")
            lines.append("    ramp = builder.createNode('ramp', 'color_ramp')")
            if noise_var:
                lines.append("    _wire(ramp, 'input', noise_vop)")
            records.append(_record(operation, Confidence.APPROXIMATE, "ramp VOP", "Color ramp stops are recorded in a comment. The ramp VOP uses its default keys unless you edit them."))
        elif operation.kind is OperationKind.SHADER_OPERATION and operation.parameters.get("mode") == "material_output":
            lines.append("    surface = None")
            lines.append("    for child in builder.children():")
            lines.append("        if 'output' in child.type().name() or child.name() == 'surface_output':")
            lines.append("            surface = child")
            lines.append("            break")
            lines.append("    if surface is not None:")
            lines.append("        _wire(surface, 'surface', principled)")
            records.append(_record(operation, Confidence.EXACT, "surface_output", "Material Output connects the principled shader to the surface output."))
        else:
            records.append(_record(operation, Confidence.APPROXIMATE, "comment", f"{operation.kind.value} is kept as a comment in the material script."))
            lines.append(f"    # operation: {operation.id} kind={operation.kind.value} confidence=approximate")
            lines.append(f"    # {operation.name} ({operation.kind.value}) has no dedicated material-builder node in this translator.")
    lines.extend(
        [
            "    builder.layoutChildren()",
            "    return builder",
            "",
            "",
            "if __name__ == '__main__':",
            "    build()",
            "",
        ]
    )
    _ensure_markers(lines, records)
    return "\n".join(lines), records


def _record(operation, confidence: Confidence, implementation: str, explanation: str) -> TranslationRecord:
    return TranslationRecord(
        operation_id=operation.id,
        operation_name=operation.name,
        operation=operation.kind.value,
        classification=Classification(confidence=confidence, explanation=explanation, implementation=implementation),
        source_types=operation.source.node_types,
    )


def _ensure_markers(lines: list[str], records: list[TranslationRecord]) -> None:
    text = "\n".join(lines)
    for record in records:
        marker = f"# operation: {record.operation_id}"
        if marker not in text:
            lines.insert(-4, f"    {marker} kind={record.operation} confidence={record.confidence.value}")
            lines.insert(-4, f"    # {record.classification.explanation}")
