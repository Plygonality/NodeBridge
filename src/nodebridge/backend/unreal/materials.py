"""Shader nodes -> Unreal Material assets via ``unreal.MaterialEditingLibrary``.

Blender Value / RGB nodes with a custom label become Scalar / Vector
Parameters, so the material keeps its user-facing controls. Color ramps
and Map Range are rebuilt exactly from arithmetic expressions. Texture
coordinates are converted centrally: UV V is flipped (Blender bottom-left
origin vs Unreal top-left) and positions are converted from Unreal
centimeters / left-handed axes back to Blender meters / right-handed.
"""

from __future__ import annotations

from typing import Any

from ...backend.codegen import PyWriter, clean_number, literal
from ...common.coordinates import BLENDER, UNREAL, convert_point, uv_flip_required
from ...common.names import NameAllocator, python_identifier, unreal_asset_name
from ...common.units import BLENDER_UNITS, UNREAL_UNITS, convert_length
from ...ir.semantic import Const, InputValue, Link, Param, SemanticGraph, SemanticOp
from ...ir.types import DataType
from ...translation.confidence import Classification, Confidence as C
from ...translation.registry import translator

T, CTX = "unreal", "material"
F, V, COL = DataType.FLOAT, DataType.VECTOR3, DataType.COLOR
CONST_INPUTS = {"A": "const_a", "B": "const_b", "Alpha": "const_alpha"}


