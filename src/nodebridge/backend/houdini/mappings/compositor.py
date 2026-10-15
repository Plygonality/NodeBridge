"""COP2 scripts for compositor graphs.

Node types are looked up at runtime. A missing type becomes a labeled null
instead of a guessed operator. Glare and masks stay unsupported.
"""

from __future__ import annotations

from nodebridge.common.names import sanitize_identifier
from nodebridge.ir.semantic import OperationKind, SemanticGraph
from nodebridge.translation.confidence import Classification, Confidence, TranslationRecord
from nodebridge.translation.registry import REGISTRY, Translator

_UNSUPPORTED_MODES = {"glare", "ellipse_mask", "box_mask", "filter"}
_COLOR_MODES = {"brightness", "color_balance", "color_correction", "exposure", "hue", "tonemap"}


def register() -> None:
    if REGISTRY.get(OperationKind.COMPOSITOR_OPERATION, "houdini") is None:
        REGISTRY.register(
            Translator(
                operation=OperationKind.COMPOSITOR_OPERATION,
                target="houdini",
                confidence=Confidence.APPROXIMATE,
                implementation="cop2net",
                explanation="Compositor operations become a COP2 network when the node type exists in the running Houdini. Glare and masks are unsupported.",
                limitations=("COP2 node type names vary by Houdini version. Missing types become nulls.",),
                function=_sop_gap,
            )
        )


def _sop_gap(operation, build) -> None:
    spec = REGISTRY.get(OperationKind.COMPOSITOR_OPERATION, "houdini")
    build.classify(
        operation,
        spec,
        confidence=Confidence.UNSUPPORTED,
        explanation="Compositor operations are not SOP nodes.",
    )
    build.passthrough(operation, "Compositor operation inside a geometry graph has no SOP equivalent.")


def generate_cop(graph: SemanticGraph, options) -> tuple[str, list[TranslationRecord]]:
    records: list[TranslationRecord] = []
    name = "NB_" + sanitize_identifier(graph.name)
    lines = [
        '"""NodeBridge Houdini COP2 network.',
        "",
        f"Source: Compositor / {graph.name}",
        "Target: Houdini",
        "",
        "Paste into the Houdini Python Source Editor and run.",
        "This does not recreate Blender's compositor pixel for pixel.",
        "Glare, vignette masks, and missing COP types are labeled nulls.",
        '"""',
        "",
        "import hou",
        "",
        "def _cop(parent, type_name, node_name, comment):",
        "    category = hou.cop2NodeTypeCategory()",
        "    if category.nodeTypes().get(type_name) is None:",
        "        node = parent.createNode('null', node_name)",
        "        node.setComment(comment + ' Missing COP type ' + type_name + '.')",
        "        node.setGenericFlag(hou.nodeFlag.DisplayComment, True)",
        "        return node",
        "    node = parent.createNode(type_name, node_name)",
        "    node.setComment(comment)",
        "    node.setGenericFlag(hou.nodeFlag.DisplayComment, True)",
        "    return node",
        "",
        "def build(parent=None):",
        "    img = parent or hou.node('/img')",
        "    if img is None:",
        "        raise hou.Error('NodeBridge could not find /img.')",
        f"    cop = img.createNode('cop2net', {name!r})",
        "    previous = None",
    ]
    for index, operation in enumerate(graph.operations):
        mode = str(operation.parameters.get("mode", operation.kind.value))
        node_name = sanitize_identifier(operation.name or mode)
        if operation.kind is not OperationKind.COMPOSITOR_OPERATION:
            confidence = Confidence.UNSUPPORTED
            explanation = f"{operation.kind.value} has no compositor equivalent in the Houdini backend."
            cop_type = "null"
        elif mode in _UNSUPPORTED_MODES:
            confidence = Confidence.UNSUPPORTED
            explanation = f"No reliable COP2 equivalent is implemented for {mode}."
            cop_type = "null"
        elif mode in _COLOR_MODES:
            confidence = Confidence.APPROXIMATE
            explanation = "Color correction uses a COP2 color node when that type exists. The controls are not a match for Blender's compositor."
            cop_type = "colorcorrect"
        elif mode == "blur":
            confidence = Confidence.APPROXIMATE
            explanation = "Blur uses the COP2 blur node when it exists."
            cop_type = "blur"
        elif mode in {"render_layer", "image"}:
            confidence = Confidence.EQUIVALENT
            explanation = "The render layer or image becomes a File COP. Assign the image path after generation."
            cop_type = "file"
        elif mode in {"composite_output", "viewer", "file_output"}:
            confidence = Confidence.EXACT
            explanation = "The compositor output is a null with the display flag set."
            cop_type = "null"
        else:
            confidence = Confidence.APPROXIMATE
            explanation = f"{mode} is represented by a labeled COP null because no specific node is mapped."
            cop_type = "null"
        var = f"cop_{index}"
        lines.append(f"    # operation: {operation.id} kind={operation.kind.value} confidence={confidence.value}")
        lines.append(f"    # {explanation}")
        lines.append(f"    {var} = _cop(cop, {cop_type!r}, {node_name!r}, {explanation!r})")
        lines.append("    if previous is not None:")
        lines.append(f"        {var}.setInput(0, previous)")
        if mode in {"composite_output", "viewer"}:
            lines.append(f"    {var}.setDisplayFlag(True)")
        lines.append(f"    previous = {var}")
        records.append(
            TranslationRecord(
                operation_id=operation.id,
                operation_name=operation.name,
                operation=operation.kind.value,
                classification=Classification(confidence=confidence, explanation=explanation, implementation=f"cop2:{cop_type}"),
                source_types=operation.source.node_types,
            )
        )
    lines.extend(["    cop.layoutChildren()", "    return cop", "", "", "if __name__ == '__main__':", "    build()", ""])
    return "\n".join(lines), records
