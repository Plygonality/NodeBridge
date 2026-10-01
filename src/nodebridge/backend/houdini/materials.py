"""Shader nodes -> MaterialX VOP networks in ``/mat`` (Karma / Solaris).

Each Blender material becomes a ``mtlxstandard_surface`` node plus the
MaterialX pattern nodes feeding it, grouped in a network box. Inputs
are wired with ``hou.Node.setNamedInput``; MaterialX type signatures
(float / color3 / vector3) are selected through the ``signature`` menu.
"""

from __future__ import annotations

from typing import Any

from ...backend.codegen import PyWriter, clean_number, literal
from ...common.names import NameAllocator, houdini_node_name, python_identifier
from ...ir.semantic import Const, InputValue, Link, Param, SemanticGraph, SemanticOp
from ...ir.types import DataType
from ...translation.confidence import Classification, Confidence as C
from ...translation.registry import translator

T, CTX = "houdini", "mtlx"
F, V, COL = DataType.FLOAT, DataType.VECTOR3, DataType.COLOR
SIGNATURE = {F: "default", V: "vector3", COL: "color3", DataType.VECTOR2: "vector2"}


class MtlxBuilder:
    def __init__(self, backend, result, graph: SemanticGraph, w: PyWriter, variables: NameAllocator) -> None:
        self.backend = backend
        self.result = result
        self.graph = graph
        self.w = w
        self.vars = variables
        self.names = NameAllocator()
        self.nodes: list[str] = []
        self.cache: dict[str, dict[str, tuple[str, int, DataType]]] = {}
        self.constants: dict[str, str] = {}
        self.surface: str | None = None

    @property
    def options(self):
        return self.result.options

    def node(self, op: SemanticOp | None, vop_type: str, suffix: str = "", *, name: str | None = None, signature: DataType | None = None) -> str:
        base = name or ((op.display_name if self.options.preserve_names else op.kind.lower()) + suffix if op else vop_type)
        hname = self.names.allocate(houdini_node_name(base))
        var = self.vars.allocate(python_identifier(hname))
        self.w.line(f'{var} = nb_create(matnet, "{vop_type}", "{hname}")')
        if signature is not None and SIGNATURE.get(signature, "default") != "default":
            self.w.line(f'nb_set_menu({var}, "signature", "{SIGNATURE[signature]}")')
        self.nodes.append(var)
        return var

    def set(self, var: str, parm: str, value: Any) -> None:
        self.w.line(f'nb_set({var}, "{parm}", {literal(value)})')

    def note(self, var: str, text: str) -> None:
        if self.options.include_comments:
            self.w.line(f"nb_note(matnet, {text!r}, {var})")

    def constant(self, value: Any, data_type: DataType) -> Any:
        if data_type in (V, COL):
            items = list(value) if isinstance(value, (list, tuple)) else [value] * 3
            return tuple(clean_number(float(v)) for v in (items + [0.0, 0.0, 0.0])[:3])
        if isinstance(value, (list, tuple)):
            value = sum(float(v) for v in value[:3]) / max(len(value[:3]), 1)
        return clean_number(float(value or 0.0))

    def param_node(self, key: str, want: DataType) -> tuple[str, int, DataType]:
        if key not in self.constants:
            parameter = self.graph.parameter(key)
            data_type = COL if parameter and parameter.data_type == COL else F
            var = self.node(None, "mtlxconstant", name=parameter.name if parameter else key, signature=data_type)
            self.set(var, "value", self.constant(parameter.current if parameter else 0.0, data_type))
            self.constants[key] = var
        parameter = self.graph.parameter(key)
        return self.constants[key], 0, COL if parameter and parameter.data_type == COL else F

    def feed(self, dst: str, input_name: str, value: InputValue | None, want: DataType, *, default: Any = None, transform=None) -> None:
        """Connect ``value`` into ``dst.input_name`` (or set the parameter for constants)."""
        if value is None:
            if default is not None:
                self.set(dst, input_name, self.constant(default, want))
            return
        if isinstance(value, Const):
            raw = value.value if value.value is not None else default
            if raw is None:
                return
            if transform is not None:
                raw = transform(raw)
            self.set(dst, input_name, self.constant(raw, want))
            return
        if isinstance(value, Param):
            var, index, _ = self.param_node(value.name, want)
        else:
            var, index, _ = self.output(value)
        self.w.line(f'nb_connect({dst}, "{input_name}", {var}, {index})')

    def output(self, link: Link) -> tuple[str, int, DataType]:
        op = self.graph.ops[link.op]
        if op.id not in self.cache:
            item = self.backend.translator(op, CTX)
            if item is None or self.result.classification(self.graph, op).confidence == C.UNSUPPORTED or self.result.is_blocked(self.graph, op):
                var = self.node(op, "mtlxconstant", "_unsupported")
                self.note(var, f"NodeBridge could not translate '{op.display_name}' ({op.kind}); a constant is used instead.")
                self.cache[op.id] = {name: (var, 0, ref.base) for name, ref in op.outputs.items()}
            else:
                if self.options.include_comments:
                    self.w.comment(f"{op.display_name}: {op.kind} [{self.result.classification(self.graph, op).confidence.value}]")
                self.cache[op.id] = item.fn(self, op)
        outputs = self.cache[op.id]
        return outputs.get(link.output) or next(iter(outputs.values()))


