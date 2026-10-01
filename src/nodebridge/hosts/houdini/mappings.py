"""Houdini SOP ↔ semantic operation mappings.

Native SOP types are provenance, not IR operations. VEX is used only when
a native SOP cannot express the semantics, and is classified CUSTOM_CODE.
"""

from __future__ import annotations

from nodebridge.core.diagnostics import TranslationStatus
from nodebridge.core.node import IRNode
from nodebridge.core.values import JSONValue
from nodebridge.hosts.native import NativeGraph, NativeNode
from nodebridge.hosts.recipes import NodeTemplate, Recipe
from nodebridge.hosts.houdini.vex import vex_for_math, vex_for_vector, vex_for_modify_position

STATIC_OPERATIONS = {
    "null": "graph.input",
    "scatter": "points.distribute",
    "scatter::2.0": "points.distribute",
    "copytopoints": "geometry.instance",
    "copytopoints::2.0": "geometry.instance",
    "unpack": "geometry.realize_instances",
    "xform": "geometry.transform",
    "xformpoints": "geometry.transform",
    "merge": "geometry.join",
    "blast": "geometry.delete",
    "delete": "geometry.delete",
    "split": "geometry.separate",
    "attribrandomize": "random.float",
    "attribrandomize::2.0": "random.float",
    "box": "geometry.primitive",
    "sphere": "geometry.primitive",
    "grid": "geometry.primitive",
    "circle": "geometry.primitive",
    "tube": "geometry.primitive",
    "attribcreate": "attribute.write",
    "attribpromote": "attribute.transfer",
}

PRIMITIVE_KINDS = {
    "box": "cube",
    "sphere": "sphere",
    "grid": "grid",
    "circle": "circle",
    "tube": "cylinder",
}


def resolve_houdini_node(node: NativeNode, graph: NativeGraph) -> tuple[str, dict[str, object]]:
    """Return ``(semantic_operation, extras)`` for a SOP node."""
    extras: dict[str, object] = {}
    sop_type = node.type.split("/")[-1]
    role = str(node.parameters.get("role") or "")
    if sop_type == "null" and role == "output":
        return "graph.output", extras
    if sop_type == "null":
        incoming = graph.incoming(node.id)
        if incoming:
            return "unknown", extras
        return "graph.input", extras
    if sop_type.startswith("attribrandomize"):
        attr = str(node.parameters.get("attrname") or node.parameters.get("name") or "pscale")
        extras["parameters"] = {"name": attr}
        if "vector" in str(node.parameters.get("type") or "").lower() or attr.lower() in {
            "p",
            "cd",
            "orient",
            "n",
            "v",
            "pscale",
        } or "scale" in attr.lower():
            return "random.vector", extras
        if "int" in str(node.parameters.get("type") or "").lower():
            return "random.integer", extras
        return "random.float", extras
    if sop_type in PRIMITIVE_KINDS:
        extras["parameters"] = {"primitive": PRIMITIVE_KINDS[sop_type]}
        return "geometry.primitive", extras
    if sop_type in STATIC_OPERATIONS:
        return STATIC_OPERATIONS[sop_type], extras
    if sop_type in {"attribwrangle", "pointwrangle", "attribvop"}:
        return "unknown", extras
    return "unknown", extras


def _params(node: IRNode) -> dict[str, JSONValue]:
    values = {name: parameter.value for name, parameter in node.parameters.items()}
    for socket in node.inputs.values():
        if socket.default is not None and socket.name not in values:
            values[socket.name] = socket.default
    return values


def _scatter_params(node: IRNode) -> dict[str, JSONValue]:
    values = _params(node)
    if "density" in values and "npts" not in values:
        try:
            values["npts"] = int(float(values["density"]) * 10)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            values["npts"] = 100
    values.setdefault("npts", 100)
    values.setdefault("seed", values.get("seed", 0))
    return values


