"""Field expressions -> VEX.

Geometry Nodes fields have no SOP equivalent: they are lazily evaluated
per element. NodeBridge compiles each field expression consumed by a
geometry operation into an Attribute Wrangle that runs over the domain
the consumer evaluates it on. Expressions are evaluated in Blender's
frame; ``nb_b`` / ``nb_h`` convert at the boundary.

Every field operation registers a translator in context ``"sop"``; the
function receives the :class:`VexCompiler` and returns its outputs as
``{output: (vex_expression, DataType)}``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...backend.codegen import clean_number
from ...common.units import ValueRole
from ...ir.semantic import Const, InputValue, Link, Param, SemanticOp
from ...ir.types import DataType
from ...translation.confidence import Classification, Confidence as C
from ...translation.registry import translator
from .vexlib import LIBRARIES, ORDER

if TYPE_CHECKING:
    from .sop import SopBuilder

T, CTX = "houdini", "sop"
VEC_TYPES = {DataType.VECTOR3, DataType.COLOR, DataType.ROTATION, DataType.VECTOR4, DataType.VECTOR2}
VEX_TYPE = {DataType.FLOAT: "float", DataType.INT: "int", DataType.BOOL: "int"}
DOMAIN_CLASS = {"detail": 0, "prim": 1, "point": 2, "vertex": 3}
ELEMENT = {"point": "@ptnum", "prim": "@primnum", "vertex": "@vtxnum", "detail": "0"}


class VexError(Exception):
    pass


def vex_type(data_type: DataType) -> str:
    return "vector" if data_type in VEC_TYPES else VEX_TYPE.get(data_type, "float")


def vex_literal(value: Any, data_type: DataType) -> str:
    if data_type in VEC_TYPES:
        items = value if isinstance(value, (list, tuple)) else [value] * 3
        items = (list(items) + [0.0, 0.0, 0.0])[:3]
        return "set(" + ", ".join(_num(v) for v in items) + ")"
    if isinstance(value, (list, tuple)):
        value = sum(float(v) for v in value[:3]) / max(len(value[:3]), 1)
    if data_type in (DataType.INT, DataType.BOOL):
        return str(int(round(float(value or 0))))
    return _num(value or 0.0)


def _num(value: Any) -> str:
    number = clean_number(float(value))
    text = repr(number)
    return text if "." in text or "e" in text else text + ".0"


def coerce(expr: str, source: DataType, target: DataType) -> str:
    src_vec, dst_vec = source in VEC_TYPES, target in VEC_TYPES
    if source == target or (src_vec and dst_vec) or target == DataType.ANY:
        return expr
    if dst_vec:
        return f"set(float({expr}), float({expr}), float({expr}))"
    if src_vec:
        scalar = f"avg({expr})"
        if target == DataType.BOOL:
            return f"(length({expr}) != 0)"
        return f"int({scalar})" if target == DataType.INT else scalar
    if target == DataType.FLOAT:
        return f"float({expr})"
    if target == DataType.INT and source == DataType.FLOAT:
        return f"int({expr})"
    if target == DataType.BOOL and source == DataType.FLOAT:
        return f"({expr} != 0)"
    return expr


class VexCompiler:
    """Compiles the field expressions used by one wrangle."""

    def __init__(self, builder: "SopBuilder", domain: str = "point") -> None:
        self.b = builder
        self.graph = builder.graph
        self.domain = domain
        self.lines: list[str] = []
        self.libraries: set[str] = {"coordinates"}
        self.side_inputs: list[tuple[str, Any]] = []
        self._cache: dict[str, dict[str, tuple[str, DataType]]] = {}
        self._counter = 0
        self.notes: list[str] = []
        self.sources: list[str] = []

    # -- infrastructure ------------------------------------------------
    @property
    def element(self) -> str:
        return ELEMENT[self.domain]

    def need(self, library: str) -> None:
        self.libraries.add(library)

    def tmp(self, prefix: str, data_type: DataType, expr: str) -> str:
        self._counter += 1
        name = f"{prefix}{self._counter}"
        self.lines.append(f"{vex_type(data_type)} {name} = {expr};")
        return name

    def stmt(self, line: str) -> None:
        self.lines.append(line)

    def side_input(self, key: str, stream) -> int:
        for index, (existing, _) in enumerate(self.side_inputs):
            if existing == key:
                return index + 1
        if len(self.side_inputs) >= 3:
            raise VexError("a wrangle supports at most three extra geometry inputs")
        self.side_inputs.append((key, stream))
        return len(self.side_inputs)

    # -- values ----------------------------------------------------------
    def value(self, value: InputValue | None, want: DataType, *, default: Any = 0.0) -> str:
        if value is None:
            return vex_literal(default, want)
        if isinstance(value, Const):
            return vex_literal(value.value if value.value is not None else default, want)
        if isinstance(value, Param):
            return coerce(self.param(value.name), self.b.param_type(value.name), want)
        if isinstance(value, Link):
            expr, produced = self.output(value)
            return coerce(expr, produced, want)
        if isinstance(value, tuple) and value:
            return self.value(value[0], want, default=default)
        return vex_literal(default, want)

    def param(self, key: str) -> str:
        parameter = self.b.parameter(key)
        path = self.b.network.param_path(parameter.key if parameter else key)
        if parameter is None:
            return "0.0"
        if parameter.data_type in VEC_TYPES:
            raw = f'chv("{path}")'
            if parameter.role in (ValueRole.POSITION, ValueRole.DIRECTION, ValueRole.NORMAL):
                return f"nb_b({raw})"
            if parameter.role == ValueRole.SCALE:
                return f"nb_bs({raw})"
            if parameter.role == ValueRole.EULER:
                return f"radians(set({raw}.x, -{raw}.z, {raw}.y))"
            return raw
        if parameter.data_type in (DataType.INT, DataType.BOOL):
            return f'chi("{path}")'
        if parameter.role in (ValueRole.ANGLE,):
            return f'radians(chf("{path}"))'
        return f'chf("{path}")'

    def output(self, link: Link) -> tuple[str, DataType]:
        op = self.graph.ops[link.op]
        if op.id not in self._cache:
            self._cache[op.id] = self.emit(op)
        outputs = self._cache[op.id]
        if link.output not in outputs:
            raise VexError(f"{op.kind} output {link.output!r} is not available in VEX")
        return outputs[link.output]

    def emit(self, op: SemanticOp) -> dict[str, tuple[str, DataType]]:
        reader = self.b.field_reader(op)
        if reader is not None:
            return reader(self, op)
        item = self.b.backend.translator(op, CTX)
        if item is None or op.kind == "UNSUPPORTED_OPERATION":
            self.notes.append(f"{op.display_name}: no VEX translation; zero is used instead.")
            self.stmt(f"// UNSUPPORTED: {op.display_name} ({op.kind}) -> zero")
            return {name: (vex_literal(0.0, ref.base), ref.base) for name, ref in op.outputs.items()}
        result = item.fn(self, op)
        self.sources.append(op.display_name)
        return result

    def parts(self, body: list[str]) -> tuple[list[str], str]:
        """(library names in dependency order, snippet body)."""
        libraries = [name for name in ORDER if name in self.libraries]
        header = [f"// Blender fields: {', '.join(dict.fromkeys(self.sources))}"] if self.sources else []
        return libraries, "\n".join(header + self.lines + body).rstrip() + "\n"

    def snippet(self, body: list[str]) -> str:
        libraries, text = self.parts(body)
        return "#include <math.h>\n\n" + "".join(LIBRARIES[name] + "\n" for name in libraries) + text


def library_constant(name: str) -> str:
    return f"NB_VEX_{name.upper()}"


def library_definitions(names: set[str]) -> list[str]:
    """Python source lines defining the VEX library strings used by a script."""
    lines = ['NB_VEX_HEADER = "#include <math.h>\\n\\n"']
    for name in ORDER:
        if name in names:
            lines.append(f'{library_constant(name)} = """\\')
            lines.extend(LIBRARIES[name].rstrip("\n").splitlines())
            lines.append('"""')
    lines.append("")
    return lines


