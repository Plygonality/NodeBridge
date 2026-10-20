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
from ...common.coordinates import UNREAL, convert_point, convert_scale, finite_components, has_non_finite
from ...common.names import snake_case
from ...common.units import UNREAL_UNITS, BLENDER_UNITS, ValueRole, convert_length, scene_scale_of
from ...compiler.limits import MAX_EXPRESSION_DEPTH, note_depth
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
    "ROUND": "math.copysign(math.floor(abs({a}) + 0.5), {a})",
    "SQRT": "math.sqrt(max({a}, 0.0))",
    "SINE": "math.sin({a})",
    "COSINE": "math.cos({a})",
    "RADIANS": "math.radians({a})",
    "DEGREES": "math.degrees({a})",
}


def control_name(key: str) -> str:
    return snake_case(key, "control").upper()


class PyExpr:
    def __init__(self, graph: SemanticGraph, diagnostics=None) -> None:
        self.graph = graph
        self.diagnostics = diagnostics
        self.uses_math = False
        self.scene_scale = scene_scale_of(graph.source)
        self._depth = 0

    def components(self, value: InputValue | None, count: int) -> list[str] | None:
        self._depth += 1
        try:
            if self._depth > MAX_EXPRESSION_DEPTH:
                note_depth(self.diagnostics, "compiler.depth", f"Expression nesting exceeded {MAX_EXPRESSION_DEPTH}; the current value was baked.")
                return None
            return self._components(value, count)
        finally:
            self._depth -= 1

    def _components(self, value: InputValue | None, count: int) -> list[str] | None:
        if value is None:
            return None
        if isinstance(value, Const):
            raw = value.value
            if isinstance(raw, dict) or raw is None:
                return None
            items = list(raw) if isinstance(raw, (list, tuple)) else [raw] * count
            if any(has_non_finite(item) for item in items):
                self._warn_non_finite()
            cleaned, changed = finite_components(items, count)
            if changed:
                self._warn_non_finite()
            if count == 1 and len(items) > 1:
                cleaned = [sum(cleaned[:3]) / len(cleaned[:3])]
            rendered = []
            originals = list(raw) if isinstance(raw, (list, tuple)) else [raw] * count
            for original, number in zip(originals, cleaned):
                if isinstance(original, bool):
                    rendered.append(literal(original))
                elif isinstance(original, int) and not changed:
                    rendered.append(literal(original))
                else:
                    rendered.append(literal(clean_number(number)))
            return rendered
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
            if op.kind == "VECTOR_MATH":
                # Walk the inputs so a long chain hits the depth limit. PCG has no
                # vector-math node, so the value still falls back to the caller's default.
                for key in ("a", "b", "c", "scale"):
                    if key in op.inputs:
                        self.components(op.inputs[key], 1 if key == "scale" else 3)
                return None
        return None

    def scalar(self, value: InputValue | None, default: Any, role: ValueRole = ValueRole.SCALAR) -> str:
        parts = self.components(value, 1)
        if parts is None:
            parts = [literal(default)]
        return to_unreal(parts, role, scene_scale=self.scene_scale)[0]

    def vector(self, value: InputValue | None, default: Any, role: ValueRole) -> list[str]:
        parts = self.components(value, 3)
        if parts is None:
            safe, changed = finite_components(default, 3)
            if changed:
                self._warn_non_finite()
            parts = [literal(clean_number(v)) for v in safe]
        return to_unreal(parts, role, scene_scale=self.scene_scale)

    def _warn_non_finite(self) -> None:
        if getattr(self, "_warned_non_finite", False):
            return
        self._warned_non_finite = True
        if self.diagnostics is not None:
            self.diagnostics.warning("unreal.non_finite", "Non-finite components were replaced with 0 before axis conversion.", target="unreal")


def to_unreal(components: list[str], role: ValueRole, *, scene_scale: float = 1.0) -> list[str]:
    """Blender-frame component expressions -> Unreal frame and units."""
    factor = convert_length(1.0, BLENDER_UNITS, UNREAL_UNITS, scene_scale=scene_scale)
    if len(components) == 1:
        if role in (ValueRole.LENGTH, ValueRole.POSITION):
            return [_scale(components[0], factor)]
        if role == ValueRole.ANGLE:
            return [f"math.degrees({components[0]})"]
        if role == ValueRole.AREA_DENSITY and scene_scale != 1.0:
            return [_scale(components[0], 1.0 / (scene_scale * scene_scale))]
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
