"""Single-value expressions -> HScript parameter expressions.

When a SOP parameter is driven by an exposed control (Blender group
input), the generated node keeps that link as a channel reference such
as ``ch("../width") * 2`` instead of baking the value. Expressions are
built per component in Blender's frame; the caller converts the
components to Houdini's frame according to the value's role.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...backend.codegen import clean_number
from ...common.names import houdini_parm_name
from ...common.units import ValueRole
from ...ir.semantic import Const, InputValue, Link, Param
from ...ir.types import DataType

if TYPE_CHECKING:
    from .sop import SopBuilder

MATH = {
    "ADD": "({a} + {b})",
    "SUBTRACT": "({a} - {b})",
    "MULTIPLY": "({a} * {b})",
    "DIVIDE": "({a} / {b})",
    "MULTIPLY_ADD": "({a} * {b} + {c})",
    "POWER": "pow({a}, {b})",
    "MINIMUM": "min({a}, {b})",
    "MAXIMUM": "max({a}, {b})",
    "ABSOLUTE": "abs({a})",
    "FLOOR": "floor({a})",
    "CEIL": "ceil({a})",
    "ROUND": "floor({a} + 0.5)",
    "SQRT": "sqrt({a})",
    "RADIANS": "rad({a})",
    "DEGREES": "deg({a})",
}
VECTOR = {"ADD": "({a} + {b})", "SUBTRACT": "({a} - {b})", "MULTIPLY": "({a} * {b})", "SCALE": "({a} * {s})"}


def number(value) -> str:
    text = repr(clean_number(float(value)))
    return text[:-2] if text.endswith(".0") else text


class HScriptCompiler:
    def __init__(self, builder: "SopBuilder") -> None:
        self.b = builder

    def components(self, value: InputValue | None, count: int) -> list[str] | None:
        """Blender-frame expression per component, or ``None`` if not expressible."""
        if value is None:
            return None
        if isinstance(value, Const):
            raw = value.value
            if isinstance(raw, bool):
                raw = int(raw)
            items = list(raw) if isinstance(raw, (list, tuple)) else [raw] * count
            if count == 1 and len(items) > 1:
                items = [sum(float(v) for v in items[:3]) / len(items[:3])]
            try:
                return [number(v) for v in (items + [0.0] * count)[:count]]
            except (TypeError, ValueError):
                return None
        if isinstance(value, Param):
            return self._param(value.name, count)
        if isinstance(value, Link):
            op = self.b.graph.ops.get(value.op)
            if op is None:
                return None
            return self._op(op, value.output, count)
        return None

    def _param(self, key: str, count: int) -> list[str] | None:
        parameter = self.b.parameter(key)
        if parameter is None:
            return None
        path = self.b.network.param_path(key)
        if parameter.data_type in (DataType.VECTOR3, DataType.COLOR, DataType.ROTATION):
            suffixes = "rgb" if parameter.data_type == DataType.COLOR else "xyz"
            h = [f'ch("{path}{s}")' for s in suffixes]
            if parameter.role in (ValueRole.POSITION, ValueRole.DIRECTION, ValueRole.NORMAL):
                b = [h[0], f"-{h[2]}", h[1]]
            elif parameter.role == ValueRole.SCALE:
                b = [h[0], h[2], h[1]]
            elif parameter.role == ValueRole.EULER:
                b = [f"rad({h[0]})", f"rad(-{h[2]})", f"rad({h[1]})"]
            else:
                b = h
            if count == 1:
                return [f"(({b[0]} + {b[1]} + {b[2]}) / 3)"]
            return b
        expr = f'ch("{path}")'
        if parameter.role == ValueRole.ANGLE:
            expr = f"rad({expr})"
        return [expr] * count if count > 1 else [expr]

    def _op(self, op, output: str, count: int) -> list[str] | None:
        if op.outputs.get(output) is not None and op.outputs[output].field:
            return None
        if op.kind == "MATH":
            template = MATH.get(op.params.get("operation", "ADD"))
            if template is None:
                return None
            args = {}
            for key in "abc":
                comps = self.components(op.inputs.get(key, Const(0.0)), 1)
                if comps is None:
                    return None
                args[key] = comps[0]
            expr = template.format(**args)
            if op.params.get("clamp"):
                expr = f"clamp({expr}, 0, 1)"
            return [expr] * count
        if op.kind == "COMBINE_VECTOR":
            parts = [self.components(op.inputs.get(k, Const(0.0)), 1) for k in "xyz"]
            if any(p is None for p in parts):
                return None
            vector = [p[0] for p in parts]  # type: ignore[index]
            return vector if count == 3 else [f"(({vector[0]} + {vector[1]} + {vector[2]}) / 3)"]
        if op.kind == "SEPARATE_VECTOR":
            vector = self.components(op.inputs.get("vector"), 3)
            if vector is None:
                return None
            return [vector["xyz".index(output)]] * count
        if op.kind == "VECTOR_MATH" and output == "vector":
            template = VECTOR.get(op.params.get("operation", "ADD"))
            if template is None:
                return None
            a = self.components(op.inputs.get("a", Const([0.0] * 3)), 3)
            b = self.components(op.inputs.get("b", Const([0.0] * 3)), 3)
            s = self.components(op.inputs.get("scale", Const(1.0)), 1)
            if a is None or b is None or s is None:
                return None
            vector = [template.format(a=a[i], b=b[i], s=s[0]) for i in range(3)]
            return vector if count == 3 else [f"(({vector[0]} + {vector[1]} + {vector[2]}) / 3)"]
        if op.kind == "MAP_RANGE" and op.params.get("interpolation") == "LINEAR" and op.params.get("data_type") == "FLOAT":
            parts = [self.components(op.inputs.get(k, Const(d)), 1) for k, d in (("value", 1.0), ("from_min", 0.0), ("from_max", 1.0), ("to_min", 0.0), ("to_max", 1.0))]
            if any(p is None for p in parts):
                return None
            fn = "fit" if op.params.get("clamp", True) else "efit"
            return [f"{fn}({', '.join(p[0] for p in parts)})"] * count  # type: ignore[index]
        return None


def to_houdini_components(components: list[str], role: ValueRole) -> list[str]:
    """Blender-frame component expressions -> Houdini-frame expressions."""
    if len(components) != 3:
        if role == ValueRole.ANGLE:
            return [f"deg({components[0]})"]
        return components
    x, y, z = components
    if role in (ValueRole.POSITION, ValueRole.DIRECTION, ValueRole.NORMAL):
        return [x, z, _negate(y)]
    if role == ValueRole.SCALE:
        return [x, z, y]
    if role == ValueRole.EULER:
        return [f"deg({x})", f"deg({z})", f"deg({_negate(y)})"]
    return components


def _negate(expr: str) -> str:
    if expr.startswith("-") and expr[1:].replace(".", "", 1).isdigit():
        return expr[1:]
    if expr.replace(".", "", 1).isdigit():
        return "0" if float(expr) == 0 else f"-{expr}"
    return f"-({expr})"


def spare_parm_name(key: str) -> str:
    return houdini_parm_name(key)
