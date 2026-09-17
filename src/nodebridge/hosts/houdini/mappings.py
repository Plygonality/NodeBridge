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