def _recipe(
    operation: str,
    native_type: str,
    *,
    fidelity: TranslationStatus = TranslationStatus.EXACT,
    inputs: tuple[str, ...] = ("input0",),
    outputs: tuple[str, ...] = ("output0",),
    expose_inputs: dict[str, tuple[str, str]] | None = None,
    expose_outputs: dict[str, tuple[str, str]] | None = None,
    note: str = "",
    parameter_builder=None,
    extra_nodes: tuple[NodeTemplate, ...] = (),
    extra_links: tuple[tuple[str, str, str, str], ...] = (),
    code_kind: str = "",
    code: str = "",
) -> Recipe:
    nodes = (
        NodeTemplate(local_id="node", native_type=native_type, inputs=inputs, outputs=outputs),
        *extra_nodes,
    )
    return Recipe(
        operation=operation,
        fidelity=fidelity,
        nodes=nodes,
        links=extra_links,
        expose_inputs=expose_inputs or {"geometry": ("node", inputs[0] if inputs else "input0")},
        expose_outputs=expose_outputs
        or {"geometry": ("node", outputs[0] if outputs else "output0")},
        note=note,
        parameter_builder=parameter_builder,
        code_kind=code_kind,
        code=code,
    )


def _math_recipe(operation: str) -> Recipe:
    vex = vex_for_math(operation)

    def builder(node: IRNode) -> dict[str, JSONValue]:
        snippet = vex_for_math(operation, node)
        return {"snippet": snippet}

    return Recipe(
        operation=operation,
        fidelity=TranslationStatus.CUSTOM_CODE,
        nodes=(
            NodeTemplate(
                local_id="wrangle",
                native_type="attribwrangle",
                inputs=("input0",),
                outputs=("output0",),
            ),
        ),
        expose_inputs={"a": ("wrangle", "input0"), "b": ("wrangle", "input0"), "geometry": ("wrangle", "input0")},
        expose_outputs={"value": ("wrangle", "output0"), "geometry": ("wrangle", "output0")},
        note="Houdini has no general scalar math SOP; an Attribute Wrangle implements the operation.",
        code_kind="vex",
        code=vex,
        parameter_builder=builder,
    )


def _vector_recipe(operation: str) -> Recipe:
    vex = vex_for_vector(operation)

    def builder(node: IRNode) -> dict[str, JSONValue]:
        return {"snippet": vex_for_vector(operation, node)}

    output_name = "value" if operation in {"vector.dot", "vector.distance"} else "vector"
    return Recipe(
        operation=operation,
        fidelity=TranslationStatus.CUSTOM_CODE,
        nodes=(
            NodeTemplate(
                local_id="wrangle",
                native_type="attribwrangle",
                inputs=("input0",),
                outputs=("output0",),
            ),
        ),
        expose_inputs={
            "a": ("wrangle", "input0"),
            "b": ("wrangle", "input0"),
            "vector": ("wrangle", "input0"),
            "scale": ("wrangle", "input0"),
            "geometry": ("wrangle", "input0"),
        },
        expose_outputs={output_name: ("wrangle", "output0"), "geometry": ("wrangle", "output0")},
        note="Vector field math is implemented as a deterministic Attribute Wrangle.",
        code_kind="vex",
        code=vex,
        parameter_builder=builder,
    )


