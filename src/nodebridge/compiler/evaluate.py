"""Reference evaluation of value operations (Blender semantics).

Used for constant folding and for baking single-value expressions that a
target cannot express. Each function mirrors Blender's node behaviour,
including its "safe" division, modulo and power conventions.
"""

from __future__ import annotations

import math
from typing import Any, Callable

from ..ir.semantic import Const, InputValue, Link, Param, SemanticGraph
from ..ir.types import DataType, convert_value


def _safe_div(a: float, b: float) -> float:
    return a / b if b != 0.0 else 0.0


def _safe_pow(a: float, b: float) -> float:
    if a < 0 and b != int(b):
        return 0.0
    try:
        return a**b
    except (OverflowError, ZeroDivisionError):
        return 0.0


def _wrap(value: float, high: float, low: float) -> float:
    span = high - low
    return value - span * math.floor((value - low) / span) if span != 0 else low


def _pingpong(a: float, b: float) -> float:
    return abs(math.fmod(a - b, 2 * b) - b) if b != 0 else 0.0  # Blender's definition for b > 0


MATH: dict[str, Callable[..., float]] = {
    "ADD": lambda a, b, c: a + b,
    "SUBTRACT": lambda a, b, c: a - b,
    "MULTIPLY": lambda a, b, c: a * b,
    "DIVIDE": lambda a, b, c: _safe_div(a, b),
    "MULTIPLY_ADD": lambda a, b, c: a * b + c,
    "POWER": lambda a, b, c: _safe_pow(a, b),
    "LOGARITHM": lambda a, b, c: math.log(a) / math.log(b) if a > 0 and b > 0 and b != 1 else 0.0,
    "SQRT": lambda a, b, c: math.sqrt(a) if a > 0 else 0.0,
    "INVERSE_SQRT": lambda a, b, c: 1.0 / math.sqrt(a) if a > 0 else 0.0,
    "ABSOLUTE": lambda a, b, c: abs(a),
    "EXPONENT": lambda a, b, c: math.exp(a),
    "MINIMUM": lambda a, b, c: min(a, b),
    "MAXIMUM": lambda a, b, c: max(a, b),
    "LESS_THAN": lambda a, b, c: 1.0 if a < b else 0.0,
    "GREATER_THAN": lambda a, b, c: 1.0 if a > b else 0.0,
    "SIGN": lambda a, b, c: float((a > 0) - (a < 0)),
    "COMPARE": lambda a, b, c: 1.0 if abs(a - b) <= max(c, 1e-5) else 0.0,
    "SMOOTH_MIN": lambda a, b, c: min(a, b) if c == 0 else min(a, b) - (max(c - abs(a - b), 0.0) / c) ** 3 * c / 6.0,
    "SMOOTH_MAX": lambda a, b, c: max(a, b) if c == 0 else max(a, b) + (max(c - abs(a - b), 0.0) / c) ** 3 * c / 6.0,
    "ROUND": lambda a, b, c: math.floor(a + 0.5),
    "FLOOR": lambda a, b, c: math.floor(a),
    "CEIL": lambda a, b, c: math.ceil(a),
    "TRUNC": lambda a, b, c: float(math.trunc(a)),
    "FRACT": lambda a, b, c: a - math.floor(a),
    "MODULO": lambda a, b, c: math.fmod(a, b) if b != 0 else 0.0,
    "FLOORED_MODULO": lambda a, b, c: a - math.floor(a / b) * b if b != 0 else 0.0,
    "WRAP": lambda a, b, c: _wrap(a, b, c),
    "SNAP": lambda a, b, c: math.floor(a / b) * b if b != 0 else 0.0,
    "PINGPONG": lambda a, b, c: _pingpong(a, b),
    "SINE": lambda a, b, c: math.sin(a),
    "COSINE": lambda a, b, c: math.cos(a),
    "TANGENT": lambda a, b, c: math.tan(a),
    "ARCSINE": lambda a, b, c: math.asin(a) if -1 <= a <= 1 else 0.0,
    "ARCCOSINE": lambda a, b, c: math.acos(a) if -1 <= a <= 1 else 0.0,
    "ARCTANGENT": lambda a, b, c: math.atan(a),
    "ARCTAN2": lambda a, b, c: math.atan2(a, b),
    "SINH": lambda a, b, c: math.sinh(a),
    "COSH": lambda a, b, c: math.cosh(a),
    "TANH": lambda a, b, c: math.tanh(a),
    "RADIANS": lambda a, b, c: math.radians(a),
    "DEGREES": lambda a, b, c: math.degrees(a),
    "CLAMP_MINMAX": lambda a, b, c: min(max(a, b), c),
    "CLAMP_RANGE": lambda a, b, c: min(max(a, min(b, c)), max(b, c)),
}