class MaterialBuilder:
    def __init__(self, backend, result, graph: SemanticGraph, w: PyWriter, variables: NameAllocator, material_var: str) -> None:
        self.backend, self.result, self.graph, self.w, self.vars = backend, result, graph, w, variables
        self.material = material_var
        self.cache: dict[str, dict[str, tuple[str, str]]] = {}
        self.params: dict[str, str] = {}
        self.count = 0

    @property
    def options(self):
        return self.result.options

    def expression(self, op: SemanticOp | None, class_name: str, suffix: str = "") -> str:
        base = python_identifier(((op.display_name if op and self.options.preserve_names else (op.kind.lower() if op else "expr")) + suffix) if op else class_name.replace("MaterialExpression", "").lower())
        var = self.vars.allocate(base)
        self.count += 1
        x = -400 - 260 * (self.count % 6)
        y = 140 * self.count
        self.w.line(f'{var} = nb_expression({self.material}, "{class_name}", {x}, {y})')
        return var

    def prop(self, var: str, name: str, expression: str) -> None:
        self.w.line(f'nb_prop({var}, "{name}", {expression})')

    def constant(self, value: Any, want: DataType) -> tuple[str, str]:
        if want in (V, COL) or (isinstance(value, (list, tuple)) and len(value) >= 3):
            items = list(value) if isinstance(value, (list, tuple)) else [value] * 3
            r, g, b = (clean_number(float(v)) for v in (items + [0.0] * 3)[:3])
            var = self.expression(None, "MaterialExpressionConstant3Vector")
            self.prop(var, "constant", f"unreal.LinearColor({literal(r)}, {literal(g)}, {literal(b)}, 1.0)")
            return var, ""
        var = self.expression(None, "MaterialExpressionConstant")
        self.prop(var, "r", literal(clean_number(float(value or 0.0))))
        return var, ""

    def param(self, key: str) -> tuple[str, str]:
        if key not in self.params:
            parameter = self.graph.parameter(key)
            if parameter is not None and parameter.data_type == COL:
                var = self.expression(None, "MaterialExpressionVectorParameter", f"_{key}")
                r, g, b = (clean_number(float(v)) for v in (list(parameter.current or [1, 1, 1]) + [1, 1, 1])[:3])
                self.prop(var, "default_value", f"unreal.LinearColor({literal(r)}, {literal(g)}, {literal(b)}, 1.0)")
            else:
                var = self.vars.allocate(python_identifier(f"param_{key}"))
                self.count += 1
                self.w.line(f'{var} = nb_expression({self.material}, "MaterialExpressionScalarParameter", {-400 - 260 * (self.count % 6)}, {140 * self.count})')
                self.prop(var, "default_value", literal(clean_number(float(parameter.current if parameter else 0.0))))
            self.prop(var, "parameter_name", repr(parameter.name if parameter else key))
            self.params[key] = var
        return self.params[key], ""

    def source(self, value: InputValue | None, want: DataType, default: Any = 0.0) -> tuple[str, str]:
        if isinstance(value, Param):
            return self.param(value.name)
        if isinstance(value, Link):
            return self.output(value)
        raw = value.value if isinstance(value, Const) and value.value is not None else default
        return self.constant(raw, want)

    def feed(self, target: str, input_name: str, value: InputValue | None, want: DataType, default: Any = None) -> None:
        if value is None and default is None:
            return
        if (value is None or isinstance(value, Const)) and input_name in CONST_INPUTS and want == F:
            raw = value.value if isinstance(value, Const) and value.value is not None else default
            if isinstance(raw, (list, tuple)):
                raw = sum(float(v) for v in raw[:3]) / len(raw[:3])
            self.prop(target, CONST_INPUTS[input_name], literal(clean_number(float(raw))))
            return
        var, output = self.source(value, want, default if default is not None else 0.0)
        self.w.line(f"nb_link({var}, {output!r}, {target}, {input_name!r})")

    def output(self, link: Link) -> tuple[str, str]:
        op = self.graph.ops[link.op]
        if op.id not in self.cache:
            item = self.backend.translator(op, CTX)
            classification = self.result.classification(self.graph, op)
            if item is None or classification.confidence == C.UNSUPPORTED or self.result.is_blocked(self.graph, op):
                self.w.line(f"NB_WARNINGS.append({f'Not translated: {op.display_name} ({op.kind}); a constant 0 is used.'!r})")
                var, _ = self.constant(0.0, F)
                self.cache[op.id] = {name: (var, "") for name in op.outputs}
            else:
                if self.options.include_comments:
                    self.w.comment(f"{op.display_name}: {op.kind} [{classification.confidence.value}]")
                self.cache[op.id] = item.fn(self, op)
        outputs = self.cache[op.id]
        return outputs.get(link.output) or next(iter(outputs.values()))

    def binary(self, op: SemanticOp, class_name: str, a: InputValue | None, b: InputValue | None, want: DataType, suffix: str = "", da: Any = 0.0, db: Any = 0.0) -> str:
        var = self.expression(op, class_name, suffix)
        self.feed(var, "A", a, want, da)
        self.feed(var, "B", b, want, db)
        return var

    def unary(self, op: SemanticOp, class_name: str, value: InputValue | tuple[str, str] | None, want: DataType, suffix: str = "") -> str:
        var = self.expression(op, class_name, suffix)
        if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str):
            self.w.line(f"nb_link({value[0]}, {value[1]!r}, {var}, '')")
        else:
            self.feed(var, "", value, want, 0.0)  # type: ignore[arg-type]
        return var


def write_material(backend, result, w: PyWriter, variables: NameAllocator) -> str:
    graph = result.semantic
    name = result.document.source.get("material") or graph.name
    function = python_identifier(f"build_material_{name}")
    w.line(f"def {function}():")
    w.indent()
    w.line(f'"""Material {name!r} as an Unreal Material asset."""')
    w.line(f'material = nb_create_asset("{unreal_asset_name(name, "M_")}", ASSET_PATH, unreal.Material, unreal.MaterialFactoryNew())')
    builder = MaterialBuilder(backend, result, graph, w, variables, "material")
    outputs = [op for op in graph.ops.values() if op.kind == "MATERIAL_OUTPUT"]
    if outputs:
        _material_output(builder, outputs[0])
    w.line("MEL.recompile_material(material)")
    w.line("unreal.EditorAssetLibrary.save_loaded_asset(material)")
    w.line("return material")
    w.dedent()
    return function


def _mat(kind, confidence, implementation, explanation="", limitations=(), classify=None, fallback=""):
    return translator(kind, target=T, context=CTX, confidence=confidence, implementation=implementation, explanation=explanation, limitations=limitations, classify=classify, fallback=fallback)