def _v(vc: VexCompiler, op: SemanticOp, name: str, want: DataType, default: Any = 0.0) -> str:
    return vc.value(op.inputs.get(name), want, default=default)


F, I, B, V = DataType.FLOAT, DataType.INT, DataType.BOOL, DataType.VECTOR3


# --- built-in fields ----------------------------------------------------------
def _field_input(vc: VexCompiler, op: SemanticOp):
    field = op.params.get("field")
    if field == "position":
        if vc.domain == "prim":
            vc.need("primitives")
            return {"value": ("nb_b(nb_prim_center(0, @primnum))", V)}
        return {"value": ("nb_b(v@P)", V)}
    if field == "normal":
        if vc.domain == "prim":
            return {"value": ("nb_b(prim_normal(0, @primnum, 0.5, 0.5))", V)}
        index = vc.side_input("point_normals", vc.b.current_stream)
        return {"value": (f'nb_b(point({index}, "N", @ptnum))', V)}
    if field == "index":
        return {"value": (vc.element, I)}
    if field == "id":
        if vc.domain == "point":
            return {"value": ('(haspointattrib(0, "id") ? point(0, "id", @ptnum) : @ptnum)', I)}
        return {"value": (vc.element, I)}
    raise VexError(f"field {field!r} is not available in SOP context")


