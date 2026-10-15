"""Trace semantic values and fold constants.

A port is either a constant, an exposed group parameter, or an expression
tree. Backends turn expression trees into VEX or material math. They do not
reimplement Blender's node evaluator.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from nodebridge.ir.semantic import Operation, OperationKind, SemanticGraph


@dataclass(frozen=True)
class Expr:
    """A small expression tree in semantic operations, not source nodes."""

    op: str
    args: tuple[Any, ...] = ()
    dtype: str = "float"
    source_id: str = ""


def trace_input(graph: SemanticGraph, operation: Operation, port: str) -> Expr:
    """Expression feeding ``port``, or the stored parameter when nothing is linked."""

    edge = graph.edge_to(operation.id, port)
    if edge is None:
        if port in operation.parameters:
            return Expr("const", (operation.parameters[port],), _dtype(operation, port), operation.id)
        return Expr("const", (None,), "any", operation.id)
    return trace_output(graph, edge.from_operation, edge.from_port)


def trace_output(graph: SemanticGraph, operation_id: str, port: str) -> Expr:
    operation = graph.get(operation_id)
    kind = operation.kind
    if kind is OperationKind.GROUP_INPUT:
        defaults = operation.parameters.get("defaults", {})
        labels = operation.parameters.get("labels", {})
        return Expr("exposed", (port, defaults.get(port), labels.get(port, port)), _dtype(operation, port), operation.id)
    if kind is OperationKind.ATTRIBUTE_READ:
        return Expr("attr", (operation.parameters.get("attribute", port),), operation.parameters.get("data_type", "float"), operation.id)
    if kind is OperationKind.MATH:
        return Expr(
            str(operation.parameters.get("operation", "add")).lower(),
            (
                trace_input(graph, operation, "a"),
                trace_input(graph, operation, "b"),
                trace_input(graph, operation, "c"),
            ),
            "float",
            operation.id,
        )
    if kind is OperationKind.VECTOR_MATH:
        return Expr(
            "vector_" + str(operation.parameters.get("operation", "add")).lower(),
            (
                trace_input(graph, operation, "a"),
                trace_input(graph, operation, "b"),
                trace_input(graph, operation, "c"),
            ),
            "vector3",
            operation.id,
        )
    if kind is OperationKind.MAP_RANGE:
        return Expr(
            "map_range",
            tuple(trace_input(graph, operation, name) for name in ("value", "from_min", "from_max", "to_min", "to_max")),
            "float",
            operation.id,
        )
    if kind is OperationKind.COMPARE:
        return Expr(
            "compare",
            (
                str(operation.parameters.get("operation", "less_than")).lower(),
                trace_input(graph, operation, "a"),
                trace_input(graph, operation, "b"),
            ),
            "bool",
            operation.id,
        )
    if kind is OperationKind.BOOLEAN_MATH:
        return Expr(
            "bool_" + str(operation.parameters.get("operation", "and")).lower(),
            (trace_input(graph, operation, "a"), trace_input(graph, operation, "b")),
            "bool",
            operation.id,
        )
    if kind is OperationKind.NOISE:
        return Expr(
            str(operation.parameters.get("noise_type", "noise")).lower(),
            (
                trace_input(graph, operation, "vector"),
                trace_input(graph, operation, "scale"),
                trace_input(graph, operation, "detail"),
                trace_input(graph, operation, "roughness"),
                trace_input(graph, operation, "distortion"),
            ),
            "float" if port in {"fac", "value", "factor"} else "color",
            operation.id,
        )
    if kind is OperationKind.RANDOM:
        return Expr(
            "random",
            (
                str(operation.parameters.get("data_type", "float")).lower(),
                trace_input(graph, operation, "minimum"),
                trace_input(graph, operation, "maximum"),
                trace_input(graph, operation, "seed"),
                trace_input(graph, operation, "id"),
            ),
            str(operation.parameters.get("data_type", "float")).lower(),
            operation.id,
        )
    if kind is OperationKind.SWITCH:
        return Expr(
            "switch",
            (
                trace_input(graph, operation, "switch"),
                trace_input(graph, operation, "false"),
                trace_input(graph, operation, "true"),
            ),
            "any",
            operation.id,
        )
    if kind is OperationKind.SPATIAL_NOISE_MASK:
        return Expr("spatial_noise_mask", (operation.parameters.get("scale", 5.0), operation.parameters.get("threshold", 0.5)), "bool", operation.id)
    if kind is OperationKind.FIELD or kind is OperationKind.COLOR_OPERATION and operation.parameters.get("mode") == "constant":
        return Expr("const", (operation.parameters.get("value"),), operation.parameters.get("data_type", "float"), operation.id)
    return Expr("opaque", (kind.value, port), "any", operation.id)


def as_constant(expr: Expr) -> Any:
    """Return a Python value when ``expr`` does not depend on attributes or noise."""

    if expr.op == "const":
        return expr.args[0]
    if expr.op in {"exposed", "attr", "noise", "voronoi", "random", "spatial_noise_mask", "opaque"}:
        return None
    values = [as_constant(arg) if isinstance(arg, Expr) else arg for arg in expr.args]
    if any(isinstance(arg, Expr) and as_constant(arg) is None and arg.op != "const" for arg in expr.args):
        if any(as_constant(arg) is None for arg in expr.args if isinstance(arg, Expr)):
            return None
    if any(value is None for value in values):
        return None
    return _eval(expr.op, values)


def is_exposed(expr: Expr) -> bool:
    return expr.op == "exposed" or any(isinstance(arg, Expr) and is_exposed(arg) for arg in expr.args)


def exposed_name(expr: Expr) -> str | None:
    if expr.op == "exposed":
        return str(expr.args[0])
    for arg in expr.args:
        if isinstance(arg, Expr):
            name = exposed_name(arg)
            if name:
                return name
    return None


def _dtype(operation: Operation, port: str) -> str:
    socket = operation.inputs.get(port) or operation.outputs.get(port)
    if socket is None:
        return "any"
    return socket.data_type.value


def _eval(op: str, values: list[Any]) -> Any:
    if op in {"add", "subtract", "multiply", "divide", "power", "minimum", "maximum", "modulo"}:
        a, b = _num(values[0]), _num(values[1])
        if op == "add":
            return a + b
        if op == "subtract":
            return a - b
        if op == "multiply":
            return a * b
        if op == "divide":
            return a / b if b != 0 else 0.0
        if op == "power":
            return a ** b
        if op == "minimum":
            return min(a, b)
        if op == "maximum":
            return max(a, b)
        return math.fmod(a, b) if b != 0 else 0.0
    if op in {"absolute", "sqrt", "floor", "ceil", "fraction", "sine", "cosine", "tangent", "radians", "degrees"}:
        a = _num(values[0])
        table = {
            "absolute": abs(a),
            "sqrt": math.sqrt(a) if a >= 0 else 0.0,
            "floor": math.floor(a),
            "ceil": math.ceil(a),
            "fraction": a - math.floor(a),
            "sine": math.sin(a),
            "cosine": math.cos(a),
            "tangent": math.tan(a),
            "radians": math.radians(a),
            "degrees": math.degrees(a),
        }
        return table[op]
    if op == "map_range":
        value, from_min, from_max, to_min, to_max = map(_num, values[:5])
        span = from_max - from_min
        factor = 0.0 if span == 0 else (value - from_min) / span
        return to_min + factor * (to_max - to_min)
    if op == "compare":
        comparison, a, b = values[0], values[1], values[2]
        return _compare(str(comparison), a, b)
    if op == "switch":
        return values[2] if values[0] else values[1]
    if op.startswith("bool_"):
        a = bool(values[0])
        b = bool(values[1]) if len(values) > 1 else False
        name = op.removeprefix("bool_")
        if name == "not":
            return not a
        if name == "or":
            return a or b
        if name == "xor":
            return a ^ b
        return a and b
    if op.startswith("vector_"):
        return _vector_eval(op.removeprefix("vector_"), values)
    return None


def _compare(op: str, a: Any, b: Any) -> bool:
    if op in {"less_than", "less"}:
        return _num(a) < _num(b)
    if op in {"greater_than", "greater"}:
        return _num(a) > _num(b)
    if op in {"equal", "equals"}:
        return a == b
    if op in {"not_equal"}:
        return a != b
    if op in {"less_equal"}:
        return _num(a) <= _num(b)
    if op in {"greater_equal"}:
        return _num(a) >= _num(b)
    return _num(a) < _num(b)


def _vector_eval(op: str, values: list[Any]) -> Any:
    a = _vec(values[0])
    b = _vec(values[1]) if len(values) > 1 else (0.0, 0.0, 0.0)
    if op == "add":
        return tuple(a[i] + b[i] for i in range(3))
    if op == "subtract":
        return tuple(a[i] - b[i] for i in range(3))
    if op == "multiply":
        return tuple(a[i] * b[i] for i in range(3))
    if op == "scale":
        scale = _num(values[1] if len(values) > 1 else 1)
        return tuple(component * scale for component in a)
    if op == "normalize":
        length = math.sqrt(sum(component * component for component in a)) or 1.0
        return tuple(component / length for component in a)
    if op == "dot":
        return sum(a[i] * b[i] for i in range(3))
    if op == "cross":
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )
    if op == "length":
        return math.sqrt(sum(component * component for component in a))
    if op == "distance":
        return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))
    return None


def _num(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (list, tuple)) and value:
        return _num(value[0])
    return 0.0


def _vec(value: Any) -> tuple[float, float, float]:
    if isinstance(value, (list, tuple)):
        items = list(value) + [0.0, 0.0, 0.0]
        return (float(items[0]), float(items[1]), float(items[2]))
    number = _num(value)
    return (number, number, number)