def write_material_function(backend, result, w: PyWriter, variables: NameAllocator, *, nested: bool = False) -> str:
    graph = result.semantic
    function = python_identifier(f"build_material_{graph.name}")
    w.line(f"def {function}():")
    w.indent()
    w.line(f'"""Material {graph.name!r} as a MaterialX network in /mat."""')
    w.line('matnet = hou.node("/mat")')
    builder = MtlxBuilder(backend, result, graph, w, variables)
    outputs = [op for op in graph.ops.values() if op.kind == "MATERIAL_OUTPUT"]
    if outputs:
        _material_output(builder, outputs[0])
    if builder.surface is None:
        builder.surface = builder.node(None, "mtlxstandard_surface", name=graph.name)
    w.line("nb_box = matnet.createNetworkBox()")
    w.line(f"for nb_item in ({', '.join(builder.nodes)},):")
    w.line("    nb_box.addItem(nb_item)")
    w.line(f"nb_box.setComment({graph.name!r})")
    w.line(f"matnet.layoutChildren(items=({', '.join(builder.nodes)},))")
    w.line("nb_box.fitAroundContents()")
    w.line(f"return {builder.surface}")
    w.dedent()
    return function


def _mtlx(kind, confidence, implementation, explanation="", limitations=(), classify=None):
    return translator(kind, target=T, context=CTX, confidence=confidence, implementation=implementation, explanation=explanation, limitations=limitations, classify=classify)


@_mtlx("MATERIAL_OUTPUT", C.EXACT, "material path /mat/<name>", "The surface shader node becomes the material.", ("Displacement is not translated.",))
def _material_output(mb: MtlxBuilder, op: SemanticOp) -> dict:
    surface = op.inputs.get("surface")
    if isinstance(surface, Link):
        var, _, _ = mb.output(surface)
        mb.surface = var
    if op.inputs.get("displacement") is not None and mb.surface:
        mb.note(mb.surface, "Blender displacement was not translated.")
    return {}


PRINCIPLED = {
    "base_color": ("base_color", COL),
    "metallic": ("metalness", F),
    "roughness": ("specular_roughness", F),
    "ior": ("specular_IOR", F),
    "normal": ("normal", V),
    "emission_color": ("emission_color", COL),
    "emission_strength": ("emission", F),
    "transmission": ("transmission", F),
    "coat": ("coat", F),
    "coat_roughness": ("coat_roughness", F),
    "sheen": ("sheen", F),
    "subsurface": ("subsurface", F),
}


@_mtlx(
    "SHADER_BSDF",
    C.EQUIVALENT,
    "mtlxstandard_surface",
    "Principled BSDF maps onto Autodesk Standard Surface; both are physically based but not identical models.",
    ("Specular IOR Level is mapped to specular weight (x2).", "Alpha is mapped to opacity."),
)
def _bsdf(mb: MtlxBuilder, op: SemanticOp) -> dict:
    var = mb.node(op, "mtlxstandard_surface", name=mb.graph.name)
    model = op.params.get("model", "principled")
    if model == "emission":
        mb.set(var, "base", 0.0)
        mb.feed(var, "emission_color", op.inputs.get("emission_color"), COL, default=[1, 1, 1])
        mb.feed(var, "emission", op.inputs.get("emission_strength"), F, default=1.0)
    else:
        for key, (name, data_type) in PRINCIPLED.items():
            if key in op.inputs:
                mb.feed(var, name, op.inputs[key], data_type)
        if model == "diffuse":
            mb.set(var, "specular", 0.0)
        if "specular" in op.inputs:
            mb.feed(var, "specular", op.inputs["specular"], F, transform=lambda v: float(v) * 2.0)
        if "alpha" in op.inputs:
            mb.feed(var, "opacity", op.inputs["alpha"], COL)
    return {"shader": (var, 0, DataType.SHADER)}


