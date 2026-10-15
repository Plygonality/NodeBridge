"""Houdini SOP translators for geometry operations.

Each function is registered for one semantic operation. Field math is inlined
by the geometry translator that consumes it; those operations are marked in
``fields.py`` so they still appear in the report.
"""

from __future__ import annotations

import math

from nodebridge.backend.houdini.sop import SopNode, SpareParm
from nodebridge.backend.houdini.vex import expression_to_vex, snippet
from nodebridge.common.coordinates import (
    convert_euler,
    convert_euler_axes,
    convert_location,
    convert_scale,
    matrix_to_quaternion,
    rotation_matrix_xyz,
)
from nodebridge.common.names import sanitize_identifier
from nodebridge.common.units import convert_length
from nodebridge.compiler.evaluate import Expr, as_constant
from nodebridge.ir.semantic import OperationKind
from nodebridge.ir.types import DataType
from nodebridge.translation.confidence import Confidence
from nodebridge.translation.registry import REGISTRY, translator


def _spec(kind: OperationKind):
    spec = REGISTRY.get(kind, "houdini")
    if spec is None:
        raise RuntimeError(f"Missing Houdini translator metadata for {kind.value}")
    return spec


def _vec(value, default=(0.0, 0.0, 0.0)):
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return (float(value[0]), float(value[1]), float(value[2]))
    if isinstance(value, (int, float)):
        return (float(value), float(value), float(value))
    return default


def _bind_number(node: SopNode, build, operation, port: str, parm: str, default: float) -> Expr | None:
    mode, payload = build.value(operation, port, default)
    if mode == "exposed":
        node.expressions.append((parm, f'ch("../{sanitize_identifier(str(payload.args[0]))}")'))
        return None
    if mode == "const":
        value = payload if isinstance(payload, (int, float)) else default
        node.parms.append((parm, value))
        return None
    return payload


@translator(
    OperationKind.GROUP_INPUT,
    "houdini",
    confidence=Confidence.EQUIVALENT,
    implementation="object_merge",
    explanation="A geometry group input becomes an Object Merge. Assign Source Object on the container.",
    limitations=("The object path is a Houdini SOP path, not a Blender object datablock.",),
)
def translate_group_input(operation, build) -> None:
    spec = _spec(OperationKind.GROUP_INPUT)
    classification = build.classify(operation, spec)
    if not classification.emitted:
        build.passthrough(operation, classification.fallback or spec.explanation)
        return
    geometry_ports = [name for name, port in operation.outputs.items() if port.role == "geometry"]
    if build.inside_subnet:
        build.prelude.append(f"_group_input = {build.container}.indirectInputs()")
        build.prelude.append("_group_input = _group_input[0] if _group_input else None")
        for name in geometry_ports or ["*"]:
            build.bind(operation.id, "_group_input", name)
        build.note(operation)
        return
    if not geometry_ports:
        build.note(operation)
        return
    var = build.var("geometry_input")
    node = SopNode(
        var=var,
        node_type="object_merge",
        name="geometry_input",
        op_id=operation.id,
        expressions=[("objpath1", 'chs("../source_object")')],
        comment="Assign source_object to the SOP that should feed this network.",
    )
    build.spares.append(SpareParm("string", "source_object", "Source Object", ""))
    build.add(node)
    for name in geometry_ports:
        build.bind(operation.id, var, name)


@translator(
    OperationKind.GROUP_OUTPUT,
    "houdini",
    confidence=Confidence.EXACT,
    implementation="null",
    explanation="The group output is a null SOP with the display and render flags set.",
)
def translate_group_output(operation, build) -> None:
    spec = _spec(OperationKind.GROUP_OUTPUT)
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Output omitted by translation strictness.")
        return
    upstream = build.first_geometry(operation)
    var = build.var("out")
    build.add(
        SopNode(
            var=var,
            node_type="null",
            name="OUT",
            op_id=operation.id,
            inputs=[upstream] if upstream else [],
            display=True,
            render=True,
        )
    )