def _v(x) -> list[float]:
    return [float(i) for i in convert_value(x, DataType.ANY, DataType.VECTOR3)]


def _length(v) -> float:
    return math.sqrt(sum(c * c for c in v))


def _normalize(v) -> list[float]:
    length = _length(v)
    return [c / length for c in v] if length > 0 else [0.0, 0.0, 0.0]


def _cross(a, b) -> list[float]:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


VECTOR_MATH: dict[str, Callable[..., tuple[list[float] | None, float | None]]] = {
    "ADD": lambda a, b, c, s: ([x + y for x, y in zip(a, b)], None),
    "SUBTRACT": lambda a, b, c, s: ([x - y for x, y in zip(a, b)], None),
    "MULTIPLY": lambda a, b, c, s: ([x * y for x, y in zip(a, b)], None),
    "DIVIDE": lambda a, b, c, s: ([_safe_div(x, y) for x, y in zip(a, b)], None),
    "MULTIPLY_ADD": lambda a, b, c, s: ([x * y + z for x, y, z in zip(a, b, c)], None),
    "CROSS_PRODUCT": lambda a, b, c, s: (_cross(a, b), None),
    "DOT_PRODUCT": lambda a, b, c, s: (None, _dot(a, b)),
    "DISTANCE": lambda a, b, c, s: (None, _length([x - y for x, y in zip(a, b)])),
    "LENGTH": lambda a, b, c, s: (None, _length(a)),
    "SCALE": lambda a, b, c, s: ([x * s for x in a], None),
    "NORMALIZE": lambda a, b, c, s: (_normalize(a), None),
    "ABSOLUTE": lambda a, b, c, s: ([abs(x) for x in a], None),
    "MINIMUM": lambda a, b, c, s: ([min(x, y) for x, y in zip(a, b)], None),
    "MAXIMUM": lambda a, b, c, s: ([max(x, y) for x, y in zip(a, b)], None),
    "FLOOR": lambda a, b, c, s: ([float(math.floor(x)) for x in a], None),
    "CEIL": lambda a, b, c, s: ([float(math.ceil(x)) for x in a], None),
    "FRACTION": lambda a, b, c, s: ([x - math.floor(x) for x in a], None),
    "SINE": lambda a, b, c, s: ([math.sin(x) for x in a], None),
    "COSINE": lambda a, b, c, s: ([math.cos(x) for x in a], None),
    "TANGENT": lambda a, b, c, s: ([math.tan(x) for x in a], None),
}

COMPARE: dict[str, Callable[[float, float, float], bool]] = {
    "LESS_THAN": lambda a, b, e: a < b,
    "LESS_EQUAL": lambda a, b, e: a <= b,
    "GREATER_THAN": lambda a, b, e: a > b,
    "GREATER_EQUAL": lambda a, b, e: a >= b,
    "EQUAL": lambda a, b, e: abs(a - b) <= e,
    "NOT_EQUAL": lambda a, b, e: abs(a - b) > e,
}

BOOLEAN: dict[str, Callable[[bool, bool], bool]] = {
    "AND": lambda a, b: a and b,
    "OR": lambda a, b: a or b,
    "NOT": lambda a, b: not a,
    "NAND": lambda a, b: not (a and b),
    "NOR": lambda a, b: not (a or b),
    "XNOR": lambda a, b: a == b,
    "XOR": lambda a, b: a != b,
    "IMPLY": lambda a, b: (not a) or b,
    "NIMPLY": lambda a, b: a and not b,
}


class NotConstant(Exception):
    pass