@_mat("MATERIAL_OUTPUT", C.EXACT, "Material output pins", "The surface shader's inputs connect to the material's attributes.", ("Displacement is not translated.",))
def _material_output(mb: MaterialBuilder, op: SemanticOp) -> dict:
    surface = mb.graph.resolve(op.inputs.get("surface"))
    if surface is not None and surface.kind == "SHADER_MIX":
        surface = mb.graph.resolve(surface.inputs.get("a")) or mb.graph.resolve(surface.inputs.get("b"))
    if surface is not None and surface.kind == "SHADER_BSDF":
        _bsdf(mb, surface)
    return {}


PROPERTIES = {
    "base_color": ("MP_BASE_COLOR", COL),
    "metallic": ("MP_METALLIC", F),
    "roughness": ("MP_ROUGHNESS", F),
    "specular": ("MP_SPECULAR", F),
    "normal": ("MP_NORMAL", V),
}


@_mat(
    "SHADER_BSDF",
    C.EQUIVALENT,
    "Default Lit material attributes",
    "Principled BSDF inputs map onto Unreal's Default Lit shading model; both are PBR but not identical.",
    ("Coat, sheen, subsurface and transmission are not mapped.", "Alpha below 1 needs a translucent / masked blend mode."),
)
def _bsdf(mb: MaterialBuilder, op: SemanticOp) -> dict:
    if mb.options.include_comments:
        mb.w.comment(f"{op.display_name}: SHADER_BSDF -> material attributes")
    model = op.params.get("model", "principled")
    properties = dict(PROPERTIES)
    if model == "diffuse":
        properties = {"base_color": PROPERTIES["base_color"], "roughness": PROPERTIES["roughness"], "normal": PROPERTIES["normal"]}
    for key, (prop, want) in properties.items():
        if key in op.inputs:
            var, output = mb.source(op.inputs[key], want)
            mb.w.line(f'nb_output({var}, {output!r}, unreal.MaterialProperty.{prop})')
    if "emission_color" in op.inputs:
        strength = op.inputs.get("emission_strength", Const(0.0))
        if not (isinstance(strength, Const) and float(strength.value or 0.0) == 0.0):
            emissive = mb.binary(op, "MaterialExpressionMultiply", op.inputs["emission_color"], strength, COL, "_emission", db=1.0)
            mb.w.line(f"nb_output({emissive}, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)")
    if model == "diffuse":
        mb.w.line("nb_output(nb_expression(material, 'MaterialExpressionConstant', -400, 0), '', unreal.MaterialProperty.MP_SPECULAR)")
    return {"shader": ("", "")}


@_mat("SHADER_MIX", C.APPROXIMATE, "first shader only", "Mixing surface shaders is not translated; the first shader is used.", ("The second shader is ignored.",))
def _shader_mix(mb: MaterialBuilder, op: SemanticOp) -> dict:
    return {"shader": ("", "")}


def _position(mb: MaterialBuilder, op: SemanticOp, class_name: str) -> str:
    raw = mb.expression(op, class_name)
    factor = convert_length(1.0, UNREAL_UNITS, BLENDER_UNITS)
    axes = convert_point((factor, factor, factor), UNREAL, BLENDER)
    convert = mb.expression(op, "MaterialExpressionMultiply", "_to_blender_meters")
    mb.w.line(f"nb_link({raw}, '', {convert}, 'A')")
    constant, _ = mb.constant(list(axes), V)
    mb.w.line(f"nb_link({constant}, '', {convert}, 'B')")
    return convert