@translator(
    OperationKind.PRIMITIVE,
    "houdini",
    confidence=Confidence.EXACT,
    implementation="box/grid/sphere/tube/circle/line",
    explanation="Mesh primitives become the matching Houdini generator SOP. Size and radius are converted into Houdini axes.",
)
def translate_primitive(operation, build) -> None:
    spec = _spec(OperationKind.PRIMITIVE)
    kind = str(operation.parameters.get("primitive", "cube"))
    node_type = {
        "cube": "box",
        "grid": "grid",
        "uv_sphere": "sphere",
        "ico_sphere": "sphere",
        "cylinder": "tube",
        "cone": "tube",
        "circle": "circle",
        "line": "line",
    }.get(kind, "box")
    confidence = Confidence.EXACT if kind == "cube" else Confidence.EQUIVALENT
    explanation = spec.explanation if kind == "cube" else f"A Blender {kind} primitive becomes a Houdini {node_type} SOP. Topology and axis orientation can differ."
    if not build.classify(operation, spec, confidence=confidence, explanation=explanation, implementation=node_type).emitted:
        build.passthrough(operation, "Primitive omitted by translation strictness.")
        return
    var = build.var(kind)
    node = SopNode(var=var, node_type=node_type, name=build.node_name(operation), op_id=operation.id)
    size = convert_scale(_vec(operation.parameters.get("size"), (1.0, 1.0, 1.0)), "blender", "houdini")
    radius = convert_length(float(operation.parameters.get("radius", 1.0) or 1.0), "blender", "houdini")
    if node_type == "box":
        node.parm_tuples.append(("size", size))
    elif node_type == "grid":
        node.parms.append(("sizex", size[0]))
        node.parms.append(("sizey", size[2] if abs(size[2]) > 1e-8 else size[1]))
        vertices = _vec(operation.parameters.get("vertices"), (2, 2, 2))
        node.parms.append(("rows", int(vertices[0])))
        node.parms.append(("cols", int(vertices[1])))
    elif node_type == "sphere":
        node.parm_tuples.append(("rad", (radius, radius, radius)))
        node.comment = "Equivalent: Houdini sphere topology is not a Blender UV or icosphere."
    elif node_type == "tube":
        node.parm_tuples.append(("rad", (radius, radius)))
        node.parms.append(("height", convert_length(float(operation.parameters.get("depth", 1.0) or 1.0), "blender", "houdini")))
        node.comment = "Equivalent: cap and end-radius controls are Houdini tube parameters."
    elif node_type == "circle":
        node.parms.append(("radx", radius))
        node.parms.append(("rady", radius))
        node.parms.append(("divs", int(_vec(operation.parameters.get("vertices"), (16, 1, 1))[0])))
    else:
        node.parms.append(("dist", convert_length(float(operation.parameters.get("depth", 1.0) or 1.0), "blender", "houdini")))
    build.add(node, "geometry")


@translator(
    OperationKind.CURVE,
    "houdini",
    confidence=Confidence.EQUIVALENT,
    implementation="circle/line",
    explanation="Curve primitives become Houdini curve generator SOPs. Point count and parameterization can differ.",
)
def translate_curve(operation, build) -> None:
    spec = _spec(OperationKind.CURVE)
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Curve omitted by translation strictness.")
        return
    kind = str(operation.parameters.get("primitive", "circle"))
    node_type = "line" if kind == "line" else "circle"
    var = build.var(kind)
    node = SopNode(var=var, node_type=node_type, name=build.node_name(operation), op_id=operation.id)
    radius = convert_length(float(operation.parameters.get("radius", 1.0) or 1.0), "blender", "houdini")
    if node_type == "circle":
        node.parms.append(("radx", radius))
        node.parms.append(("rady", radius))
        node.parms.append(("divs", int(operation.parameters.get("resolution", 16) or 16)))
        node.comment = "Equivalent: Houdini's circle SOP may default to a primitive curve. Set the type to polygon if you need a polyline."
    build.add(node, "geometry")


@translator(
    OperationKind.TRANSFORM,
    "houdini",
    confidence=Confidence.EXACT,
    implementation="xform",
    explanation="A constant geometry transform becomes a Transform SOP. Rotation is converted from Blender radians into Houdini degrees and axes.",
)
def translate_transform(operation, build) -> None:
    spec = _spec(OperationKind.TRANSFORM)
    mode = str(operation.parameters.get("mode", "geometry"))
    if mode in {"instance_rotation", "instance_scale"}:
        _translate_instance_channel(operation, build, spec, mode)
        return
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Transform omitted by translation strictness.")
        return
    upstream = build.geometry(operation, "geometry") or build.first_geometry(operation)
    translation = _vec(operation.parameters.get("translation"))
    rotation = _vec(operation.parameters.get("rotation"))
    scale = _vec(operation.parameters.get("scale"), (1.0, 1.0, 1.0))
    var = build.var("transform")
    node = SopNode(
        var=var,
        node_type="xform",
        name=build.node_name(operation),
        op_id=operation.id,
        inputs=[upstream] if upstream else [],
    )
    node.parm_tuples.append(("t", convert_location(translation, "blender", "houdini")))
    houdini_euler = convert_euler(rotation, "blender", "houdini")
    node.parm_tuples.append(("r", tuple(math.degrees(component) for component in houdini_euler)))
    node.parm_tuples.append(("s", convert_scale(scale, "blender", "houdini")))
    build.add(node, "geometry")