@_mtlx("SHADER_MIX", C.APPROXIMATE, "first shader only", "Mixing two surface shaders is not translated; the first shader is used.", ("The second shader and the mix factor are ignored.",))
def _shader_mix(mb: MtlxBuilder, op: SemanticOp) -> dict:
    first = op.inputs.get("a") or op.inputs.get("b")
    if isinstance(first, Link):
        var, index, data_type = mb.output(first)
        mb.note(var, f"'{op.display_name}' mixed two shaders; only this one was kept.")
        return {"shader": (var, index, data_type)}
    return {"shader": (mb.node(op, "mtlxstandard_surface"), 0, DataType.SHADER)}


FIELDS = {"generated": ("mtlxposition", "object"), "object": ("mtlxposition", "object"), "world_position": ("mtlxposition", "world"), "normal": ("mtlxnormal", "world"), "uv": ("mtlxtexcoord", None)}


@_mtlx(
    "FIELD_INPUT",
    C.EQUIVALENT,
    "mtlxposition / mtlxnormal / mtlxtexcoord",
    "Texture coordinates map onto MaterialX geometric inputs.",
    ("Blender's Generated coordinates are bounding-box normalized; MaterialX object position is not.", "Axes follow Houdini's Y-up convention."),
    classify=lambda op, g, base: Classification(C.UNSUPPORTED, f"{op.params.get('field')} coordinates are not translated.", "none") if op.params.get("field") not in FIELDS else None,
)
def _field(mb: MtlxBuilder, op: SemanticOp) -> dict:
    vop, space = FIELDS[op.params["field"]]
    var = mb.node(op, vop, signature=V if vop != "mtlxtexcoord" else DataType.VECTOR2)
    if space:
        mb.w.line(f'nb_set_menu({var}, "space", "{space}")')
    return {"value": (var, 0, V)}


def _fractal(mb: MtlxBuilder, op: SemanticOp, position: InputValue | None) -> str:
    scaled = mb.node(op, "mtlxmultiply", "_scale", signature=V)
    mb.w.line(f'nb_set_menu({scaled}, "signature", "vector3FA")')
    if position is not None:
        mb.feed(scaled, "in1", position, V)
    else:
        coords = mb.node(op, "mtlxposition", "_position", signature=V)
        mb.w.line(f'nb_connect({scaled}, "in1", {coords}, 0)')
    mb.feed(scaled, "in2", op.inputs.get("scale"), F, default=5.0)
    fractal = mb.node(op, "mtlxfractal3d")
    mb.w.line(f'nb_connect({fractal}, "position", {scaled}, 0)')
    detail = op.inputs.get("detail")
    octaves = int(float(detail.value)) + 1 if isinstance(detail, Const) else 3
    mb.set(fractal, "octaves", octaves)
    mb.feed(fractal, "diminish", op.inputs.get("roughness"), F, default=0.5)
    mb.feed(fractal, "lacunarity", op.inputs.get("lacunarity"), F, default=2.0)
    remap = mb.node(op, "mtlxremap", "_to_unit")
    mb.w.line(f'nb_connect({remap}, "in", {fractal}, 0)')
    mb.set(remap, "inlow", -1.0)
    mb.set(remap, "inhigh", 1.0)
    return remap


@_mtlx(
    "NOISE",
    C.APPROXIMATE,
    "mtlxfractal3d",
    "Blender fBm noise approximated with MaterialX fractal noise remapped to 0..1.",
    ("Pattern will not be numerically identical.", "Color output reuses the scalar noise."),
)
def _noise(mb: MtlxBuilder, op: SemanticOp) -> dict:
    remap = _fractal(mb, op, op.inputs.get("vector"))
    return {"fac": (remap, 0, F), "color": (remap, 0, F)}