def _uv(mb: MaterialBuilder, op: SemanticOp) -> str:
    coords = mb.expression(op, "MaterialExpressionTextureCoordinate")
    if not uv_flip_required(BLENDER, UNREAL):
        return coords
    u = mb.expression(op, "MaterialExpressionComponentMask", "_u")
    mb.prop(u, "r", "True")
    v = mb.expression(op, "MaterialExpressionComponentMask", "_v")
    mb.prop(v, "g", "True")
    mb.w.line(f"nb_link({coords}, '', {u}, '')")
    mb.w.line(f"nb_link({coords}, '', {v}, '')")
    flipped = mb.unary(op, "MaterialExpressionOneMinus", (v, ""), F, "_v_flipped")
    uv = mb.expression(op, "MaterialExpressionAppendVector", "_blender_uv")
    mb.w.line(f"nb_link({u}, '', {uv}, 'A')")
    mb.w.line(f"nb_link({flipped}, '', {uv}, 'B')")
    return uv


@_mat(
    "FIELD_INPUT",
    C.EQUIVALENT,
    "TextureCoordinate / LocalPosition / WorldPosition / VertexNormalWS",
    "Coordinates converted to Blender conventions (UV V flipped; positions in meters, right-handed).",
    ("Blender's Generated coordinates are bounding-box normalized; Unreal local position is not.",),
    classify=lambda op, g, base: Classification(C.EXACT, "UV with the V axis flipped to Blender's convention.", "TextureCoordinate + OneMinus(V)") if op.params.get("field") == "uv" else (Classification(C.UNSUPPORTED, f"{op.params.get('field')} coordinates are not translated.", "none") if op.params.get("field") not in ("uv", "generated", "object", "world_position", "normal") else None),
)
def _field(mb: MaterialBuilder, op: SemanticOp) -> dict:
    field = op.params.get("field")
    if field == "uv":
        return {"value": (_uv(mb, op), "")}
    if field == "normal":
        normal = mb.expression(op, "MaterialExpressionVertexNormalWS")
        return {"value": (normal, "")}
    class_name = "MaterialExpressionWorldPosition" if field == "world_position" else "MaterialExpressionLocalPosition"
    return {"value": (_position(mb, op, class_name), "")}


@_mat(
    "NOISE",
    C.APPROXIMATE,
    "MaterialExpressionNoise",
    "Blender fBm noise approximated with Unreal's gradient noise expression (output 0..1).",
    ("Pattern will not be numerically identical.", "Color output reuses the scalar noise."),
)
def _noise(mb: MaterialBuilder, op: SemanticOp) -> dict:
    var = mb.expression(op, "MaterialExpressionNoise")
    vector = op.inputs.get("vector")
    if vector is not None:
        mb.feed(var, "Position", vector, V)
    else:
        position = _position(mb, op, "MaterialExpressionLocalPosition")
        mb.w.line(f"nb_link({position}, '', {var}, 'Position')")
    scale = op.inputs.get("scale")
    mb.prop(var, "scale", literal(clean_number(float(scale.value if isinstance(scale, Const) else 5.0))))
    detail = op.inputs.get("detail")
    mb.prop(var, "levels", str(int(float(detail.value)) + 1 if isinstance(detail, Const) else 3))
    mb.prop(var, "output_min", "0.0")
    mb.prop(var, "output_max", "1.0")
    mb.w.line(f'nb_prop({var}, "noise_function", nb_enum("NoiseFunction", "NOISEFUNCTION_GRADIENT_ALU", "GRADIENT_ALU"))')
    return {"fac": (var, ""), "color": (var, "")}


@_mat("VORONOI", C.APPROXIMATE, "MaterialExpressionNoise (Voronoi)", "Cellular noise with Unreal's Voronoi noise function.", ("Only the distance output is meaningful.",))
def _voronoi(mb: MaterialBuilder, op: SemanticOp) -> dict:
    var = mb.expression(op, "MaterialExpressionNoise")
    if op.inputs.get("vector") is not None:
        mb.feed(var, "Position", op.inputs.get("vector"), V)
    scale = op.inputs.get("scale")
    mb.prop(var, "scale", literal(clean_number(float(scale.value if isinstance(scale, Const) else 5.0))))
    mb.w.line(f'nb_prop({var}, "noise_function", nb_enum("NoiseFunction", "NOISEFUNCTION_VORONOI_ALU", "VORONOI_ALU"))')
    return {"distance": (var, ""), "color": (var, ""), "position": (var, "")}