def _translate_instance_channel(operation, build, spec, mode: str) -> None:
    explanation = "Instance rotation or scale is written to point attributes before Copy to Points."
    if not build.classify(operation, spec, confidence=Confidence.EQUIVALENT, explanation=explanation, implementation="attribwrangle").emitted:
        build.passthrough(operation, "Instance transform omitted by translation strictness.")
        return
    upstream = build.geometry(operation, "geometry") or build.first_geometry(operation)
    body = _attribute_lines(build, operation)
    if not body:
        if upstream:
            build.bind(operation.id, upstream, "geometry")
        build.note(operation)
        return
    var = build.var("instance_variation")
    build.add(
        SopNode(
            var=var,
            node_type="attribwrangle",
            name=build.node_name(operation),
            op_id=operation.id,
            inputs=[upstream] if upstream else [],
            snippet=snippet("\n".join(body), deterministic=build.options.deterministic_random),
        ),
        "geometry",
    )


@translator(
    OperationKind.RANDOM_TRANSFORM,
    "houdini",
    confidence=Confidence.EQUIVALENT,
    implementation="attribwrangle",
    explanation="Random instance variation uses NodeBridge's hash when deterministic randomness is on. It does not reproduce Blender's random series.",
    limitations=("Sample values match the NodeBridge hash, not Blender's Random Value node.",),
)
def translate_random_transform(operation, build) -> None:
    spec = _spec(OperationKind.RANDOM_TRANSFORM)
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Random transform omitted by translation strictness.")
        return
    upstream = build.first_geometry(operation)
    channel = str(operation.parameters.get("channel", "instance_scale"))
    seed = int(operation.parameters.get("seed", 0) or 0)
    minimum = operation.parameters.get("minimum", 0.0)
    maximum = operation.parameters.get("maximum", 1.0)
    if channel == "instance_rotation":
        body = _rotation_lines(minimum, maximum, seed, build.options.deterministic_random)
    else:
        body = _scale_lines(minimum, maximum, seed, build.options.deterministic_random)
    var = build.var("random_transform")
    build.add(
        SopNode(
            var=var,
            node_type="attribwrangle",
            name=build.node_name(operation),
            op_id=operation.id,
            inputs=[upstream] if upstream else [],
            snippet=snippet("\n".join(body), deterministic=build.options.deterministic_random),
            comment="Equivalent: the hash is NodeBridge's, not Blender's.",
        ),
        "geometry",
    )


@translator(
    OperationKind.TRANSFORM_POINTS,
    "houdini",
    confidence=Confidence.EQUIVALENT,
    implementation="attribwrangle",
    explanation="Set Position becomes an Attribute Wrangle that writes P. Offsets are converted into Houdini space.",
)
def translate_transform_points(operation, build) -> None:
    spec = _spec(OperationKind.TRANSFORM_POINTS)
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Set Position omitted by translation strictness.")
        return
    upstream = build.geometry(operation, "geometry") or build.first_geometry(operation)
    offset = convert_location(_vec(operation.parameters.get("offset")), "blender", "houdini")
    position = operation.parameters.get("position")
    lines = []
    if position not in (None, (0.0, 0.0, 0.0), [0.0, 0.0, 0.0]):
        converted = convert_location(_vec(position), "blender", "houdini")
        lines.append(f"@P = set({converted[0]:.6f}, {converted[1]:.6f}, {converted[2]:.6f});")
    else:
        lines.append(f"@P += set({offset[0]:.6f}, {offset[1]:.6f}, {offset[2]:.6f});")
    var = build.var("set_position")
    build.add(
        SopNode(
            var=var,
            node_type="attribwrangle",
            name=build.node_name(operation),
            op_id=operation.id,
            inputs=[upstream] if upstream else [],
            snippet=snippet("\n".join(lines), deterministic=False),
        ),
        "geometry",
    )


@translator(
    OperationKind.MERGE,
    "houdini",
    confidence=Confidence.EXACT,
    implementation="merge",
    explanation="Join Geometry becomes a Merge SOP. Inputs stay in link order.",
)
def translate_merge(operation, build) -> None:
    spec = _spec(OperationKind.MERGE)
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Merge omitted by translation strictness.")
        return
    inputs = []
    for edge in build.graph.incoming(operation.id):
        if edge.to_port.startswith("geometry"):
            source = build._geometry_from_edge(edge.from_operation, edge.from_port)
            if source:
                inputs.append(source)
    var = build.var("merge")
    build.add(SopNode(var=var, node_type="merge", name=build.node_name(operation), op_id=operation.id, inputs=inputs), "geometry")