def _classify_field_input(op, graph, base):
    if op.params.get("field") not in ("position", "normal", "index", "id"):
        return Classification(C.UNSUPPORTED, f"The {op.params.get('field')} field has no SOP equivalent.", "none")
    return None


translator(
    "FIELD_INPUT",
    target=T,
    context=CTX,
    confidence=C.EXACT,
    implementation="VEX @P / @N / @ptnum / id",
    explanation="Built-in attributes read in a wrangle and converted to Blender's Z-up frame.",
    limitations=("Point normals come from a Normal SOP side input (area-weighted, no cusping).",),
    classify=_classify_field_input,
)(_field_input)


@translator("ATTRIBUTE_READ", target=T, context=CTX, confidence=C.EXACT, implementation="VEX point()/prim()", explanation="Named attribute read; Blender built-in names are mapped (position->P, normal->N).")
def _attribute_read(vc: VexCompiler, op: SemanticOp):
    name = op.inputs.get("name")
    if not isinstance(name, Const):
        raise VexError("attribute name must be constant")
    attr = vc.b.attribute_name(str(name.value))
    data_type = op.outputs["value"].base
    reader = "point" if vc.domain == "point" else "prim"
    expr = f'{reader}(0, "{attr}", {vc.element})'
    if attr in ("P", "N"):
        expr = f"nb_b({expr})"
    exists = f'has{"point" if vc.domain == "point" else "prim"}attrib(0, "{attr}")'
    return {"value": (expr, data_type), "exists": (exists, B)}


def _random_classify(op, graph, base):
    return None


@translator(
    "RANDOM",
    target=T,
    context=CTX,
    confidence=C.EQUIVALENT,
    implementation="VEX nb_random(seed, id)",
    explanation="Per-element random values from NodeBridge's deterministic hash.",
    limitations=("Blender and NodeBridge use different random generators: same distribution, different samples.",),
)
def _random(vc: VexCompiler, op: SemanticOp):
    vc.need("random")
    seed = _v(vc, op, "seed", I, 0)
    element = _v(vc, op, "id", I, 0)
    data_type = op.params.get("data_type", "FLOAT")
    if not vc.b.options.deterministic_random:
        rnd = lambda stream: f"rand(set(float({element}), float({seed}), {stream}.0))"  # noqa: E731
    else:
        rnd = lambda stream: f"nb_random({seed}, {element}, {stream})"  # noqa: E731
    if data_type == "FLOAT":
        return {"value": (f"fit01({rnd(0)}, {_v(vc, op, 'min', F, 0.0)}, {_v(vc, op, 'max', F, 1.0)})", F)}
    if data_type == "INT":
        lo, hi = _v(vc, op, "min", I, 0), _v(vc, op, "max", I, 100)
        return {"value": (f"min(int(floor(fit01({rnd(0)}, {lo}, {hi} + 1))), {hi})", I)}
    if data_type == "BOOLEAN":
        return {"value": (f"({rnd(0)} < {_v(vc, op, 'probability', F, 0.5)})", B)}
    lo = vc.tmp("nb_lo", V, _v(vc, op, "min", V, 0.0))
    hi = vc.tmp("nb_hi", V, _v(vc, op, "max", V, 1.0))
    return {"value": (f"set(fit01({rnd(0)}, {lo}.x, {hi}.x), fit01({rnd(1)}, {lo}.y, {hi}.y), fit01({rnd(2)}, {lo}.z, {hi}.z))", V)}


@translator(
    "NOISE",
    target=T,
    context=CTX,
    confidence=C.APPROXIMATE,
    implementation="VEX fractal noise()",
    explanation="Source uses Blender's noise implementation; target uses Houdini's noise() in an fBm loop.",
    limitations=("Pattern will not be numerically identical.", "Distortion and 4D (W) noise are not translated."),
)
def _noise(vc: VexCompiler, op: SemanticOp):
    vc.need("noise")
    p = vc.tmp("nb_p", V, f"{_v(vc, op, 'vector', V)} * {_v(vc, op, 'scale', F, 5.0)}")
    args = f"{_v(vc, op, 'detail', F, 2.0)}, {_v(vc, op, 'roughness', F, 0.5)}, {_v(vc, op, 'lacunarity', F, 2.0)}"
    fac = vc.tmp("nb_noise", F, f"nb_fbm({p}, {args})")
    color = f"set({fac}, nb_fbm({p} + set(1.3, 7.1, 3.7), {args}), nb_fbm({p} + set(4.9, 2.3, 8.2), {args}))"
    return {"fac": (fac, F), "color": (color, DataType.COLOR)}