def evaluate(graph: SemanticGraph, value: InputValue | None, *, params: dict[str, Any] | None = None, default: Any = None) -> Any:
    """Evaluate a single-value expression. Parameters use ``params`` or their current values."""
    if value is None:
        return default
    if isinstance(value, Const):
        return value.value
    if isinstance(value, Param):
        if params and value.name in params:
            return params[value.name]
        parameter = graph.parameter(value.name)
        if parameter is None:
            raise NotConstant(value.name)
        return parameter.current
    if isinstance(value, Link):
        op = graph.ops[value.op]
        result = evaluate_op(graph, op, params)
        if value.output not in result:
            raise NotConstant(f"{op.kind}.{value.output}")
        return result[value.output]
    raise NotConstant(repr(value))


def evaluate_op(graph: SemanticGraph, op, params: dict[str, Any] | None = None) -> dict[str, Any]:
    def arg(name: str, default: Any = 0.0) -> Any:
        return evaluate(graph, op.inputs.get(name), params=params, default=default)

    if op.kind == "MATH":
        fn = MATH.get(op.params.get("operation", "ADD"))
        if fn is None:
            raise NotConstant(op.params.get("operation"))
        result = fn(float(arg("a")), float(arg("b")), float(arg("c")))
        if op.params.get("clamp"):
            result = min(max(result, 0.0), 1.0)
        if op.outputs.get("value") is not None and op.outputs["value"].base == DataType.INT:
            result = int(result)
        return {"value": result}
    if op.kind == "VECTOR_MATH":
        fn = VECTOR_MATH.get(op.params.get("operation", "ADD"))
        if fn is None:
            raise NotConstant(op.params.get("operation"))
        vector, scalar = fn(_v(arg("a", [0.0] * 3)), _v(arg("b", [0.0] * 3)), _v(arg("c", [0.0] * 3)), float(arg("scale", 1.0)))
        return {"vector": vector if vector is not None else [0.0, 0.0, 0.0], "value": scalar if scalar is not None else 0.0}
    if op.kind == "COMBINE_VECTOR":
        return {"vector": [float(arg("x")), float(arg("y")), float(arg("z"))]}
    if op.kind == "SEPARATE_VECTOR":
        v = _v(arg("vector", [0.0] * 3))
        return {"x": v[0], "y": v[1], "z": v[2]}
    if op.kind == "COMPARE" and op.params.get("data_type", "FLOAT") in ("FLOAT", "INT"):
        fn = COMPARE.get(op.params.get("operation", "GREATER_THAN"))
        if fn is None:
            raise NotConstant(op.params.get("operation"))
        return {"result": fn(float(arg("a")), float(arg("b")), float(arg("epsilon", 0.001)))}
    if op.kind == "BOOLEAN_MATH":
        fn = BOOLEAN[op.params.get("operation", "AND")]
        return {"value": fn(bool(arg("a", False)), bool(arg("b", False)))}
    if op.kind == "MAP_RANGE" and op.params.get("data_type", "FLOAT") == "FLOAT" and op.params.get("interpolation", "LINEAR") == "LINEAR":
        value, fmin, fmax, tmin, tmax = (float(arg(k, d)) for k, d in (("value", 1.0), ("from_min", 0.0), ("from_max", 1.0), ("to_min", 0.0), ("to_max", 1.0)))
        t = _safe_div(value - fmin, fmax - fmin)
        if op.params.get("clamp", True):
            t = min(max(t, 0.0), 1.0)
        return {"result": tmin + t * (tmax - tmin)}
    raise NotConstant(op.kind)


FOLDABLE = {"MATH", "VECTOR_MATH", "COMBINE_VECTOR", "SEPARATE_VECTOR", "COMPARE", "BOOLEAN_MATH", "MAP_RANGE"}


def is_single_value(graph: SemanticGraph, value: InputValue | None) -> bool:
    """True when ``value`` is not a field (constants, parameters and math over them)."""
    if value is None or isinstance(value, (Const, Param)):
        return True
    if isinstance(value, Link):
        op = graph.ops.get(value.op)
        ref = op.outputs.get(value.output) if op else None
        return bool(ref is not None and not ref.field)
    if isinstance(value, tuple):
        return all(is_single_value(graph, item) for item in value)
    return False