@_mtlx("VORONOI", C.APPROXIMATE, "mtlxworleynoise3d", "Cellular noise via MaterialX Worley noise.", ("Only the distance output is meaningful.",))
def _voronoi(mb: MtlxBuilder, op: SemanticOp) -> dict:
    var = mb.node(op, "mtlxworleynoise3d")
    if op.inputs.get("vector") is not None:
        mb.feed(var, "position", op.inputs.get("vector"), V)
    mb.feed(var, "jitter", op.inputs.get("randomness"), F, default=1.0)
    return {"distance": (var, 0, F), "color": (var, 0, F), "position": (var, 0, F)}


@_mtlx("COLOR_RAMP", C.EXACT, "mtlxremap + mtlxclamp + mtlxmix chain", "Linear ramps are rebuilt stop by stop with remap / clamp / mix.", classify=lambda op, g, base: Classification(C.APPROXIMATE, "Non-linear ramp interpolation is approximated as linear.", base.implementation) if op.params.get("interpolation", "LINEAR") != "LINEAR" else None)
def _ramp(mb: MtlxBuilder, op: SemanticOp) -> dict:
    stops = sorted(op.params.get("stops") or [[0.0, [0, 0, 0, 1]], [1.0, [1, 1, 1, 1]]], key=lambda s: s[0])
    current = mb.node(op, "mtlxconstant", "_stop_0", signature=COL)
    mb.set(current, "value", mb.constant(stops[0][1], COL))
    for index, ((p0, _), (p1, c1)) in enumerate(zip(stops, stops[1:]), start=1):
        remap = mb.node(op, "mtlxremap", f"_segment_{index}")
        mb.feed(remap, "in", op.inputs.get("fac"), F, default=0.5)
        mb.set(remap, "inlow", clean_number(p0))
        mb.set(remap, "inhigh", clean_number(max(p1, p0 + 1e-6)))
        clamp = mb.node(op, "mtlxclamp", f"_segment_{index}_clamp")
        mb.w.line(f'nb_connect({clamp}, "in", {remap}, 0)')
        mix = mb.node(op, "mtlxmix", f"_stop_{index}", signature=COL)
        mb.w.line(f'nb_connect({mix}, "bg", {current}, 0)')
        mb.set(mix, "fg", mb.constant(c1, COL))
        mb.w.line(f'nb_connect({mix}, "mix", {clamp}, 0)')
        current = mix
    return {"color": (current, 0, COL), "alpha": (current, 0, F)}


@_mtlx("MAP_RANGE", C.EXACT, "mtlxremap (+ mtlxclamp)", "Linear remapping with optional clamping.", classify=lambda op, g, base: Classification(C.APPROXIMATE, f"{op.params.get('interpolation')} interpolation is approximated as linear.", base.implementation) if op.params.get("interpolation", "LINEAR") != "LINEAR" else None)
def _map_range(mb: MtlxBuilder, op: SemanticOp) -> dict:
    var = mb.node(op, "mtlxremap")
    for name, key, default in (("in", "value", 1.0), ("inlow", "from_min", 0.0), ("inhigh", "from_max", 1.0), ("outlow", "to_min", 0.0), ("outhigh", "to_max", 1.0)):
        mb.feed(var, name, op.inputs.get(key), F, default=default)
    if op.params.get("clamp", True):
        clamp = mb.node(op, "mtlxclamp", "_clamp")
        mb.w.line(f'nb_connect({clamp}, "in", {var}, 0)')
        mb.feed(clamp, "low", op.inputs.get("to_min"), F, default=0.0)
        mb.feed(clamp, "high", op.inputs.get("to_max"), F, default=1.0)
        var = clamp
    return {"result": (var, 0, F)}


MATH_MTLX = {
    "ADD": ("mtlxadd", ("in1", "in2")),
    "SUBTRACT": ("mtlxsubtract", ("in1", "in2")),
    "MULTIPLY": ("mtlxmultiply", ("in1", "in2")),
    "DIVIDE": ("mtlxdivide", ("in1", "in2")),
    "POWER": ("mtlxpower", ("in1", "in2")),
    "MINIMUM": ("mtlxmin", ("in1", "in2")),
    "MAXIMUM": ("mtlxmax", ("in1", "in2")),
    "MODULO": ("mtlxmodulo", ("in1", "in2")),
    "ABSOLUTE": ("mtlxabsval", ("in",)),
    "FLOOR": ("mtlxfloor", ("in",)),
    "CEIL": ("mtlxceil", ("in",)),
    "SINE": ("mtlxsin", ("in",)),
    "COSINE": ("mtlxcos", ("in",)),
    "SQRT": ("mtlxsqrt", ("in",)),
    "CLAMP_MINMAX": ("mtlxclamp", ("in", "low", "high")),
}


