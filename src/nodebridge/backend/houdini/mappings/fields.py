"""Field operations are inlined into the geometry node that consumes them.

They still receive a classification and a comment so the report does not drop them.
"""

from __future__ import annotations

from nodebridge.ir.semantic import OperationKind
from nodebridge.translation.confidence import Confidence
from nodebridge.translation.registry import REGISTRY, Translator


def _note(operation, build) -> None:
    spec = REGISTRY.get(operation.kind, "houdini")
    build.classify(operation, spec)
    if not build.classifications[operation.id].emitted:
        build.note(operation)
        build.notes.append(f"# passthrough: {operation.id} excluded by strictness and inlined as its default where a consumer exists")
        return
    build.note(operation)


_FIELDS = {
    OperationKind.MATH: (Confidence.EXACT, "math", "Scalar math is exact arithmetic inlined into the consuming Attribute Wrangle or parameter."),
    OperationKind.VECTOR_MATH: (Confidence.EXACT, "vex", "Vector math is exact arithmetic inlined into VEX."),
    OperationKind.MAP_RANGE: (Confidence.EXACT, "fit", "Map Range uses the same linear remap as VEX fit()."),
    OperationKind.COMPARE: (Confidence.EXACT, "compare", "Compare is inlined as a boolean expression."),
    OperationKind.BOOLEAN_MATH: (Confidence.EXACT, "boolean", "Boolean math is inlined as a boolean expression."),
    OperationKind.ATTRIBUTE_READ: (Confidence.EXACT, "attribute", "Position, normal, index, and id read the matching Houdini attribute."),
    OperationKind.RANDOM: (
        Confidence.EQUIVALENT,
        "nb_rand",
        "Random values use NodeBridge's hash when deterministic randomness is on, otherwise Houdini rand(). Neither is Blender's sequence.",
    ),
    OperationKind.NOISE: (
        Confidence.APPROXIMATE,
        "noise()",
        "Blender noise and Houdini noise() are different functions. Controls are preserved. The pattern is not numerically identical.",
    ),
    OperationKind.SPATIAL_NOISE_MASK: (
        Confidence.APPROXIMATE,
        "noise mask",
        "A fused noise, map range, and compare becomes a Houdini noise mask. The pattern is not numerically identical.",
    ),
    OperationKind.FIELD: (Confidence.EXACT, "constant", "A constant field is inlined as a literal."),
    OperationKind.COLOR_OPERATION: (
        Confidence.APPROXIMATE,
        "color",
        "Color operations are inlined when a material or attribute consumer can represent them.",
    ),
    OperationKind.ATTRIBUTE_WRITE: (
        Confidence.APPROXIMATE,
        "attribute",
        "Attribute writes are kept as comments unless a downstream wrangle consumes the value.",
    ),
    OperationKind.SELECTION: (Confidence.EQUIVALENT, "group", "Selections are carried as the consuming node's selection input."),
    OperationKind.FILTER: (Confidence.APPROXIMATE, "group", "Filters are approximated by the consuming deletion or split."),
    OperationKind.SAMPLE: (Confidence.APPROXIMATE, "sample", "Sampling is approximated by the consuming proximity or attribute transfer."),
    OperationKind.INTERPOLATE: (Confidence.APPROXIMATE, "fit", "Interpolation falls back to the linear map-range math."),
    OperationKind.CUSTOM_EXPRESSION: (Confidence.EQUIVALENT, "snippet", "A custom expression is emitted as a wrangle comment or snippet."),
    OperationKind.TEXTURE_SAMPLE: (
        Confidence.APPROXIMATE,
        "texture",
        "Texture sampling in a SOP network does not reproduce a shader texture lookup.",
    ),
}


def register() -> None:
    for kind, (confidence, implementation, explanation) in _FIELDS.items():
        if REGISTRY.get(kind, "houdini") is not None:
            continue
        limitations = ()
        if confidence is Confidence.APPROXIMATE and kind is OperationKind.NOISE:
            limitations = ("The noise pattern will not match Blender.",)
        if kind is OperationKind.RANDOM:
            limitations = ("Target random samples may differ from Blender.",)
        REGISTRY.register(
            Translator(
                operation=kind,
                target="houdini",
                confidence=confidence,
                implementation=implementation,
                explanation=explanation,
                limitations=limitations,
                function=_note,
            )
        )