@translator(
    OperationKind.SCATTER,
    "houdini",
    confidence=Confidence.EQUIVALENT,
    implementation="scatter::2.0",
    explanation="Distribute Points on Faces becomes a Scatter SOP in density mode. Houdini's random distribution is not Blender's, so the same seed does not reproduce the same points.",
    limitations=("Target random samples may differ.", "Poisson disk is not a hard minimum distance."),
)
def translate_scatter(operation, build) -> None:
    spec = _spec(OperationKind.SCATTER)
    mode = str(operation.parameters.get("distribution_mode", "density"))
    confidence = Confidence.APPROXIMATE if mode == "distance" else Confidence.EQUIVALENT
    explanation = spec.explanation
    if mode == "distance":
        explanation = "Poisson disk scatter is approximated with Houdini density scatter. distance_min is not enforced as an exclusion radius."
    if not build.classify(operation, spec, confidence=confidence, explanation=explanation).emitted:
        build.passthrough(operation, "Scatter omitted by translation strictness.")
        return
    upstream = build.geometry(operation, "geometry") or build.first_geometry(operation)
    density_mode, density_payload = build.value(operation, "density", operation.parameters.get("density", 10.0))
    if density_mode == "expr":
        upstream = _density_wrangle(build, operation, upstream, density_payload)
    var = build.var("scatter")
    node = SopNode(
        var=var,
        node_type="scatter::2.0",
        name=build.node_name(operation),
        op_id=operation.id,
        inputs=[upstream] if upstream else [],
        comment=explanation,
    )
    node.parms.append(("forcetotal", 0))
    if density_mode == "expr":
        node.parms.append(("usedensityattrib", 1))
        node.parms.append(("densityattrib", "density"))
        node.parms.append(("densityscale", 1.0))
    elif density_mode == "exposed":
        node.expressions.append(("densityscale", f'ch("../{sanitize_identifier(str(density_payload.args[0]))}")'))
    else:
        node.parms.append(("densityscale", float(density_payload or 0.0)))
    node.parms.append(("seed", int(operation.parameters.get("seed", 0) or 0)))
    if operation.parameters.get("density_attribute"):
        node.parms.append(("usedensityattrib", 1))
        node.parms.append(("densityattrib", str(operation.parameters["density_attribute"])))
    build.add(node, "points")


def _density_wrangle(build, operation, upstream, expr: Expr) -> str:
    var = build.var("density")
    body = f"f@density = {expression_to_vex(expr, deterministic=build.options.deterministic_random)};"
    build.add(
        SopNode(
            var=var,
            node_type="attribwrangle",
            name="density",
            op_id=operation.id,
            inputs=[upstream] if upstream else [],
            snippet=snippet(body, deterministic=build.options.deterministic_random),
        )
    )
    return var


@translator(
    OperationKind.INSTANCE,
    "houdini",
    confidence=Confidence.EQUIVALENT,
    implementation="copytopoints::2.0",
    explanation="Instance on Points becomes Copy to Points. The first input is the instance geometry and the second input is the points. Scale and rotation are point attributes.",
    limitations=("Packed instance pivots follow Copy to Points, which is not identical to Blender's instance transform.",),
)
def translate_instance(operation, build) -> None:
    spec = _spec(OperationKind.INSTANCE)
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Instance omitted by translation strictness.")
        return
    points = build.geometry(operation, "points") or build.first_geometry(operation)
    instance = build.geometry(operation, "instance")
    points = _variation_wrangle(build, operation, points)
    var = build.var("instance")
    node = SopNode(
        var=var,
        node_type="copytopoints::2.0",
        name=build.node_name(operation),
        op_id=operation.id,
        inputs=[instance, points],
        comment="Input 0 is the geometry to copy. Input 1 is the points.",
    )
    build.add(node, "instances")


def _variation_wrangle(build, operation, points: str | None) -> str | None:
    body = _attribute_lines(build, operation)
    if not body:
        return points
    var = build.var("variation")
    build.add(
        SopNode(
            var=var,
            node_type="attribwrangle",
            name="instance_variation",
            op_id=operation.id,
            inputs=[points] if points else [],
            snippet=snippet("\n".join(body), deterministic=build.options.deterministic_random),
            comment="Equivalent: random values use the selected NodeBridge or Houdini random, not Blender's sequence.",
        )
    )
    return var


def _attribute_lines(build, operation) -> list[str]:
    lines = []
    scale_mode, scale_payload = build.value(operation, "scale", operation.parameters.get("scale", (1.0, 1.0, 1.0)))
    if scale_mode == "expr":
        lines.extend(_scale_expr(scale_payload, build.options.deterministic_random))
    elif scale_mode == "const" and _vec(scale_payload, (1.0, 1.0, 1.0)) != (1.0, 1.0, 1.0):
        converted = convert_scale(_vec(scale_payload, (1.0, 1.0, 1.0)), "blender", "houdini")
        lines.append(f"@scale = set({converted[0]:.6f}, {converted[1]:.6f}, {converted[2]:.6f});")
    rotation_mode, rotation_payload = build.value(operation, "rotation", operation.parameters.get("rotation", (0.0, 0.0, 0.0)))
    if rotation_mode == "expr":
        lines.extend(_rotation_expr(rotation_payload, build.options.deterministic_random))
    elif rotation_mode == "const" and _vec(rotation_payload) != (0.0, 0.0, 0.0):
        euler = convert_euler(_vec(rotation_payload), "blender", "houdini")
        quat = matrix_to_quaternion(rotation_matrix_xyz(euler))
        lines.append(f"@orient = set({quat[0]:.6f}, {quat[1]:.6f}, {quat[2]:.6f}, {quat[3]:.6f});")
    return lines