@translator(
    "VORONOI",
    target=T,
    context=CTX,
    confidence=C.APPROXIMATE,
    implementation="VEX vnoise()",
    explanation="Worley noise via VEX vnoise(); cell layout differs from Blender.",
    limitations=("Only F1 Euclidean distance is mapped; cell colors are random per cell but differ from Blender.",),
)
def _voronoi(vc: VexCompiler, op: SemanticOp):
    p = vc.tmp("nb_vp", V, f"{_v(vc, op, 'vector', V)} * {_v(vc, op, 'scale', F, 5.0)}")
    jitter = _v(vc, op, "randomness", F, 1.0)
    vc.stmt("int nb_vseed; float nb_f1, nb_f2; vector nb_vp1, nb_vp2;")
    vc.stmt(f"vnoise({p}, set({jitter}, {jitter}, {jitter}), nb_vseed, nb_f1, nb_f2, nb_vp1, nb_vp2);")
    return {
        "distance": ("nb_f1", F),
        "color": ("rand(set(float(nb_vseed), 1.0, 2.0))", DataType.COLOR),
        "position": (f"nb_vp1 / max({_v(vc, op, 'scale', F, 5.0)}, 1e-6)", V),
    }


@translator(
    "MAP_RANGE",
    target=T,
    context=CTX,
    confidence=C.EXACT,
    implementation="VEX fit()/efit()",
    explanation="Linear, stepped, smoothstep and smootherstep remapping reproduced exactly.",
)
def _map_range(vc: VexCompiler, op: SemanticOp):
    vector = op.params.get("data_type") == "FLOAT_VECTOR"
    t_ = V if vector else F
    names = ("value", "from_min", "from_max", "to_min", "to_max")
    defaults = (1.0, 0.0, 1.0, 0.0, 1.0)
    value, fmin, fmax, tmin, tmax = (vc.tmp("nb_mr", t_, _v(vc, op, n, t_, d)) for n, d in zip(names, defaults))
    clamp = op.params.get("clamp", True)
    interpolation = op.params.get("interpolation", "LINEAR")
    span = vc.tmp("nb_span", t_, f"{fmax} - {fmin}")
    if vector:
        t = vc.tmp("nb_t", V, f"nb_safe_div3({value} - {fmin}, {span})")
        vc.need("safe")
    else:
        t = vc.tmp("nb_t", F, f"{span} != 0 ? ({value} - {fmin}) / {span} : 0.0")
    if interpolation == "STEPPED":
        steps = _v(vc, op, "steps", t_, 4.0)
        vc.stmt(f"{t} = {steps} > 0 ? floor({t} * ({steps} + 1)) / {steps} : {t};")
    if clamp or interpolation in ("SMOOTHSTEP", "SMOOTHERSTEP"):
        vc.stmt(f"{t} = clamp({t}, 0.0, 1.0);")
    if interpolation == "SMOOTHSTEP":
        vc.stmt(f"{t} = {t} * {t} * (3.0 - 2.0 * {t});")
    elif interpolation == "SMOOTHERSTEP":
        vc.stmt(f"{t} = {t} * {t} * {t} * ({t} * ({t} * 6.0 - 15.0) + 10.0);")
    return {"result": (f"{tmin} + {t} * ({tmax} - {tmin})", t_)}


MATH_VEX = {
    "ADD": "{a} + {b}",
    "SUBTRACT": "{a} - {b}",
    "MULTIPLY": "{a} * {b}",
    "DIVIDE": "({b} != 0 ? {a} / {b} : 0.0)",
    "MULTIPLY_ADD": "{a} * {b} + {c}",
    "POWER": "({a} < 0 && {b} != floor({b}) ? 0.0 : pow({a}, {b}))",
    "LOGARITHM": "({a} > 0 && {b} > 0 && {b} != 1 ? log({a}) / log({b}) : 0.0)",
    "SQRT": "({a} > 0 ? sqrt({a}) : 0.0)",
    "INVERSE_SQRT": "({a} > 0 ? 1.0 / sqrt({a}) : 0.0)",
    "ABSOLUTE": "abs({a})",
    "EXPONENT": "exp({a})",
    "MINIMUM": "min({a}, {b})",
    "MAXIMUM": "max({a}, {b})",
    "LESS_THAN": "({a} < {b} ? 1.0 : 0.0)",
    "GREATER_THAN": "({a} > {b} ? 1.0 : 0.0)",
    "SIGN": "sign({a})",
    "COMPARE": "(abs({a} - {b}) <= max({c}, 1e-5) ? 1.0 : 0.0)",
    "SMOOTH_MIN": "({c} != 0 ? min({a}, {b}) - pow(max({c} - abs({a} - {b}), 0.0) / {c}, 3) * {c} / 6.0 : min({a}, {b}))",
    "SMOOTH_MAX": "({c} != 0 ? max({a}, {b}) + pow(max({c} - abs({a} - {b}), 0.0) / {c}, 3) * {c} / 6.0 : max({a}, {b}))",
    "ROUND": "floor({a} + 0.5)",
    "FLOOR": "floor({a})",
    "CEIL": "ceil({a})",
    "TRUNC": "trunc({a})",
    "FRACT": "frac({a})",
    "MODULO": "({b} != 0 ? {a} % {b} : 0.0)",
    "FLOORED_MODULO": "({b} != 0 ? {a} - floor({a} / {b}) * {b} : 0.0)",
    "WRAP": "({b} - {c} != 0 ? {a} - ({b} - {c}) * floor(({a} - {c}) / ({b} - {c})) : {c})",
    "SNAP": "({b} != 0 ? floor({a} / {b}) * {b} : 0.0)",
    "PINGPONG": "({b} != 0 ? abs(({a} - {b}) % (2.0 * {b}) - {b}) : 0.0)",
    "SINE": "sin({a})",
    "COSINE": "cos({a})",
    "TANGENT": "tan({a})",
    "ARCSINE": "asin(clamp({a}, -1.0, 1.0))",
    "ARCCOSINE": "acos(clamp({a}, -1.0, 1.0))",
    "ARCTANGENT": "atan({a})",
    "ARCTAN2": "atan2({a}, {b})",
    "SINH": "sinh({a})",
    "COSH": "cosh({a})",
    "TANH": "tanh({a})",
    "RADIANS": "radians({a})",
    "DEGREES": "degrees({a})",
    "CLAMP_MINMAX": "clamp({a}, {b}, {c})",
    "CLAMP_RANGE": "clamp({a}, min({b}, {c}), max({b}, {c}))",
}