@_mtlx("MATH", C.EXACT, "MaterialX math nodes", "Scalar math maps onto MaterialX arithmetic.", classify=lambda op, g, base: Classification(C.UNSUPPORTED, f"Math {op.params.get('operation')} has no MaterialX mapping here.", "none") if op.params.get("operation") not in MATH_MTLX else None)
def _math(mb: MtlxBuilder, op: SemanticOp) -> dict:
    vop, names = MATH_MTLX[op.params["operation"]]
    var = mb.node(op, vop)
    for name, key in zip(names, "abc"):
        mb.feed(var, name, op.inputs.get(key), F, default=0.0)
    if op.params.get("clamp"):
        clamp = mb.node(op, "mtlxclamp", "_clamp")
        mb.w.line(f'nb_connect({clamp}, "in", {var}, 0)')
        var = clamp
    return {"value": (var, 0, F)}


VECTOR_MTLX = {"ADD": "mtlxadd", "SUBTRACT": "mtlxsubtract", "MULTIPLY": "mtlxmultiply", "DIVIDE": "mtlxdivide", "SCALE": "mtlxmultiply", "NORMALIZE": "mtlxnormalize", "LENGTH": "mtlxmagnitude", "DOT_PRODUCT": "mtlxdotproduct", "CROSS_PRODUCT": "mtlxcrossproduct"}


@_mtlx("VECTOR_MATH", C.EXACT, "MaterialX vector nodes", "Vector math maps onto MaterialX vector3 nodes.", classify=lambda op, g, base: Classification(C.UNSUPPORTED, f"Vector Math {op.params.get('operation')} has no MaterialX mapping here.", "none") if op.params.get("operation") not in VECTOR_MTLX else None)
def _vector_math(mb: MtlxBuilder, op: SemanticOp) -> dict:
    operation = op.params["operation"]
    var = mb.node(op, VECTOR_MTLX[operation], signature=V)
    if operation in ("NORMALIZE", "LENGTH"):
        mb.feed(var, "in", op.inputs.get("a"), V)
    else:
        mb.feed(var, "in1", op.inputs.get("a"), V)
        if operation == "SCALE":
            mb.w.line(f'nb_set_menu({var}, "signature", "vector3FA")')
            mb.feed(var, "in2", op.inputs.get("scale"), F, default=1.0)
        else:
            mb.feed(var, "in2", op.inputs.get("b"), V)
    return {"vector": (var, 0, V), "value": (var, 0, F)}


@_mtlx("MIX", C.EXACT, "mtlxmix", "Blending with MaterialX mix (bg = A, fg = B).", classify=lambda op, g, base: Classification(C.APPROXIMATE, f"Blend mode {op.params.get('blend_type')} is approximated as Mix.", base.implementation) if op.params.get("blend_type", "MIX") not in ("MIX", "MULTIPLY", "ADD") else None)
def _mix(mb: MtlxBuilder, op: SemanticOp) -> dict:
    data_type = {"RGBA": COL, "VECTOR": V}.get(op.params.get("data_type", "FLOAT"), F)
    blend = op.params.get("blend_type", "MIX")
    fg_source: Any = op.inputs.get("b")
    if blend in ("MULTIPLY", "ADD"):
        combined = mb.node(op, "mtlxmultiply" if blend == "MULTIPLY" else "mtlxadd", "_blend", signature=data_type)
        mb.feed(combined, "in1", op.inputs.get("a"), data_type)
        mb.feed(combined, "in2", op.inputs.get("b"), data_type)
        fg_source = combined
    var = mb.node(op, "mtlxmix", signature=data_type)
    mb.feed(var, "bg", op.inputs.get("a"), data_type)
    if isinstance(fg_source, str):
        mb.w.line(f'nb_connect({var}, "fg", {fg_source}, 0)')
    else:
        mb.feed(var, "fg", fg_source, data_type)
    mb.feed(var, "mix", op.inputs.get("factor"), F, default=0.5)
    return {"result": (var, 0, data_type)}