def _scale_expr(expr: Expr, deterministic: bool) -> list[str]:
    if expr.op == "random" and "vector" not in str(expr.args[0]):
        minimum = as_constant(expr.args[1]) if len(expr.args) > 1 else 0.0
        maximum = as_constant(expr.args[2]) if len(expr.args) > 2 else 1.0
        unit = expression_to_vex(expr, deterministic=deterministic)
        return [f"@pscale = lerp({float(minimum or 0):.6f}, {float(maximum or 1):.6f}, {unit});"]
    if expr.op == "random":
        return _scale_lines(expr.args[1], expr.args[2], expr.args[3] if len(expr.args) > 3 else 0, deterministic)
    return [f"@scale = {expression_to_vex(expr, deterministic=deterministic)};"]


def _scale_lines(minimum, maximum, seed, deterministic: bool) -> list[str]:
    mins = _vec(as_constant(minimum) if isinstance(minimum, Expr) else minimum, (0.0, 0.0, 0.0))
    maxs = _vec(as_constant(maximum) if isinstance(maximum, Expr) else maximum, (1.0, 1.0, 1.0))
    seed_text = expression_to_vex(seed, deterministic=deterministic) if isinstance(seed, Expr) else f"{float(as_constant(seed) or 0):.0f}"
    if deterministic:
        return [
            f"float _sx = lerp({mins[0]:.6f}, {maxs[0]:.6f}, nb_rand(int({seed_text}) + 11, @ptnum));",
            f"float _sy = lerp({mins[1]:.6f}, {maxs[1]:.6f}, nb_rand(int({seed_text}) + 29, @ptnum));",
            f"float _sz = lerp({mins[2]:.6f}, {maxs[2]:.6f}, nb_rand(int({seed_text}) + 47, @ptnum));",
            "@scale = set(_sx, _sy, _sz);",
        ]
    return [
        f"float _sx = lerp({mins[0]:.6f}, {maxs[0]:.6f}, rand(@ptnum + ({seed_text}) + 11));",
        f"float _sy = lerp({mins[1]:.6f}, {maxs[1]:.6f}, rand(@ptnum + ({seed_text}) + 29));",
        f"float _sz = lerp({mins[2]:.6f}, {maxs[2]:.6f}, rand(@ptnum + ({seed_text}) + 47));",
        "@scale = set(_sx, _sy, _sz);",
    ]


def _rotation_expr(expr: Expr, deterministic: bool) -> list[str]:
    if expr.op == "random":
        return ["// Random euler components are remapped onto Houdini axes, then interpolated.", *_rotation_lines_from_expr(expr, deterministic)]
    return [f"// Field rotation is written as a Houdini euler in radians.\n@orient = {expression_to_vex(expr, deterministic=deterministic)};"]


def _rotation_lines_from_expr(expr: Expr, deterministic: bool) -> list[str]:
    minimum = as_constant(expr.args[1]) if len(expr.args) > 1 else (0, 0, 0)
    maximum = as_constant(expr.args[2]) if len(expr.args) > 2 else (0, 0, 0)
    seed = expr.args[3] if len(expr.args) > 3 else 0
    return _rotation_lines(minimum, maximum, seed, deterministic)


def _rotation_lines(minimum, maximum, seed, deterministic: bool = True) -> list[str]:
    start = convert_euler_axes(_vec(as_constant(minimum) if isinstance(minimum, Expr) else minimum), "blender", "houdini")
    end = convert_euler_axes(_vec(as_constant(maximum) if isinstance(maximum, Expr) else maximum), "blender", "houdini")
    seed_text = expression_to_vex(seed, deterministic=deterministic) if isinstance(seed, Expr) else str(int(seed or 0))
    if deterministic:
        sample = lambda offset: f"nb_rand(int({seed_text}) + {offset}, @ptnum)"
    else:
        sample = lambda offset: f"rand(@ptnum + ({seed_text}) + {offset})"
    return [
        _EULER_TO_ORIENT,
        f"float _rx = lerp({start[0]:.6f}, {end[0]:.6f}, {sample(11)});",
        f"float _ry = lerp({start[1]:.6f}, {end[1]:.6f}, {sample(29)});",
        f"float _rz = lerp({start[2]:.6f}, {end[2]:.6f}, {sample(47)});",
        "@orient = nb_euler_to_orient(_rx, _ry, _rz);",
    ]


_EULER_TO_ORIENT = """
vector4 nb_euler_to_orient(float x; float y; float z) {
    float cx = cos(x * 0.5);
    float sx = sin(x * 0.5);
    float cy = cos(y * 0.5);
    float sy = sin(y * 0.5);
    float cz = cos(z * 0.5);
    float sz = sin(z * 0.5);
    return set(
        sx * cy * cz - cx * sy * sz,
        cx * sy * cz + sx * cy * sz,
        cx * cy * sz - sx * sy * cz,
        cx * cy * cz + sx * sy * sz
    );
}
""".strip()