def _math_classify(op, graph, base):
    if op.params.get("operation") not in MATH_VEX:
        return Classification(C.UNSUPPORTED, f"Math operation {op.params.get('operation')} has no VEX mapping.", "none")
    return None


@translator("MATH", target=T, context=CTX, confidence=C.EXACT, implementation="VEX arithmetic", explanation="Blender math (including safe division/modulo) reproduced in VEX.", classify=_math_classify)
def _math(vc: VexCompiler, op: SemanticOp):
    template = MATH_VEX.get(op.params.get("operation", "ADD"))
    if template is None:
        raise VexError(f"math operation {op.params.get('operation')}")
    args = {k: vc.tmp("nb_m", F, _v(vc, op, k, F, 0.0)) if template.count("{" + k + "}") > 1 else _v(vc, op, k, F, 0.0) for k in "abc"}
    expr = template.format(**args)
    if op.params.get("clamp"):
        expr = f"clamp({expr}, 0.0, 1.0)"
    out_type = op.outputs["value"].base if op.outputs.get("value") else F
    return {"value": (f"int({expr})" if out_type == I else f"({expr})", out_type)}


VECTOR_VEX = {
    "ADD": ("v", "{a} + {b}"),
    "SUBTRACT": ("v", "{a} - {b}"),
    "MULTIPLY": ("v", "{a} * {b}"),
    "DIVIDE": ("v", "nb_safe_div3({a}, {b})"),
    "MULTIPLY_ADD": ("v", "{a} * {b} + {c}"),
    "CROSS_PRODUCT": ("v", "cross({a}, {b})"),
    "PROJECT": ("v", "(dot({b}, {b}) != 0 ? dot({a}, {b}) / dot({b}, {b}) * {b} : set(0.0, 0.0, 0.0))"),
    "REFLECT": ("v", "reflect({a}, normalize({b}))"),
    "DOT_PRODUCT": ("f", "dot({a}, {b})"),
    "DISTANCE": ("f", "distance({a}, {b})"),
    "LENGTH": ("f", "length({a})"),
    "SCALE": ("v", "{a} * {s}"),
    "NORMALIZE": ("v", "normalize({a})"),
    "ABSOLUTE": ("v", "abs({a})"),
    "MINIMUM": ("v", "min({a}, {b})"),
    "MAXIMUM": ("v", "max({a}, {b})"),
    "FLOOR": ("v", "floor({a})"),
    "CEIL": ("v", "ceil({a})"),
    "FRACTION": ("v", "frac({a})"),
    "SINE": ("v", "set(sin({a}.x), sin({a}.y), sin({a}.z))"),
    "COSINE": ("v", "set(cos({a}.x), cos({a}.y), cos({a}.z))"),
    "TANGENT": ("v", "set(tan({a}.x), tan({a}.y), tan({a}.z))"),
}


def _vector_math_classify(op, graph, base):
    if op.params.get("operation") not in VECTOR_VEX:
        return Classification(C.UNSUPPORTED, f"Vector Math {op.params.get('operation')} has no VEX mapping.", "none")
    return None