HOUDINI_RECIPES: dict[str, Recipe] = {
    "graph.input": _recipe(
        "graph.input",
        "null",
        inputs=(),
        outputs=("output0",),
        expose_inputs={},
        expose_outputs={"geometry": ("node", "output0")},
        parameter_builder=lambda node: {"role": "input", "label": node.id},
    ),
    "graph.output": _recipe(
        "graph.output",
        "null",
        inputs=("input0",),
        outputs=(),
        expose_inputs={"geometry": ("node", "input0")},
        expose_outputs={},
        parameter_builder=lambda node: {"role": "output", "label": node.id},
    ),
    "geometry.transform": _recipe(
        "geometry.transform",
        "xform",
        inputs=("input0",),
        outputs=("output0",),
        expose_inputs={
            "geometry": ("node", "input0"),
            "translation": ("node", "t"),
            "rotation": ("node", "r"),
            "scale": ("node", "s"),
        },
        parameter_builder=_params,
    ),
    "geometry.join": _recipe(
        "geometry.join",
        "merge",
        inputs=("input0", "input1"),
        outputs=("output0",),
        expose_inputs={"geometry": ("node", "input0"), "geometry_001": ("node", "input1")},
    ),
    "geometry.separate": _recipe(
        "geometry.separate",
        "split",
        inputs=("input0",),
        outputs=("output0", "output1"),
        expose_outputs={"true": ("node", "output0"), "false": ("node", "output1")},
        fidelity=TranslationStatus.LOWERED,
        note="Split SOP approximates separate-geometry; group/selection semantics may differ.",
    ),
    "geometry.realize_instances": Recipe(
        operation="geometry.realize_instances",
        fidelity=TranslationStatus.LOWERED,
        nodes=(
            NodeTemplate(local_id="unpack", native_type="unpack", inputs=("input0",), outputs=("output0",)),
            NodeTemplate(
                local_id="convert",
                native_type="convert",
                inputs=("input0",),
                outputs=("output0",),
            ),
        ),
        links=(("unpack", "output0", "convert", "input0"),),
        expose_inputs={"geometry": ("unpack", "input0")},
        expose_outputs={"geometry": ("convert", "output0")},
        note="Packed instances unpack then convert into explicit geometry.",
    ),
    "geometry.instance": Recipe(
        operation="geometry.instance",
        fidelity=TranslationStatus.LOWERED,
        nodes=(
            NodeTemplate(
                local_id="copy",
                native_type="copytopoints",
                inputs=("input0", "input1"),
                outputs=("output0",),
            ),
        ),
        expose_inputs={
            "instance": ("copy", "input0"),
            "points": ("copy", "input1"),
            "scale": ("copy", "input1"),
            "rotation": ("copy", "input1"),
        },
        expose_outputs={"instances": ("copy", "output0"), "geometry": ("copy", "output0")},
        note="Copy to Points instances the template onto points; scale/rotation use point attributes when wired.",
        parameter_builder=_params,
    ),
    "points.distribute": _recipe(
        "points.distribute",
        "scatter",
        inputs=("input0",),
        outputs=("output0",),
        expose_inputs={"geometry": ("node", "input0"), "density": ("node", "density"), "seed": ("node", "seed")},
        expose_outputs={"points": ("node", "output0"), "geometry": ("node", "output0")},
        parameter_builder=_scatter_params,
    ),
    "geometry.primitive": _recipe(
        "geometry.primitive",
        "box",
        inputs=(),
        outputs=("output0",),
        expose_inputs={},
        parameter_builder=_params,
    ),
    "geometry.delete": _recipe(
        "geometry.delete",
        "blast",
        expose_inputs={"geometry": ("node", "input0"), "selection": ("node", "group")},
        parameter_builder=_params,
    ),
    "random.float": _recipe(
        "random.float",
        "attribrandomize",
        expose_inputs={"min": ("node", "min"), "max": ("node", "max"), "seed": ("node", "seed"), "geometry": ("node", "input0")},
        expose_outputs={"value": ("node", "output0"), "geometry": ("node", "output0")},
        parameter_builder=lambda node: {**_params(node), "attrname": "value"},
    ),
    "random.integer": _recipe(
        "random.integer",
        "attribrandomize",
        parameter_builder=lambda node: {**_params(node), "attrname": "value", "type": "integer"},
        expose_outputs={"value": ("node", "output0")},
    ),
    "random.vector": Recipe(
        operation="random.vector",
        fidelity=TranslationStatus.LOWERED,
        nodes=(
            NodeTemplate(
                local_id="randomize",
                native_type="attribrandomize",
                inputs=("input0",),
                outputs=("output0",),
            ),
            NodeTemplate(
                local_id="bind",
                native_type="attribwrangle",
                inputs=("input0",),
                outputs=("output0",),
            ),
        ),
        links=(("randomize", "output0", "bind", "input0"),),
        expose_inputs={
            "min": ("randomize", "min"),
            "max": ("randomize", "max"),
            "seed": ("randomize", "seed"),
            "id": ("randomize", "seed"),
            "geometry": ("randomize", "input0"),
        },
        expose_outputs={"vector": ("bind", "output0"), "geometry": ("bind", "output0")},
        note="Attribute Randomize writes a vector attribute; a wrangle binds it to pscale when used as instance scale.",
        code_kind="vex",
        code="f@pscale = length(v@value);\n",
        parameter_builder=lambda node: {
            "randomize": {**_params(node), "attrname": "value", "type": "vector"},
            "bind": {"snippet": "f@pscale = length(v@value);\nv@scale = v@value;"},
        },
    ),
    "geometry.modify_position": _recipe(
        "geometry.modify_position",
        "attribwrangle",
        fidelity=TranslationStatus.CUSTOM_CODE,
        note="Set Position with a field has no dedicated SOP; a Point Wrangle writes @P.",
        code_kind="vex",
        code=vex_for_modify_position(),
        parameter_builder=lambda node: {"snippet": vex_for_modify_position(node)},
    ),
    "attribute.read": _recipe(
        "attribute.read",
        "null",
        note="Named attribute read is a no-op passthrough; the attribute already lives on the geometry.",
        fidelity=TranslationStatus.APPROXIMATE,
        parameter_builder=_params,
        expose_outputs={"value": ("node", "output0"), "geometry": ("node", "output0")},
    ),
    "attribute.write": _recipe(
        "attribute.write",
        "attribcreate",
        parameter_builder=_params,
        expose_inputs={"geometry": ("node", "input0"), "value": ("node", "value")},
    ),
    "math.clamp": _math_recipe("math.clamp"),
    "math.map_range": _math_recipe("math.map_range"),
}