@translator(
    OperationKind.REALIZE_INSTANCES,
    "houdini",
    confidence=Confidence.EQUIVALENT,
    implementation="unpack",
    explanation="Realize Instances becomes Unpack. Copy to Points has already applied instance transforms.",
)
def translate_realize(operation, build) -> None:
    spec = _spec(OperationKind.REALIZE_INSTANCES)
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Realize omitted by translation strictness.")
        return
    upstream = build.first_geometry(operation)
    var = build.var("realize")
    build.add(
        SopNode(var=var, node_type="unpack", name=build.node_name(operation), op_id=operation.id, inputs=[upstream] if upstream else []),
        "geometry",
    )


@translator(
    OperationKind.EXTRUDE,
    "houdini",
    confidence=Confidence.EQUIVALENT,
    implementation="polyextrude::2.0",
    explanation="Extrude Mesh becomes Poly Extrude. The offset vector is reduced to a distance along the Houdini extrude.",
    limitations=("Individual face insets and Blender's offset vector are not fully reproduced.",),
)
def translate_extrude(operation, build) -> None:
    spec = _spec(OperationKind.EXTRUDE)
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Extrude omitted by translation strictness.")
        return
    upstream = build.first_geometry(operation)
    offset = convert_location(_vec(operation.parameters.get("offset"), (0.0, 0.0, 1.0)), "blender", "houdini")
    distance = math.sqrt(sum(component * component for component in offset)) * float(operation.parameters.get("offset_scale", 1.0) or 1.0)
    var = build.var("extrude")
    node = SopNode(
        var=var,
        node_type="polyextrude::2.0",
        name=build.node_name(operation),
        op_id=operation.id,
        inputs=[upstream] if upstream else [],
        parms=[("dist", distance)],
        comment="Equivalent: distance is the length of the converted offset.",
    )
    build.add(node, "geometry")


@translator(
    OperationKind.SUBDIVIDE,
    "houdini",
    confidence=Confidence.EQUIVALENT,
    implementation="subdivide",
    explanation="Subdivide Mesh becomes one Subdivide SOP per level, capped at six.",
)
def translate_subdivide(operation, build) -> None:
    spec = _spec(OperationKind.SUBDIVIDE)
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Subdivide omitted by translation strictness.")
        return
    upstream = build.first_geometry(operation)
    levels = max(1, min(6, int(operation.parameters.get("level", 1) or 1)))
    var = upstream
    last = None
    for index in range(levels):
        last = build.var("subdivide")
        build.add(
            SopNode(
                var=last,
                node_type="subdivide",
                name=f"{build.node_name(operation)}_{index + 1}",
                op_id=operation.id,
                inputs=[var] if var else [],
            ),
            "geometry",
        )
        var = last


@translator(
    OperationKind.DELETE_GEOMETRY,
    "houdini",
    confidence=Confidence.EQUIVALENT,
    implementation="blast",
    explanation="Delete Geometry becomes a Blast SOP. A selection field is written to a point or primitive group first.",
)
def translate_delete(operation, build) -> None:
    spec = _spec(OperationKind.DELETE_GEOMETRY)
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Delete omitted by translation strictness.")
        return
    upstream = build.first_geometry(operation)
    var = build.var("delete")
    node = SopNode(
        var=var,
        node_type="blast",
        name=build.node_name(operation),
        op_id=operation.id,
        inputs=[upstream] if upstream else [],
        parms=[("group", "*")],
        comment="Equivalent: without a compiled selection group, Blast is created for the whole input. Narrow the group after generation if needed.",
    )
    build.add(node, "geometry")


@translator(
    OperationKind.SEPARATE,
    "houdini",
    confidence=Confidence.APPROXIMATE,
    implementation="split",
    explanation="Separate Geometry becomes a Split SOP. The two outputs are not a perfect match for Blender's selection and inverted domains.",
)
def translate_separate(operation, build) -> None:
    spec = _spec(OperationKind.SEPARATE)
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Separate omitted by translation strictness.")
        return
    upstream = build.first_geometry(operation)
    var = build.var("separate")
    node = SopNode(
        var=var,
        node_type="split",
        name=build.node_name(operation),
        op_id=operation.id,
        inputs=[upstream] if upstream else [],
        comment="Approximate: connect the group that should define the split.",
    )
    build.add(node, "selected")
    build.bind(operation.id, var, "inverted")