@translator("VECTOR_MATH", target=T, context=CTX, confidence=C.EXACT, implementation="VEX vector math", explanation="Vector operations reproduced in VEX.", classify=_vector_math_classify)
def _vector_math(vc: VexCompiler, op: SemanticOp):
    kind, template = VECTOR_VEX[op.params.get("operation", "ADD")]
    if "nb_safe_div3" in template:
        vc.need("safe")
    args = {k: vc.tmp("nb_vec", V, _v(vc, op, k, V, 0.0)) for k in "abc" if "{" + k + "}" in template}
    args["s"] = _v(vc, op, "scale", F, 1.0)
    expr = template.format(**args)
    if kind == "v":
        return {"vector": (expr, V), "value": (f"length({expr})", F)}
    return {"value": (expr, F), "vector": (f"set({expr}, {expr}, {expr})", V)}


COMPARE_VEX = {"LESS_THAN": "<", "LESS_EQUAL": "<=", "GREATER_THAN": ">", "GREATER_EQUAL": ">="}


@translator("COMPARE", target=T, context=CTX, confidence=C.EXACT, implementation="VEX comparison", explanation="Float, integer and vector comparisons reproduced in VEX.")
def _compare(vc: VexCompiler, op: SemanticOp):
    data_type = op.params.get("data_type", "FLOAT")
    operation = op.params.get("operation", "GREATER_THAN")
    t_ = {"FLOAT": F, "INT": I, "VECTOR": V, "RGBA": DataType.COLOR}.get(data_type, F)
    a, b = _v(vc, op, "a", t_), _v(vc, op, "b", t_)
    epsilon = _v(vc, op, "epsilon", F, 0.001)
    if t_ in (F, I):
        if operation in COMPARE_VEX:
            return {"result": (f"({a} {COMPARE_VEX[operation]} {b})", B)}
        if operation == "EQUAL":
            return {"result": (f"(abs({a} - {b}) <= {epsilon})", B)}
        if operation == "NOT_EQUAL":
            return {"result": (f"(abs({a} - {b}) > {epsilon})", B)}
    mode = op.params.get("mode", "ELEMENT")
    if mode == "LENGTH" and operation in COMPARE_VEX:
        return {"result": (f"(length({a}) {COMPARE_VEX[operation]} length({b}))", B)}
    if mode == "AVERAGE" and operation in COMPARE_VEX:
        return {"result": (f"(avg({a}) {COMPARE_VEX[operation]} avg({b}))", B)}
    va, vb = vc.tmp("nb_ca", V, a), vc.tmp("nb_cb", V, b)
    if operation in COMPARE_VEX:
        sym = COMPARE_VEX[operation]
        return {"result": (f"({va}.x {sym} {vb}.x && {va}.y {sym} {vb}.y && {va}.z {sym} {vb}.z)", B)}
    if operation == "EQUAL":
        return {"result": (f"(distance({va}, {vb}) <= {epsilon})", B)}
    return {"result": (f"(distance({va}, {vb}) > {epsilon})", B)}


BOOLEAN_VEX = {
    "AND": "({a} && {b})",
    "OR": "({a} || {b})",
    "NOT": "(!{a})",
    "NAND": "(!({a} && {b}))",
    "NOR": "(!({a} || {b}))",
    "XNOR": "({a} == {b})",
    "XOR": "({a} != {b})",
    "IMPLY": "(!{a} || {b})",
    "NIMPLY": "({a} && !{b})",
}


@translator("BOOLEAN_MATH", target=T, context=CTX, confidence=C.EXACT, implementation="VEX logic", explanation="Boolean logic reproduced in VEX.")
def _boolean_math(vc: VexCompiler, op: SemanticOp):
    a, b = vc.tmp("nb_ba", B, _v(vc, op, "a", B, 0)), _v(vc, op, "b", B, 0)
    return {"value": (BOOLEAN_VEX[op.params.get("operation", "AND")].format(a=a, b=b), B)}


@translator("COMBINE_VECTOR", target=T, context=CTX, confidence=C.EXACT, implementation="VEX set()", explanation="Vector construction.")
def _combine(vc: VexCompiler, op: SemanticOp):
    return {"vector": (f"set({_v(vc, op, 'x', F)}, {_v(vc, op, 'y', F)}, {_v(vc, op, 'z', F)})", V)}


@translator("SEPARATE_VECTOR", target=T, context=CTX, confidence=C.EXACT, implementation="VEX components", explanation="Component access (in Blender's axis convention).")
def _separate(vc: VexCompiler, op: SemanticOp):
    v = vc.tmp("nb_sep", V, _v(vc, op, "vector", V))
    return {"x": (f"{v}.x", F), "y": (f"{v}.y", F), "z": (f"{v}.z", F)}