for _op in (
    "math.add",
    "math.subtract",
    "math.multiply",
    "math.divide",
    "math.power",
    "math.min",
    "math.max",
):
    HOUDINI_RECIPES[_op] = _math_recipe(_op)

for _op in (
    "vector.add",
    "vector.subtract",
    "vector.scale",
    "vector.normalize",
    "vector.cross",
    "vector.dot",
    "vector.distance",
):
    HOUDINI_RECIPES[_op] = _vector_recipe(_op)

PRIMITIVE_BACKEND_TYPES = {
    "cube": "box",
    "grid": "grid",
    "sphere": "sphere",
    "ico_sphere": "sphere",
    "uv_sphere": "sphere",
    "circle": "circle",
    "cylinder": "tube",
    "cone": "tube",
    "line": "line",
}


def _vex_recipe(operation: str, snippet: str, *, note: str, output: str = "geometry") -> Recipe:
    def builder(node: IRNode) -> dict[str, JSONValue]:
        del node
        return {"snippet": snippet, "class": "point"}

    return Recipe(
        operation=operation,
        fidelity=TranslationStatus.CUSTOM_CODE,
        nodes=(
            NodeTemplate(
                local_id="wrangle",
                native_type="attribwrangle",
                inputs=("input0",),
                outputs=("output0",),
            ),
        ),
        expose_inputs={"geometry": ("wrangle", "input0"), "vector": ("wrangle", "input0")},
        expose_outputs={output: ("wrangle", "output0"), "geometry": ("wrangle", "output0")},
        note=note,
        code_kind="vex",
        code=snippet,
        parameter_builder=builder,
    )


HOUDINI_RECIPES["procedural.noise"] = _vex_recipe(
    "procedural.noise",
    "f@noise = noise(@P * chf('scale') + ch('seed'));\n",
    note="Houdini noise() is not Blender's Noise Texture. The pattern will not match numerically.",
    output="value",
)
HOUDINI_RECIPES["procedural.voronoi"] = _vex_recipe(
    "procedural.voronoi",
    "f@noise = noise(@P * chf('scale'), 1);\n",
    note="Houdini has no Blender-identical Voronoi. This uses a cellular-style noise approximation.",
    output="value",
)
HOUDINI_RECIPES["selection.compare"] = _vex_recipe(
    "selection.compare",
    "i@mask = f@value > chf('threshold');\n",
    note="Comparison is implemented as a point wrangle.",
    output="result",
)
HOUDINI_RECIPES["selection.spatial_noise"] = _vex_recipe(
    "selection.spatial_noise",
    "vector sample = v@P;\nf@noise = noise(sample * chf('scale') + ch('seed'));\ni@mask = f@noise > chf('threshold');\n",
    note="Spatial noise mask uses Houdini noise(), which is not Blender's Noise Texture.",
    output="result",
)
def _boolean_snippet(node: IRNode) -> str:
    operation = str(_params(node).get("operation") or "and").lower()
    snippets = {
        "and": "i@value = i@a && i@b;",
        "or": "i@value = i@a || i@b;",
        "not": "i@value = !i@a;",
        "xor": "i@value = i@a ^ i@b;",
        "nand": "i@value = !(i@a && i@b);",
        "nor": "i@value = !(i@a || i@b);",
    }
    return snippets.get(operation, snippets["and"]) + "\n"