def _remap01(mb: MaterialBuilder, op: SemanticOp, value: InputValue | tuple[str, str] | None, low: float, high: float, suffix: str, clamp: bool = True) -> str:
    shifted = mb.expression(op, "MaterialExpressionSubtract", f"{suffix}_shift")
    if isinstance(value, tuple) and isinstance(value[0], str):
        mb.w.line(f"nb_link({value[0]}, {value[1]!r}, {shifted}, 'A')")
    else:
        mb.feed(shifted, "A", value, F, 0.5)  # type: ignore[arg-type]
    mb.prop(shifted, "const_b", literal(clean_number(low)))
    scaled = mb.expression(op, "MaterialExpressionMultiply", f"{suffix}_scale")
    mb.w.line(f"nb_link({shifted}, '', {scaled}, 'A')")
    mb.prop(scaled, "const_b", literal(clean_number(1.0 / (high - low) if high != low else 0.0)))
    if not clamp:
        return scaled
    return mb.unary(op, "MaterialExpressionSaturate", (scaled, ""), F, f"{suffix}_clamp")


@_mat("COLOR_RAMP", C.EXACT, "Lerp chain with saturated remaps", "Linear ramps are rebuilt exactly stop by stop.", classify=lambda op, g, base: Classification(C.APPROXIMATE, "Non-linear ramp interpolation is approximated as linear.", base.implementation) if op.params.get("interpolation", "LINEAR") != "LINEAR" else None)
def _ramp(mb: MaterialBuilder, op: SemanticOp) -> dict:
    stops = sorted(op.params.get("stops") or [[0.0, [0, 0, 0, 1]], [1.0, [1, 1, 1, 1]]], key=lambda s: s[0])
    fac = mb.source(op.inputs.get("fac"), F, 0.5)
    current, _ = mb.constant(stops[0][1][:3], COL)
    for index, ((p0, _c0), (p1, c1)) in enumerate(zip(stops, stops[1:]), start=1):
        alpha = _remap01(mb, op, fac, float(p0), max(float(p1), float(p0) + 1e-6), f"_segment_{index}")
        lerp = mb.expression(op, "MaterialExpressionLinearInterpolate", f"_stop_{index}")
        mb.w.line(f"nb_link({current}, '', {lerp}, 'A')")
        color, _ = mb.constant(c1[:3], COL)
        mb.w.line(f"nb_link({color}, '', {lerp}, 'B')")
        mb.w.line(f"nb_link({alpha}, '', {lerp}, 'Alpha')")
        current = lerp
    return {"color": (current, ""), "alpha": (current, "A")}


@_mat("MAP_RANGE", C.EXACT, "Subtract / Divide / Lerp", "Linear Map Range rebuilt from arithmetic (with clamping).", classify=lambda op, g, base: Classification(C.APPROXIMATE, f"{op.params.get('interpolation')} interpolation is approximated as linear.", base.implementation) if op.params.get("interpolation", "LINEAR") != "LINEAR" else None)
def _map_range(mb: MaterialBuilder, op: SemanticOp) -> dict:
    from_min, from_max = op.inputs.get("from_min", Const(0.0)), op.inputs.get("from_max", Const(1.0))
    if isinstance(from_min, Const) and isinstance(from_max, Const):
        t = _remap01(mb, op, op.inputs.get("value"), float(from_min.value), float(from_max.value), "_t", clamp=op.params.get("clamp", True))
    else:
        shifted = mb.binary(op, "MaterialExpressionSubtract", op.inputs.get("value"), from_min, F, "_shift", 1.0, 0.0)
        span = mb.binary(op, "MaterialExpressionSubtract", from_max, from_min, F, "_span", 1.0, 0.0)
        t = mb.expression(op, "MaterialExpressionDivide", "_t")
        mb.w.line(f"nb_link({shifted}, '', {t}, 'A')")
        mb.w.line(f"nb_link({span}, '', {t}, 'B')")
        if op.params.get("clamp", True):
            t = mb.unary(op, "MaterialExpressionSaturate", (t, ""), F, "_clamp")
    lerp = mb.expression(op, "MaterialExpressionLinearInterpolate")
    mb.feed(lerp, "A", op.inputs.get("to_min"), F, 0.0)
    mb.feed(lerp, "B", op.inputs.get("to_max"), F, 1.0)
    mb.w.line(f"nb_link({t}, '', {lerp}, 'Alpha')")
    return {"result": (lerp, "")}