@_mtlx("MAPPING", C.EXACT, "mtlxmultiply + mtlxadd", "Point mapping: vector * scale + location.", classify=lambda op, g, base: Classification(C.APPROXIMATE, "Mapping rotation is not translated.", base.implementation) if not (isinstance(op.inputs.get("rotation"), Const) and not any(op.inputs["rotation"].value)) else None)
def _mapping(mb: MtlxBuilder, op: SemanticOp) -> dict:
    scaled = mb.node(op, "mtlxmultiply", "_scale", signature=V)
    mb.feed(scaled, "in1", op.inputs.get("vector"), V)
    mb.feed(scaled, "in2", op.inputs.get("scale"), V, default=[1, 1, 1])
    var = scaled
    if "location" in op.inputs:
        moved = mb.node(op, "mtlxadd", "_offset", signature=V)
        mb.w.line(f'nb_connect({moved}, "in1", {scaled}, 0)')
        mb.feed(moved, "in2", op.inputs.get("location"), V, default=[0, 0, 0])
        var = moved
    return {"vector": (var, 0, V)}


@_mtlx("BUMP", C.EQUIVALENT, "mtlxheighttonormal", "Height-driven normal perturbation.", ("Bump distance is folded into the scale.",))
def _bump(mb: MtlxBuilder, op: SemanticOp) -> dict:
    var = mb.node(op, "mtlxheighttonormal")
    mb.feed(var, "in", op.inputs.get("height"), F, default=0.0)
    mb.feed(var, "scale", op.inputs.get("strength"), F, default=1.0)
    return {"normal": (var, 0, V)}


@_mtlx("NORMAL_MAP", C.EQUIVALENT, "mtlxnormalmap", "Tangent-space normal map (OpenGL convention in both).")
def _normal_map(mb: MtlxBuilder, op: SemanticOp) -> dict:
    var = mb.node(op, "mtlxnormalmap")
    mb.feed(var, "in", op.inputs.get("color"), V)
    mb.feed(var, "scale", op.inputs.get("strength"), F, default=1.0)
    return {"normal": (var, 0, V)}


@_mtlx("TEXTURE_SAMPLE", C.EQUIVALENT, "mtlximage", "Image texture with the same file path.", ("Color space and extension modes use MaterialX defaults.",))
def _image(mb: MtlxBuilder, op: SemanticOp) -> dict:
    var = mb.node(op, "mtlximage", signature=COL)
    image = op.inputs.get("image")
    path = image.value.get("filepath", "") if isinstance(image, Const) and isinstance(image.value, dict) else ""
    mb.set(var, "file", path)
    vector = op.inputs.get("vector")
    if isinstance(vector, Link) and mb.graph.ops[vector.op].params.get("field") != "uv":
        mb.feed(var, "texcoord", vector, DataType.VECTOR2)
    return {"color": (var, 0, COL), "alpha": (var, 0, F)}


@_mtlx("COMBINE_VECTOR", C.EXACT, "mtlxcombine3", "Vector construction.")
def _combine(mb: MtlxBuilder, op: SemanticOp) -> dict:
    var = mb.node(op, "mtlxcombine3", signature=V)
    for name, key in (("in1", "x"), ("in2", "y"), ("in3", "z")):
        mb.feed(var, name, op.inputs.get(key), F, default=0.0)
    return {"vector": (var, 0, V)}


@_mtlx("SEPARATE_VECTOR", C.EXACT, "mtlxseparate3", "Component access.")
def _separate(mb: MtlxBuilder, op: SemanticOp) -> dict:
    var = mb.node(op, "mtlxseparate3", signature=V)
    mb.feed(var, "in", op.inputs.get("vector"), V)
    return {"x": (var, 0, F), "y": (var, 1, F), "z": (var, 2, F)}


@_mtlx("COLOR_OPERATION", C.EXACT, "mtlxsubtract (invert)", "Color invert as 1 - color.", classify=lambda op, g, base: Classification(C.UNSUPPORTED, f"Color operation {op.params.get('operation')} is not translated to MaterialX yet.", "none") if op.params.get("operation") != "invert" else None)
def _color_op(mb: MtlxBuilder, op: SemanticOp) -> dict:
    var = mb.node(op, "mtlxsubtract", signature=COL)
    mb.set(var, "in1", (1.0, 1.0, 1.0))
    mb.feed(var, "in2", op.inputs.get("color"), COL)
    return {"color": (var, 0, COL)}