BLEND_VEX = {
    "MIX": "lerp({a}, {b}, {f})",
    "MULTIPLY": "lerp({a}, {a} * {b}, {f})",
    "ADD": "({a} + {b} * {f})",
    "SUBTRACT": "({a} - {b} * {f})",
    "SCREEN": "(1.0 - ((1.0 - {f}) + {f} * (1.0 - {b})) * (1.0 - {a}))",
    "DARKEN": "lerp({a}, min({a}, {b}), {f})",
    "LIGHTEN": "lerp({a}, max({a}, {b}), {f})",
    "DIFFERENCE": "lerp({a}, abs({a} - {b}), {f})",
}


def _mix_classify(op, graph, base):
    if op.params.get("blend_type", "MIX") not in BLEND_VEX:
        return Classification(C.APPROXIMATE, f"Blend mode {op.params.get('blend_type')} is approximated as Mix.", "VEX lerp()")
    return None


@translator("MIX", target=T, context=CTX, confidence=C.EXACT, implementation="VEX lerp()", explanation="Mix / blend reproduced in VEX.", classify=_mix_classify)
def _mix(vc: VexCompiler, op: SemanticOp):
    t_ = {"FLOAT": F, "VECTOR": V, "RGBA": DataType.COLOR}.get(op.params.get("data_type", "FLOAT"), F)
    f = _v(vc, op, "factor", F, 0.5)
    if op.params.get("clamp_factor", True):
        f = f"clamp({f}, 0.0, 1.0)"
    f = vc.tmp("nb_f", F, f)
    a, b = vc.tmp("nb_a", t_, _v(vc, op, "a", t_)), vc.tmp("nb_b", t_, _v(vc, op, "b", t_))
    expr = BLEND_VEX.get(op.params.get("blend_type", "MIX"), BLEND_VEX["MIX"]).format(a=a, b=b, f=f)
    if op.params.get("clamp_result"):
        expr = f"clamp({expr}, 0.0, 1.0)"
    return {"result": (expr, t_)}


@translator(
    "COLOR_RAMP",
    target=T,
    context=CTX,
    confidence=C.EXACT,
    implementation="VEX piecewise interpolation",
    explanation="Linear and constant ramps are reproduced stop by stop.",
    classify=lambda op, g, base: Classification(C.APPROXIMATE, "Ease / B-spline / cardinal ramps are approximated as linear.", base.implementation) if op.params.get("interpolation", "LINEAR") not in ("LINEAR", "CONSTANT") else None,
)
def _color_ramp(vc: VexCompiler, op: SemanticOp):
    stops = sorted(op.params.get("stops") or [[0.0, [0, 0, 0, 1]], [1.0, [1, 1, 1, 1]]], key=lambda s: s[0])
    t = vc.tmp("nb_rt", F, f"clamp({_v(vc, op, 'fac', F, 0.5)}, 0.0, 1.0)")
    color = vc.tmp("nb_rc", V, vex_literal(stops[0][1][:3], V))
    alpha = vc.tmp("nb_ra", F, _num(stops[0][1][3] if len(stops[0][1]) > 3 else 1.0))
    constant = op.params.get("interpolation") == "CONSTANT"
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        c0v, c1v = vex_literal(c0[:3], V), vex_literal(c1[:3], V)
        a0, a1 = _num(c0[3] if len(c0) > 3 else 1.0), _num(c1[3] if len(c1) > 3 else 1.0)
        if constant:
            vc.stmt(f"if ({t} >= {_num(p1)}) {{ {color} = {c1v}; {alpha} = {a1}; }}")
        else:
            span = max(float(p1) - float(p0), 1e-9)
            vc.stmt(f"if ({t} > {_num(p0)}) {{ float nb_k = clamp(({t} - {_num(p0)}) / {_num(span)}, 0.0, 1.0); {color} = lerp({c0v}, {c1v}, nb_k); {alpha} = lerp({a0}, {a1}, nb_k); }}")
    return {"color": (color, DataType.COLOR), "alpha": (alpha, F)}


def vex_switch(vc: VexCompiler, op: SemanticOp):
    """Field switch (the SOP translator in sop.py dispatches here)."""
    t_ = op.outputs["output"].base
    return {"output": (f"({_v(vc, op, 'switch', B, 0)} ? {_v(vc, op, 'true', t_)} : {_v(vc, op, 'false', t_)})", t_)}