@translator(
    OperationKind.CURVE_RESAMPLE,
    "houdini",
    confidence=Confidence.EQUIVALENT,
    implementation="resample",
    explanation="Resample Curve becomes a Resample SOP using segment length.",
)
def translate_resample(operation, build) -> None:
    spec = _spec(OperationKind.CURVE_RESAMPLE)
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Resample omitted by translation strictness.")
        return
    upstream = build.first_geometry(operation)
    var = build.var("resample")
    length = convert_length(float(operation.parameters.get("length", 0.1) or 0.1), "blender", "houdini")
    build.add(
        SopNode(
            var=var,
            node_type="resample",
            name=build.node_name(operation),
            op_id=operation.id,
            inputs=[upstream] if upstream else [],
            parms=[("length", length)],
        ),
        "geometry",
    )


@translator(
    OperationKind.CURVE_TO_MESH,
    "houdini",
    confidence=Confidence.EQUIVALENT,
    implementation="sweep::2.0",
    explanation="Curve to Mesh becomes a Sweep. A circle is created when no profile curve is connected.",
)
def translate_curve_to_mesh(operation, build) -> None:
    spec = _spec(OperationKind.CURVE_TO_MESH)
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Curve to Mesh omitted by translation strictness.")
        return
    curve = build.geometry(operation, "curve") or build.first_geometry(operation)
    profile = build.geometry(operation, "profile")
    if profile is None:
        profile = build.var("profile")
        build.add(
            SopNode(
                var=profile,
                node_type="circle",
                name="sweep_profile",
                op_id=operation.id,
                parms=[("radx", 0.1), ("rady", 0.1), ("divs", 8)],
            )
        )
    var = build.var("sweep")
    build.add(
        SopNode(
            var=var,
            node_type="sweep::2.0",
            name=build.node_name(operation),
            op_id=operation.id,
            inputs=[curve, profile],
        ),
        "geometry",
    )


@translator(
    OperationKind.MESH_TO_CURVE,
    "houdini",
    confidence=Confidence.APPROXIMATE,
    implementation="convert",
    explanation="Mesh to Curve has no single exact SOP. A Convert SOP is created so the conversion type can be set in Houdini.",
    limitations=("The Convert SOP target menu is not set, because the menu index is version-dependent.",),
)
def translate_mesh_to_curve(operation, build) -> None:
    spec = _spec(OperationKind.MESH_TO_CURVE)
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Mesh to Curve omitted by translation strictness.")
        return
    upstream = build.first_geometry(operation)
    var = build.var("mesh_to_curve")
    build.add(
        SopNode(
            var=var,
            node_type="convert",
            name=build.node_name(operation),
            op_id=operation.id,
            inputs=[upstream] if upstream else [],
            comment="Approximate: set the conversion target to a polygon curve.",
        ),
        "geometry",
    )


@translator(
    OperationKind.RAYCAST,
    "houdini",
    confidence=Confidence.EQUIVALENT,
    implementation="ray",
    explanation="Raycast becomes a Ray SOP. Hit attributes follow Houdini's ray result, not Blender's named outputs.",
)
def translate_raycast(operation, build) -> None:
    spec = _spec(OperationKind.RAYCAST)
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Raycast omitted by translation strictness.")
        return
    target = build.geometry(operation, "target")
    source = build.first_geometry(operation)
    var = build.var("raycast")
    build.add(
        SopNode(var=var, node_type="ray", name=build.node_name(operation), op_id=operation.id, inputs=[source, target]),
        "geometry",
    )


@translator(
    OperationKind.PROXIMITY,
    "houdini",
    confidence=Confidence.EQUIVALENT,
    implementation="attribwrangle xyzdist",
    explanation="Geometry Proximity becomes xyzdist in an Attribute Wrangle. The distance is equivalent, not a copy of Blender's proximity node.",
)
def translate_proximity(operation, build) -> None:
    spec = _spec(OperationKind.PROXIMITY)
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Proximity omitted by translation strictness.")
        return
    target = build.geometry(operation, "target")
    source = build.first_geometry(operation)
    var = build.var("proximity")
    body = "int prim;\nvector uv;\nf@distance = xyzdist(1, @P, prim, uv);\nv@closest = primuv(1, 'P', prim, uv);"
    build.add(
        SopNode(
            var=var,
            node_type="attribwrangle",
            name=build.node_name(operation),
            op_id=operation.id,
            inputs=[source, target],
            snippet=snippet(body, deterministic=False),
        ),
        "geometry",
    )


@translator(
    OperationKind.BOOLEAN,
    "houdini",
    confidence=Confidence.EQUIVALENT,
    implementation="boolean::2.0",
    explanation="Mesh Boolean becomes a Boolean SOP. Non-manifold results can differ from Blender's exact solver.",
)
def translate_boolean(operation, build) -> None:
    spec = _spec(OperationKind.BOOLEAN)
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Boolean omitted by translation strictness.")
        return
    first = build.geometry(operation, "a") or build.first_geometry(operation)
    second = build.geometry(operation, "b")
    mapping = {"union": 0, "intersect": 1, "difference": 2}
    var = build.var("boolean")
    build.add(
        SopNode(
            var=var,
            node_type="boolean::2.0",
            name=build.node_name(operation),
            op_id=operation.id,
            inputs=[first, second],
            parms=[("booleanop", mapping.get(str(operation.parameters.get("operation", "difference")), 2))],
            comment="Equivalent: booleanop menu 0 union, 1 intersect, 2 subtract. Confirm the menu in this Houdini version.",
        ),
        "geometry",
    )