MATH_UE = {
    "ADD": ("MaterialExpressionAdd", 2),
    "SUBTRACT": ("MaterialExpressionSubtract", 2),
    "MULTIPLY": ("MaterialExpressionMultiply", 2),
    "DIVIDE": ("MaterialExpressionDivide", 2),
    "MINIMUM": ("MaterialExpressionMin", 2),
    "MAXIMUM": ("MaterialExpressionMax", 2),
    "POWER": ("MaterialExpressionPower", 2),
    "ABSOLUTE": ("MaterialExpressionAbs", 1),
    "FLOOR": ("MaterialExpressionFloor", 1),
    "CEIL": ("MaterialExpressionCeil", 1),
    "FRACT": ("MaterialExpressionFrac", 1),
    "SQRT": ("MaterialExpressionSquareRoot", 1),
    "SINE": ("MaterialExpressionSine", 1),
    "COSINE": ("MaterialExpressionCosine", 1),
}


@_mat("MATH", C.EXACT, "Material arithmetic expressions", "Scalar math maps onto material expressions.", classify=lambda op, g, base: Classification(C.UNSUPPORTED, f"Math {op.params.get('operation')} has no material mapping here.", "none") if op.params.get("operation") not in MATH_UE else None)
def _math(mb: MaterialBuilder, op: SemanticOp) -> dict:
    class_name, arity = MATH_UE[op.params["operation"]]
    if arity == 2 and class_name == "MaterialExpressionPower":
        var = mb.expression(op, class_name)
        mb.feed(var, "Base", op.inputs.get("a"), F, 0.0)
        mb.feed(var, "Exp", op.inputs.get("b"), F, 1.0)
    elif arity == 2:
        var = mb.binary(op, class_name, op.inputs.get("a"), op.inputs.get("b"), F)
    else:
        var = mb.unary(op, class_name, op.inputs.get("a"), F)
        if class_name in ("MaterialExpressionSine", "MaterialExpressionCosine"):
            mb.prop(var, "period", "6.283185")
    if op.params.get("clamp"):
        var = mb.unary(op, "MaterialExpressionSaturate", (var, ""), F, "_clamp")
    return {"value": (var, "")}


VECTOR_UE = {"ADD": "MaterialExpressionAdd", "SUBTRACT": "MaterialExpressionSubtract", "MULTIPLY": "MaterialExpressionMultiply", "DIVIDE": "MaterialExpressionDivide", "SCALE": "MaterialExpressionMultiply", "DOT_PRODUCT": "MaterialExpressionDotProduct", "CROSS_PRODUCT": "MaterialExpressionCrossProduct", "NORMALIZE": "MaterialExpressionNormalize"}


@_mat("VECTOR_MATH", C.EXACT, "Material vector expressions", "Vector math maps onto material expressions.", classify=lambda op, g, base: Classification(C.UNSUPPORTED, f"Vector Math {op.params.get('operation')} has no material mapping here.", "none") if op.params.get("operation") not in VECTOR_UE else None)
def _vector_math(mb: MaterialBuilder, op: SemanticOp) -> dict:
    operation = op.params["operation"]
    class_name = VECTOR_UE[operation]
    if operation == "NORMALIZE":
        var = mb.unary(op, class_name, op.inputs.get("a"), V)
    elif operation == "SCALE":
        var = mb.binary(op, class_name, op.inputs.get("a"), op.inputs.get("scale"), V)
    else:
        var = mb.expression(op, class_name)
        mb.feed(var, "A", op.inputs.get("a"), V, [0, 0, 0])
        mb.feed(var, "B", op.inputs.get("b"), V, [0, 0, 0])
    return {"vector": (var, ""), "value": (var, "")}


