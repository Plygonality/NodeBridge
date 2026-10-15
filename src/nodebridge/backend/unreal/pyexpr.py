"""Single-value expressions -> Python expressions over script-level controls.

Exposed Blender parameters become named constants at the top of the
generated Unreal script (``DENSITY = 4.0``). Values derived from them
stay expressions (``FLOORS * FLOOR_HEIGHT``) so editing a control and
re-running the script reproduces the procedural link. Components are
produced in Blender's frame and units; callers convert with
:func:`to_unreal`.
"""

from __future__ import annotations

from typing import Any

from ...backend.codegen import clean_number, literal
from ...common.coordinates import UNREAL, convert_point, convert_scale
from ...common.names import snake_case
from ...common.units import UNREAL_UNITS, BLENDER_UNITS, ValueRole, convert_length
from ...ir.semantic import Const, InputValue, Link, Param, SemanticGraph
from ...ir.types import DataType

MATH = {
    "ADD": "({a} + {b})",
    "SUBTRACT": "({a} - {b})",
    "MULTIPLY": "({a} * {b})",
    "DIVIDE": "(({a} / {b}) if {b} else 0.0)",
    "MULTIPLY_ADD": "({a} * {b} + {c})",
    "POWER": "({a} ** {b})",
    "MINIMUM": "min({a}, {b})",
    "MAXIMUM": "max({a}, {b})",
    "ABSOLUTE": "abs({a})",
    "FLOOR": "math.floor({a})",
    "CEIL": "math.ceil({a})",
    "ROUND": "math.floor({a} + 0.5)",
    "SQRT": "math.sqrt(max({a}, 0.0))",
    "SINE": "math.sin({a})",
    "COSINE": "math.cos({a})",
    "RADIANS": "math.radians({a})",
    "DEGREES": "math.degrees({a})",
}


def control_name(key: str) -> str:
    return snake_case(key, "control").upper()


class PyExpr:
    def __init__(self, graph: SemanticGraph) -> None:
        self.graph = graph
        self.uses_math = False

    def components(self, value: InputValue | None, count: int) -> list[str] | None:
        if value is None:
            return None
        if isinstance(value, Const):
            raw = value.value
            if isinstance(raw, dict) or raw is None:
                return None
            items = list(raw) if isinstance(raw, (list, tuple)) else [raw] * count
            if count == 1 and len(items) > 1:
                items = [sum(float(v) for v in items[:3]) / len(items[:3])]
            return [literal(v) if isinstance(v, (bool, int)) else literal(clean_number(float(v))) for v in (items + [0.0] * count)[:count]]
        if isinstance(value, Param):
            parameter = self.graph.parameter(value.name)
            name = control_name(value.name)
            if parameter is not None and parameter.data_type in (DataType.VECTOR3, DataType.COLOR, DataType.ROTATION):
                parts = [f"{name}[{i}]" for i in range(3)]
                return parts if count == 3 else [f"(sum({name}[:3]) / 3.0)"]
            return [name] * count
        if isinstance(value, Link):
            op = self.graph.ops.get(value.op)
            if op is None or (op.outputs.get(value.output) is not None and op.outputs[value.output].field):
                return None
            if op.kind == "MATH":
                template = MATH.get(op.params.get("operation", "ADD"))
                if template is None:
                    return None
                args = {}
                for key in "abc":
                    parts = self.components(op.inputs.get(key, Const(0.0)), 1)
                    if parts is None:
                        return None
                    args[key] = parts[0]
                if "math." in template:
                    self.uses_math = True
                expr = template.format(**args)
                if op.params.get("clamp"):
                    expr = f"min(max({expr}, 0.0), 1.0)"
                return [expr] * count
            if op.kind == "COMBINE_VECTOR":
                parts = [self.components(op.inputs.get(k, Const(0.0)), 1) for k in "xyz"]
                if any(p is None for p in parts):
                    return None
                vector = [p[0] for p in parts]  # type: ignore[index]
                return vector if count == 3 else [f"(({vector[0]} + {vector[1]} + {vector[2]}) / 3.0)"]
            if op.kind == "SEPARATE_VECTOR":
                vector = self.components(op.inputs.get("vector"), 3)
                return [vector["xyz".index(value.output)]] * count if vector else None
        return None

    def scalar(self, value: InputValue | None, default: Any, role: ValueRole = ValueRole.SCALAR) -> str:
        parts = self.components(value, 1)
        if parts is None:
            parts = [literal(default)]
        return to_unreal(parts, role)[0]

    def vector(self, value: InputValue | None, default: Any, role: ValueRole) -> list[str]:
        parts = self.components(value, 3)
        if parts is None:
            parts = [literal(clean_number(float(v))) for v in default]
        return to_unreal(parts, role)


def to_unreal(components: list[str], role: ValueRole) -> list[str]:
    """Blender-frame component expressions -> Unreal frame and units."""
    factor = convert_length(1.0, BLENDER_UNITS, UNREAL_UNITS)
    if len(components) == 1:
        if role in (ValueRole.LENGTH, ValueRole.POSITION):
            return [_scale(components[0], factor)]
        if role == ValueRole.ANGLE:
            return [f"math.degrees({components[0]})"]
        return components
    x, y, z = components
    if role in (ValueRole.POSITION, ValueRole.DIRECTION):
        sign = convert_point((1.0, 1.0, 1.0), target=UNREAL)
        return [_scale(c, factor * s) for c, s in zip((x, y, z), sign)]
    if role == ValueRole.SCALE:
        order = convert_scale((0.0, 1.0, 2.0), target=UNREAL)
        return [components[int(i)] for i in order]
    return components


def _scale(expr: str, factor: float) -> str:
    if factor == 1.0:
        return expr
    try:
        return literal(clean_number(float(expr) * factor))
    except ValueError:
        return f"{expr} * {literal(clean_number(factor))}"