@translator(
    OperationKind.MATERIAL_ASSIGNMENT,
    "houdini",
    confidence=Confidence.EQUIVALENT,
    implementation="material",
    explanation="Set Material becomes a Material SOP. The material path is /mat/<name> and the material itself is not rebuilt unless the source was a shader graph.",
)
def translate_material(operation, build) -> None:
    spec = _spec(OperationKind.MATERIAL_ASSIGNMENT)
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Material assignment omitted by translation strictness.")
        return
    upstream = build.first_geometry(operation)
    material = str(operation.parameters.get("material") or operation.name or "material")
    path = "/mat/" + sanitize_identifier(material)
    var = build.var("material")
    build.add(
        SopNode(
            var=var,
            node_type="material",
            name=build.node_name(operation),
            op_id=operation.id,
            inputs=[upstream] if upstream else [],
            parms=[("shop_materialpath1", path)],
            comment="Equivalent: create the material at this path or retarget the parameter.",
        ),
        "geometry",
    )


@translator(
    OperationKind.SWITCH,
    "houdini",
    confidence=Confidence.EQUIVALENT,
    implementation="switch",
    explanation="A constant Switch becomes a Switch SOP. A field switch is approximate because the SOP switch is not per element.",
)
def translate_switch(operation, build) -> None:
    spec = _spec(OperationKind.SWITCH)
    mode, payload = build.value(operation, "switch", operation.parameters.get("switch", False))
    if mode != "const":
        build.classify(
            operation,
            spec,
            confidence=Confidence.APPROXIMATE,
            explanation="The switch condition is a field. The false input is passed through and the condition is kept in the comment.",
        )
        build.passthrough(operation, "Approximate field switch. The false branch is connected.")
        return
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Switch omitted by translation strictness.")
        return
    false_input = build.geometry(operation, "false")
    true_input = build.geometry(operation, "true")
    var = build.var("switch")
    build.add(
        SopNode(
            var=var,
            node_type="switch",
            name=build.node_name(operation),
            op_id=operation.id,
            inputs=[false_input, true_input],
            parms=[("input", 1 if payload else 0)],
        ),
        "output",
    )


@translator(
    OperationKind.SUBGRAPH,
    "houdini",
    confidence=Confidence.EQUIVALENT,
    implementation="subnet",
    explanation="A node group becomes a subnet. The first geometry input is the subnet input. Interface values become spare parameters on the subnet.",
    limitations=("Only the first geometry input is wired as a subnet indirect input.",),
)
def translate_subgraph(operation, build) -> None:
    from nodebridge.backend.houdini.backend import _promote, populate
    from nodebridge.backend.houdini.generators import render_nodes
    from nodebridge.backend.houdini.sop import SubnetNode

    spec = _spec(OperationKind.SUBGRAPH)
    if not build.classify(operation, spec).emitted:
        build.passthrough(operation, "Subnet omitted by translation strictness.")
        return
    upstream = build.first_geometry(operation)
    var = build.var("subnet")
    inner = type(build)(operation.subgraph, build.options, container=var, inside_subnet=True)
    populate(inner)
    _promote(inner)
    inner_lines = []
    for line in inner.prelude:
        inner_lines.append(line)
    for note in inner.notes:
        inner_lines.extend(note.splitlines())
    inner_lines.extend(line[4:] if line.startswith("    ") else line for line in _inner_spares(inner))
    for line in render_nodes(inner, var, indent=""):
        inner_lines.append(line)
    build.nodes.append(SubnetNode(var=var, name=build.node_name(operation), op_id=operation.id, inputs=[upstream] if upstream else [], inner_lines=inner_lines))
    build.bind(operation.id, var, "*")
    build.nested = getattr(build, "nested", {})
    build.nested[operation.id] = inner


def _inner_spares(inner) -> list[str]:
    from nodebridge.backend.houdini.generators import _spare_lines

    return _spare_lines(inner.spares, inner.container)


@translator(
    OperationKind.UNSUPPORTED,
    "houdini",
    confidence=Confidence.UNSUPPORTED,
    implementation="null",
    explanation="No Houdini semantic translation is registered for this operation.",
    fallback="passthrough null so downstream nodes keep a connection",
)
def translate_unsupported(operation, build) -> None:
    spec = _spec(OperationKind.UNSUPPORTED)
    reason = str(operation.parameters.get("reason") or spec.explanation)
    build.classify(operation, spec, explanation=reason, fallback=spec.fallback)
    build.passthrough(operation, reason)