@_mat("MIX", C.EXACT, "LinearInterpolate", "Mix, Multiply and Add blends rebuilt with Lerp.", classify=lambda op, g, base: Classification(C.APPROXIMATE, f"Blend mode {op.params.get('blend_type')} is approximated as Mix.", base.implementation) if op.params.get("blend_type", "MIX") not in ("MIX", "MULTIPLY", "ADD") else None)
def _mix(mb: MaterialBuilder, op: SemanticOp) -> dict:
    want = {"RGBA": COL, "VECTOR": V}.get(op.params.get("data_type", "FLOAT"), F)
    blend = op.params.get("blend_type", "MIX")
    lerp = mb.expression(op, "MaterialExpressionLinearInterpolate")
    mb.feed(lerp, "A", op.inputs.get("a"), want, 0.0)
    if blend in ("MULTIPLY", "ADD"):
        combined = mb.binary(op, "MaterialExpressionMultiply" if blend == "MULTIPLY" else "MaterialExpressionAdd", op.inputs.get("a"), op.inputs.get("b"), want, "_blend")
        mb.w.line(f"nb_link({combined}, '', {lerp}, 'B')")
    else:
        mb.feed(lerp, "B", op.inputs.get("b"), want, 1.0)
    mb.feed(lerp, "Alpha", op.inputs.get("factor"), F, 0.5)
    return {"result": (lerp, "")}


@_mat("MAPPING", C.EXACT, "Multiply + Add", "Point mapping: vector * scale + location.", classify=lambda op, g, base: Classification(C.APPROXIMATE, "Mapping rotation is not translated.", base.implementation) if not (isinstance(op.inputs.get("rotation"), Const) and not any(op.inputs["rotation"].value)) else None)
def _mapping(mb: MaterialBuilder, op: SemanticOp) -> dict:
    var = mb.expression(op, "MaterialExpressionMultiply", "_scale")
    mb.feed(var, "A", op.inputs.get("vector"), V, [0, 0, 0])
    mb.feed(var, "B", op.inputs.get("scale"), V, [1, 1, 1])
    location = op.inputs.get("location")
    if location is not None and not (isinstance(location, Const) and not any(location.value)):
        moved = mb.expression(op, "MaterialExpressionAdd", "_offset")
        mb.w.line(f"nb_link({var}, '', {moved}, 'A')")
        mb.feed(moved, "B", location, V, [0, 0, 0])
        var = moved
    return {"vector": (var, "")}


@_mat(
    "BUMP",
    C.APPROXIMATE,
    "DDX/DDY screen-space bump",
    "Height-based bump approximated from screen-space derivatives (no height-to-normal expression is constructible from Python).",
    ("Bump detail depends on screen resolution; strength is matched only roughly.",),
)
def _bump(mb: MaterialBuilder, op: SemanticOp) -> dict:
    height = mb.source(op.inputs.get("height"), F, 0.0)
    ddx = mb.unary(op, "MaterialExpressionDDX", height, F, "_ddx")
    ddy = mb.unary(op, "MaterialExpressionDDY", height, F, "_ddy")
    strength = op.inputs.get("strength")
    scale = -float(strength.value if isinstance(strength, Const) else 1.0) * 100.0
    gx = mb.expression(op, "MaterialExpressionMultiply", "_gx")
    mb.w.line(f"nb_link({ddx}, '', {gx}, 'A')")
    mb.prop(gx, "const_b", literal(clean_number(scale)))
    gy = mb.expression(op, "MaterialExpressionMultiply", "_gy")
    mb.w.line(f"nb_link({ddy}, '', {gy}, 'A')")
    mb.prop(gy, "const_b", literal(clean_number(scale)))
    xy = mb.expression(op, "MaterialExpressionAppendVector", "_xy")
    mb.w.line(f"nb_link({gx}, '', {xy}, 'A')")
    mb.w.line(f"nb_link({gy}, '', {xy}, 'B')")
    xyz = mb.expression(op, "MaterialExpressionAppendVector", "_xyz")
    mb.w.line(f"nb_link({xy}, '', {xyz}, 'A')")
    one, _ = mb.constant(1.0, F)
    mb.w.line(f"nb_link({one}, '', {xyz}, 'B')")
    normal = mb.unary(op, "MaterialExpressionNormalize", (xyz, ""), V, "_normal")
    return {"normal": (normal, "")}