@translator(
    "SPATIAL_NOISE_MASK",
    target=T,
    context=CTX,
    confidence=C.APPROXIMATE,
    implementation="VEX fractal noise mask",
    explanation="Noise of position compared with a threshold; Houdini's noise differs numerically from Blender's.",
    limitations=("Mask boundaries follow the same parameters but not the same pattern.",),
)
def _noise_mask(vc: VexCompiler, op: SemanticOp):
    vc.need("noise")
    p = vc.tmp("nb_p", V, f"{_v(vc, op, 'vector', V)} * {_v(vc, op, 'scale', F, 5.0)}")
    n = vc.tmp("nb_noise", F, f"nb_fbm({p}, {_v(vc, op, 'detail', F, 2.0)}, {_v(vc, op, 'roughness', F, 0.5)}, {_num(op.params.get('lacunarity', 2.0))})")
    remap = op.params.get("remap")
    if remap:
        fn = "fit" if remap.get("clamp", True) else "efit"
        vc.stmt(f"{n} = {fn}({n}, {_num(remap['from_min'])}, {_num(remap['from_max'])}, {_num(remap['to_min'])}, {_num(remap['to_max'])});")
    return {"mask": (f"({n} {COMPARE_VEX[op.params['operation']]} {_v(vc, op, 'threshold', F, 0.5)})", B)}


@translator(
    "PROXIMITY",
    target=T,
    context=CTX,
    confidence=C.EXACT,
    implementation="VEX xyzdist()/nearpoint()",
    explanation="Closest point on the target geometry, read through a wrangle input.",
    classify=lambda op, g, base: Classification(C.APPROXIMATE, "Edge targets are measured against faces.", base.implementation) if op.params.get("target_element") == "EDGES" else None,
)
def _proximity(vc: VexCompiler, op: SemanticOp):
    index = vc.side_input(f"target:{op.id}", vc.b.stream_for(op.inputs.get("target")))
    source = vc.tmp("nb_src", V, f"nb_h({_v(vc, op, 'source_position', V)})")
    if op.params.get("target_element") == "POINTS":
        vc.stmt(f"int nb_pt{op.id[-3:]} = nearpoint({index}, {source});")
        pos = vc.tmp("nb_near", V, f"point({index}, \"P\", nb_pt{op.id[-3:]})")
    else:
        pos = vc.tmp("nb_near", V, f"minpos({index}, {source})")
    return {"position": (f"nb_b({pos})", V), "distance": (f"distance({source}, {pos})", F), "is_valid": (f"(npoints({index}) > 0)", B)}


@translator(
    "RAYCAST",
    target=T,
    context=CTX,
    confidence=C.EQUIVALENT,
    implementation="VEX intersect()",
    explanation="Ray intersection against the target geometry through a wrangle input.",
    limitations=("Attribute sampling at the hit point is not translated.",),
)
def _raycast(vc: VexCompiler, op: SemanticOp):
    index = vc.side_input(f"target:{op.id}", vc.b.stream_for(op.inputs.get("target")))
    origin = vc.tmp("nb_ro", V, f"nb_h({_v(vc, op, 'source_position', V)})")
    direction = vc.tmp("nb_rd", V, f"normalize(nb_h({_v(vc, op, 'ray_direction', V, [0.0, 0.0, -1.0])})) * {_v(vc, op, 'ray_length', F, 100.0)}")
    suffix = op.id[-3:]
    vc.stmt(f"vector nb_hit{suffix}; float nb_u{suffix}, nb_v{suffix};")
    vc.stmt(f"int nb_prim{suffix} = intersect({index}, {origin}, {direction}, nb_hit{suffix}, nb_u{suffix}, nb_v{suffix});")
    return {
        "is_hit": (f"(nb_prim{suffix} >= 0)", B),
        "hit_position": (f"(nb_prim{suffix} >= 0 ? nb_b(nb_hit{suffix}) : set(0.0, 0.0, 0.0))", V),
        "hit_normal": (f"(nb_prim{suffix} >= 0 ? nb_b(prim_normal({index}, nb_prim{suffix}, nb_u{suffix}, nb_v{suffix})) : set(0.0, 0.0, 0.0))", V),
        "hit_distance": (f"(nb_prim{suffix} >= 0 ? distance({origin}, nb_hit{suffix}) : 0.0)", F),
    }


@translator(
    "ALIGN_ROTATION",
    target=T,
    context=CTX,
    confidence=C.EQUIVALENT,
    implementation="VEX dihedral()",
    explanation="Rotation aligned to a vector with quaternion math.",
    limitations=("Pivot axis is always AUTO (shortest arc).",),
)
def _align(vc: VexCompiler, op: SemanticOp):
    vc.need("rotation")
    axis = {"X": "{1, 0, 0}", "Y": "{0, 1, 0}", "Z": "{0, 0, 1}"}[op.params.get("axis", "Z")]
    expr = f"nb_align_euler({_v(vc, op, 'rotation', V)}, {axis}, {_v(vc, op, 'vector', V, [0.0, 0.0, 1.0])}, {_v(vc, op, 'factor', F, 1.0)})"
    return {"rotation": (expr, DataType.ROTATION)}