HOUDINI_RECIPES["math.boolean"] = Recipe(
    operation="math.boolean",
    fidelity=TranslationStatus.CUSTOM_CODE,
    nodes=(
        NodeTemplate(
            local_id="wrangle",
            native_type="attribwrangle",
            inputs=("input0",),
            outputs=("output0",),
        ),
    ),
    expose_inputs={"a": ("wrangle", "input0"), "b": ("wrangle", "input0"), "geometry": ("wrangle", "input0")},
    expose_outputs={"value": ("wrangle", "output0"), "geometry": ("wrangle", "output0")},
    note="Boolean math is a point wrangle. It preserves the operation, not a Blender field evaluator.",
    code_kind="vex",
    code="i@value = i@a && i@b;\n",
    parameter_builder=lambda node: {"snippet": _boolean_snippet(node), "class": "point"},
)
HOUDINI_RECIPES["attribute.position"] = _vex_recipe(
    "attribute.position",
    "v@position = @P;\n",
    note="Position is Houdini's @P. A wrangle copies it to @position for downstream bindings.",
    output="vector",
)
HOUDINI_RECIPES["attribute.normal"] = _vex_recipe(
    "attribute.normal",
    "v@normal = @N;\n",
    note="Normal is Houdini's @N.",
    output="vector",
)
HOUDINI_RECIPES["attribute.index"] = _vex_recipe(
    "attribute.index",
    "i@index = @ptnum;\n",
    note="Index maps to @ptnum on points.",
    output="value",
)
HOUDINI_RECIPES["attribute.id"] = _vex_recipe(
    "attribute.id",
    "i@nb_id = haspointattrib(0, \"id\") ? point(0, \"id\", @ptnum) : @ptnum;\n",
    note="Blender ID reads Houdini's id point attribute when it exists, otherwise @ptnum.",
    output="value",
)
HOUDINI_RECIPES["geometry.extrude"] = _recipe(
    "geometry.extrude",
    "polyextrude",
    fidelity=TranslationStatus.LOWERED,
    note="PolyExtrude matches the intent of Extrude Mesh. Inset and individual-face options are not fully reproduced.",
    parameter_builder=_params,
)
HOUDINI_RECIPES["geometry.subdivide"] = _recipe(
    "geometry.subdivide",
    "subdivide",
    fidelity=TranslationStatus.APPROXIMATE,
    note="Houdini Subdivide is not Blender's subdivision algorithm.",
    parameter_builder=_params,
)
HOUDINI_RECIPES["geometry.set_material"] = _recipe(
    "geometry.set_material",
    "material",
    fidelity=TranslationStatus.LOWERED,
    note="Material SOP assigns a shop material path. Blender material slots are not copied.",
    parameter_builder=lambda node: {"shop_materialpath1": str(_params(node).get("material") or "")},
)
HOUDINI_RECIPES["geometry.rotate_instances"] = _vex_recipe(
    "geometry.rotate_instances",
    "p@orient = eulertoquaternion(radians(chv('rotation')), 0);\n",
    note="Instance rotation is written to the orient attribute. Euler order follows Houdini's default.",
)
HOUDINI_RECIPES["geometry.scale_instances"] = _vex_recipe(
    "geometry.scale_instances",
    "v@scale = chv('scale');\nf@pscale = 1;\n",
    note="Instance scale is written to @scale for Copy to Points.",
)
HOUDINI_RECIPES["geometry.switch"] = _recipe(
    "geometry.switch",
    "switch",
    inputs=("input0", "input1"),
    expose_inputs={"false": ("node", "input0"), "true": ("node", "input1"), "geometry": ("node", "input0")},
    note="Switch SOP selects an input. Field-driven per-element switches are not a single SOP.",
    fidelity=TranslationStatus.LOWERED,
    parameter_builder=_params,
)
HOUDINI_RECIPES["geometry.curve_to_mesh"] = _recipe(
    "geometry.curve_to_mesh",
    "sweep",
    inputs=("input0", "input1"),
    expose_inputs={"curve": ("node", "input0"), "profile": ("node", "input1")},
    expose_outputs={"geometry": ("node", "output0")},
    fidelity=TranslationStatus.APPROXIMATE,
    note="Sweep builds a mesh from a backbone and profile. It is not identical to Curve to Mesh.",
)
HOUDINI_RECIPES["geometry.resample_curve"] = _recipe(
    "geometry.resample_curve",
    "resample",
    expose_inputs={"curve": ("node", "input0"), "geometry": ("node", "input0")},
    expose_outputs={"curve": ("node", "output0"), "geometry": ("node", "output0")},
    fidelity=TranslationStatus.LOWERED,
    note="Resample SOP matches the intent of Resample Curve.",
    parameter_builder=_params,
)
HOUDINI_RECIPES["geometry.curve_primitive"] = _recipe(
    "geometry.curve_primitive",
    "circle",
    inputs=(),
    expose_outputs={"curve": ("node", "output0"), "geometry": ("node", "output0")},
    fidelity=TranslationStatus.LOWERED,
    note="Curve primitives become circle or line SOPs. Primitive kind selects the node type.",
    parameter_builder=_params,
)
HOUDINI_RECIPES["geometry.proximity"] = Recipe(
    operation="geometry.proximity",
    fidelity=TranslationStatus.CUSTOM_CODE,
    nodes=(
        NodeTemplate(
            local_id="wrangle",
            native_type="attribwrangle",
            inputs=("input0", "input1"),
            outputs=("output0",),
        ),
    ),
    expose_inputs={"source": ("wrangle", "input0"), "target": ("wrangle", "input1"), "geometry": ("wrangle", "input0")},
    expose_outputs={"distance": ("wrangle", "output0"), "position": ("wrangle", "output0"), "geometry": ("wrangle", "output0")},
    note="Proximity uses xyzdist against the second input. Attribute names differ from Blender.",
    code_kind="vex",
    code="int prim; vector uv; f@distance = xyzdist(1, @P, prim, uv); v@position = primuv(1, \"P\", prim, uv);\n",
    parameter_builder=lambda node: {
        "snippet": 'int prim; vector uv; f@distance = xyzdist(1, @P, prim, uv); v@position = primuv(1, "P", prim, uv);\n',
        "class": "point",
    },
)
HOUDINI_RECIPES["geometry.raycast"] = _recipe(
    "geometry.raycast",
    "ray",
    inputs=("input0", "input1"),
    expose_inputs={"source": ("node", "input0"), "target": ("node", "input1"), "geometry": ("node", "input1")},
    expose_outputs={"geometry": ("node", "output0"), "is_hit": ("node", "output0")},
    fidelity=TranslationStatus.LOWERED,
    note="Ray SOP performs the raycast. Hit attributes differ from Blender's Raycast node outputs.",
)
HOUDINI_RECIPES["graph.group"] = _recipe(
    "graph.group",
    "subnet",
    note="Nested Blender node groups become Houdini subnets.",
)
HOUDINI_RECIPES["graph.reroute"] = _recipe(
    "graph.reroute",
    "null",
    note="Reroutes are passthrough nulls when they were not collapsed earlier.",
)
HOUDINI_RECIPES["shader.principled_surface"] = _recipe(
    "shader.principled_surface",
    "principledshader",
    inputs=(),
    expose_inputs={"base_color": ("node", "basecolor"), "roughness": ("node", "rough"), "metallic": ("node", "metallic")},
    expose_outputs={"shader": ("node", "output0")},
    fidelity=TranslationStatus.LOWERED,
    note="Principled Shader approximates Principled BSDF. Closures are not numerically identical.",
    parameter_builder=_params,
)