@_mat("NORMAL_MAP", C.EQUIVALENT, "Normal map with green flip", "Tangent-space normal map; Blender's OpenGL convention is converted to Unreal's DirectX convention by flipping green.")
def _normal_map(mb: MaterialBuilder, op: SemanticOp) -> dict:
    flip = mb.expression(op, "MaterialExpressionMultiply", "_green_flip")
    mb.feed(flip, "A", op.inputs.get("color"), V, [0.5, 0.5, 1.0])
    constant, _ = mb.constant([1.0, -1.0, 1.0], V)
    mb.w.line(f"nb_link({constant}, '', {flip}, 'B')")
    return {"normal": (flip, "")}


@_mat("TEXTURE_SAMPLE", C.EQUIVALENT, "TextureSample", "Image texture sample; the texture asset must be imported into Unreal.", ("The script looks for /Game/NodeBridge/Textures/<image name>.",))
def _image(mb: MaterialBuilder, op: SemanticOp) -> dict:
    var = mb.expression(op, "MaterialExpressionTextureSample")
    image = op.inputs.get("image")
    name = image.value.get("name", "") if isinstance(image, Const) and isinstance(image.value, dict) else ""
    if name:
        mb.w.line(f'nb_prop({var}, "texture", unreal.EditorAssetLibrary.load_asset(ASSET_PATH + "/Textures/{unreal_asset_name(name.rsplit(".", 1)[0], "T_")}"))')
    vector = op.inputs.get("vector")
    if isinstance(vector, Link):
        mb.feed(var, "UVs", vector, V)
    return {"color": (var, "RGB"), "alpha": (var, "A")}


@_mat("COMBINE_VECTOR", C.EXACT, "AppendVector", "Vector construction.")
def _combine(mb: MaterialBuilder, op: SemanticOp) -> dict:
    xy = mb.expression(op, "MaterialExpressionAppendVector", "_xy")
    mb.feed(xy, "A", op.inputs.get("x"), F, 0.0)
    mb.feed(xy, "B", op.inputs.get("y"), F, 0.0)
    xyz = mb.expression(op, "MaterialExpressionAppendVector")
    mb.w.line(f"nb_link({xy}, '', {xyz}, 'A')")
    mb.feed(xyz, "B", op.inputs.get("z"), F, 0.0)
    return {"vector": (xyz, "")}


@_mat("SEPARATE_VECTOR", C.EXACT, "ComponentMask", "Component access.")
def _separate(mb: MaterialBuilder, op: SemanticOp) -> dict:
    source = mb.source(op.inputs.get("vector"), V, [0, 0, 0])
    outputs = {}
    for axis, channel in (("x", "r"), ("y", "g"), ("z", "b")):
        mask = mb.expression(op, "MaterialExpressionComponentMask", f"_{axis}")
        mb.prop(mask, channel, "True")
        mb.w.line(f"nb_link({source[0]}, {source[1]!r}, {mask}, '')")
        outputs[axis] = (mask, "")
    return outputs


@_mat("COLOR_OPERATION", C.EXACT, "OneMinus / Desaturation", "Invert and grayscale conversions.", classify=lambda op, g, base: Classification(C.UNSUPPORTED, f"Color operation {op.params.get('operation')} is not translated yet.", "none") if op.params.get("operation") not in ("invert", "rgb_to_bw") else None)
def _color_op(mb: MaterialBuilder, op: SemanticOp) -> dict:
    if op.params.get("operation") == "invert":
        return {"color": (mb.unary(op, "MaterialExpressionOneMinus", op.inputs.get("color"), COL), "")}
    var = mb.unary(op, "MaterialExpressionDesaturation", op.inputs.get("color"), COL)
    return {"value": (var, "")}
