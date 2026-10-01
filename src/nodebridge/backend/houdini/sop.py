"""Semantic geometry operations -> Houdini SOP networks.

Native SOPs are used whenever a defensible mapping exists. Field inputs
(per-element expressions) are compiled to VEX in an Attribute Wrangle
placed immediately before the consuming SOP, writing standard Houdini
attributes (``scale``, ``orient``, groups) that the SOP reads.

Parameter names target Houdini 20.x. Generated code sets them through
``nb_set`` / ``nb_set_menu``, which report (rather than crash on)
parameters that a different Houdini version names differently.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Callable

from ...backend.codegen import PyWriter, clean_number, literal
from ...common.coordinates import HOUDINI, convert_point, convert_scale
from ...common.names import NameAllocator, houdini_label_name, houdini_node_name, python_identifier, snake_case
from ...common.units import ValueRole
from ...ir.operations import Category, get_operation
from ...ir.semantic import Const, ExposedParameter, InputValue, Link, Param, SemanticGraph, SemanticOp
from ...ir.types import GEOMETRY_TYPES, DataType
from ...translation.confidence import Classification, Confidence as C
from ...translation.registry import translator
from .hscript import HScriptCompiler, spare_parm_name, to_houdini_components
from .vex import DOMAIN_CLASS, VexCompiler, VexError, library_constant, vex_switch

T, CTX = "houdini", "sop"
F, I, B, V = DataType.FLOAT, DataType.INT, DataType.BOOL, DataType.VECTOR3
ATTRIBUTE_NAMES = {"position": "P", "normal": "N", "id": "id", "material_index": "shop_materialpath", "radius": "pscale", "UVMap": "uv"}


@dataclass
class Stream:
    var: str
    index: int = 0


class Network:
    """One Houdini network level: the geo container or a subnet."""

    def __init__(self, var: str, label: str, parameters: list[ExposedParameter]) -> None:
        self.var = var
        self.label = label
        self.parameters = parameters
        self.names = NameAllocator()

    def param_path(self, key: str) -> str:
        return f"../{spare_parm_name(key)}"


class SopBuilder:
    def __init__(self, backend, result, graph: SemanticGraph, writer: PyWriter, network: Network, variables: NameAllocator, *, in_subnet: bool = False, libraries: set | None = None) -> None:
        self.backend = backend
        self.libraries: set[str] = libraries if libraries is not None else set()
        self.result = result
        self.graph = graph
        self.w = writer
        self.network = network
        self.vars = variables
        self.in_subnet = in_subnet
        self.streams: dict[tuple[str, str], Stream] = {}
        self.current_stream: Stream | None = None
        self.hscript = HScriptCompiler(self)
        self.temp_point_attributes: list[str] = []
        self.field_attributes: dict[tuple[str, str], tuple[str, str, DataType]] = {}
        self.outputs: list[str] = []
        self.indirect_inputs: str | None = None
        self.materials: dict[str, str] = {}

    @property
    def options(self):
        return self.result.options

    # -- parameters ----------------------------------------------------
    def parameter(self, key: str) -> ExposedParameter | None:
        return next((p for p in self.network.parameters if p.key == key), None)

    def param_type(self, key: str) -> DataType:
        parameter = self.parameter(key)
        return parameter.data_type if parameter else F

    def attribute_name(self, name: str) -> str:
        return ATTRIBUTE_NAMES.get(name, name)

    # -- driving -------------------------------------------------------
    def build(self) -> None:
        for op in self.graph.topological_order():
            if self.is_geometry_op(op):
                self.translate(op)

    def is_geometry_op(self, op: SemanticOp) -> bool:
        if op.kind in ("SUBGRAPH", "GEOMETRY_OUTPUT"):
            return True
        spec = get_operation(op.kind)
        if spec is not None and spec.category == Category.GEOMETRY:
            return True
        return any(ref.base in GEOMETRY_TYPES for ref in op.outputs.values())

    def classification(self, op: SemanticOp) -> Classification:
        return self.result.classification(self.graph, op)

    def translate(self, op: SemanticOp) -> None:
        classification = self.classification(op)
        self.w.blank()
        if self.options.include_comments:
            source = ", ".join(op.source.types) or "generated"
            self.w.comment(f"{op.display_name}: {op.kind} [{classification.confidence.value}]  (Blender: {source})")
        item = self.backend.translator(op, CTX)
        if self.result.is_blocked(self.graph, op):
            self.placeholder(op, f"Skipped by strictness ({self.options.strictness.value}): {classification.confidence.value}. {classification.explanation}")
            return
        if item is None or classification.confidence == C.UNSUPPORTED:
            self.placeholder(op, classification.explanation)
            return
        try:
            item.fn(self, op)
        except VexError as exc:
            self.result.diagnostics.warning("houdini.vex", f"{op.display_name}: {exc}; a placeholder was generated.", op=op.id, target=T)
            self.placeholder(op, f"Could not compile field input: {exc}")

    # -- emission helpers ------------------------------------------------
    def node_name(self, op: SemanticOp, suffix: str = "") -> str:
        base = op.display_name if self.options.preserve_names else op.kind.lower()
        return self.network.names.allocate(houdini_node_name(base + suffix))

    def node(self, op: SemanticOp | None, node_type: str, suffix: str = "", *, name: str | None = None, meta: bool = True) -> str:
        hname = self.network.names.allocate(houdini_label_name(name)) if name else self.node_name(op, suffix)  # type: ignore[arg-type]
        var = self.vars.allocate(python_identifier(hname))
        self.w.line(f'{var} = nb_create({self.network.var}, "{node_type}", "{hname}")')
        if op is not None and meta and self.options.embed_metadata:
            c = self.classification(op)
            comment = f"NodeBridge: {op.display_name} ({c.confidence.value})"
            data = json.dumps({"op": op.kind, "source": op.source.types, "confidence": c.confidence.value})
            self.w.line(f"nb_meta({var}, {comment!r}, {data!r})")
        return var

    def connect(self, var: str, index: int, stream: Stream | None) -> None:
        if stream is not None:
            suffix = f", {stream.index}" if stream.index else ""
            self.w.line(f"{var}.setInput({index}, {stream.var}{suffix})")

    def set(self, var: str, parm: str, value: Any) -> None:
        self.w.line(f'nb_set({var}, "{parm}", {literal(value)})')

    def menu(self, var: str, parm: str, token: str) -> None:
        self.w.line(f'nb_set_menu({var}, "{parm}", "{token}")')

    def note(self, op: SemanticOp | None, var: str | None, text: str) -> None:
        if self.options.include_comments:
            self.w.line(f"nb_note({self.network.var}, {text!r}, {var or 'None'})")

    def stream_for(self, value: InputValue | None) -> Stream | None:
        if isinstance(value, tuple):
            value = value[0] if value else None
        if isinstance(value, Link):
            return self.streams.get((value.op, value.output))
        return None

    def set_output(self, op: SemanticOp, output: str, var: str, index: int = 0) -> None:
        self.streams[(op.id, output)] = Stream(var, index)

    def evaluate(self, value: InputValue | None, default: Any) -> Any:
        from ...compiler.evaluate import NotConstant, evaluate

        try:
            result = evaluate(self.graph, value, default=default)
        except (NotConstant, KeyError):
            return default
        return default if result is None else result

    def set_value(self, var: str, parm: str, value: InputValue | None, role: ValueRole, *, count: int = 1, default: Any = None, integer: bool = False) -> None:
        """Set a SOP parameter from a constant, a parameter or an expression of parameters."""
        if value is None:
            return
        if isinstance(value, Const) or self.is_constant(value):
            raw = self.evaluate(value, default)
            if raw is None:
                return
            converted = self.convert_constant(raw, role, count)
            if integer:
                converted = int(round(converted)) if not isinstance(converted, tuple) else tuple(int(round(c)) for c in converted)
            self.set(var, parm, converted)
            return
        components = self.hscript.components(value, count)
        if components is None:
            raw = self.evaluate(value, default)
            self.result.diagnostics.warning("houdini.baked", f"A parameter expression feeding {parm!r} could not be expressed in HScript; its current value was baked.", target=T)
            self.set(var, parm, self.convert_constant(raw, role, count))
            return
        for index, expr in enumerate(to_houdini_components(components, role)):
            if integer:
                expr = f"int({expr})"
            target_index = "" if count == 1 else f", index={index}"
            self.w.line(f'nb_expr({var}, "{parm}", {expr!r}{target_index})')

    def is_constant(self, value: InputValue | None) -> bool:
        return isinstance(value, Const) or (isinstance(value, Link) and not any(isinstance(v, Param) for v in self._leaves(value)))

    def _leaves(self, value: InputValue):
        if isinstance(value, Link):
            op = self.graph.ops.get(value.op)
            if op is None:
                return
            for item in op.inputs.values():
                yield from self._leaves(item)
        elif isinstance(value, tuple):
            for item in value:
                yield from self._leaves(item)
        else:
            yield value

    def convert_constant(self, raw: Any, role: ValueRole, count: int) -> Any:
        if count == 3:
            items = list(raw) if isinstance(raw, (list, tuple)) else [raw] * 3
            items = [float(v) for v in (items + [0.0, 0.0, 0.0])[:3]]
            if role in (ValueRole.POSITION, ValueRole.DIRECTION, ValueRole.NORMAL):
                items = list(convert_point(items, target=HOUDINI))
            elif role == ValueRole.SCALE:
                items = list(convert_scale(items, target=HOUDINI))
            elif role == ValueRole.EULER:
                items = [math.degrees(items[0]), math.degrees(items[2]), -math.degrees(items[1])]
            return tuple(clean_number(v) for v in items)
        if isinstance(raw, (list, tuple)):
            raw = sum(float(v) for v in raw[:3]) / max(len(raw[:3]), 1)
        if isinstance(raw, bool):
            return int(raw)
        if role == ValueRole.ANGLE:
            return clean_number(math.degrees(float(raw)))
        return clean_number(float(raw)) if isinstance(raw, float) else raw

    def is_true(self, value: InputValue | None) -> bool:
        return value is None or (isinstance(value, Const) and bool(value.value) is True)

    def is_false(self, value: InputValue | None) -> bool:
        return isinstance(value, Const) and not value.value

    # -- wrangles ----------------------------------------------------------
    def wrangle(self, op: SemanticOp, domain: str, stream: Stream | None, body: Callable[[VexCompiler], list[str]], suffix: str = "_vex") -> Stream:
        vc = VexCompiler(self, domain)
        self.current_stream = stream
        statements = body(vc)
        var = self.node(op, "attribwrangle", suffix, meta=not suffix)
        self.connect(var, 0, stream)
        for index, (key, side) in enumerate(vc.side_inputs, start=1):
            if key == "point_normals":
                normals = self.node(op, "normal", "_point_normals", meta=False)
                self.connect(normals, 0, stream)
                self.set(normals, "type", 0)
                self.connect(var, index, Stream(normals))
            else:
                self.connect(var, index, side)
        self.set(var, "class", DOMAIN_CLASS[domain])
        libraries, text = vc.parts(statements)
        self.snippet(var, text, libraries)
        for text in vc.notes:
            self.note(op, var, text)
        return Stream(var)

    def snippet(self, var: str, text: str, libraries=()) -> None:
        """Write a VEX snippet as a readable multi-line string plus shared libraries."""
        self.libraries.update(libraries)
        prefix = " + ".join(["NB_VEX_HEADER"] + [library_constant(name) for name in libraries])
        self.w.multiline(f"{var}_vex", prefix, text)
        self.w.line(f'nb_set({var}, "snippet", {var}_vex)')

    def selection_group(self, op: SemanticOp, stream: Stream | None, domain: str, name: str) -> tuple[Stream | None, str]:
        """Evaluate a selection field into a group; returns (stream, group name or '')."""
        selection = op.inputs.get("selection")
        if self.is_true(selection):
            return stream, ""
        group = f"nb_{name}_{snake_case(op.id)}"
        setter = "setprimgroup" if domain == "prim" else "setpointgroup"

        def body(vc: VexCompiler) -> list[str]:
            return [f'{setter}(0, "{group}", {vc.element}, {vc.value(selection, B, default=1)}, "set");']

        return self.wrangle(op, domain, stream, body, "_selection"), group

    def field_reader(self, op: SemanticOp):
        if any((op.id, out) in self.field_attributes for out in op.outputs):
            return _read_field_attributes
        return None

    def placeholder(self, op: SemanticOp, reason: str) -> None:
        geometry_inputs = [v for k, v in op.inputs.items() if self.stream_for(v) is not None]
        var = self.node(op, "null", name=f"UNSUPPORTED_{houdini_node_name(op.display_name)}")
        if geometry_inputs:
            self.connect(var, 0, self.stream_for(geometry_inputs[0]))
        self.note(op, var, f"NodeBridge could not translate '{op.display_name}' ({', '.join(op.source.types) or op.kind}).\n{reason}\nThe input passes through unchanged.")
        for name, ref in op.outputs.items():
            if ref.base in GEOMETRY_TYPES:
                self.set_output(op, name, var)


def _read_field_attributes(vc: VexCompiler, op: SemanticOp) -> dict[str, tuple[str, DataType]]:
    result = {}
    for name in op.outputs:
        info = vc.b.field_attributes.get((op.id, name))
        if info is None:
            continue
        kind, attr, data_type = info
        if kind == "point_normal":
            reader = f'point(0, "{attr}", @ptnum)' if vc.domain == "point" else f'prim(0, "{attr}", @primnum)'
            if name == "rotation":
                vc.need("rotation")
                result[name] = (f"nb_euler_from_normal(nb_b({reader}))", DataType.ROTATION)
            else:
                result[name] = (f"nb_b({reader})", V)
        elif kind == "prim_group":
            if vc.domain == "prim":
                result[name] = (f'inprimgroup(0, "{attr}", @primnum)', B)
            else:
                result[name] = (f'(len(expandprimgroup(0, "{attr}")) > 0 && inprimgroup(0, "{attr}", pointprims(0, @ptnum)[0]))', B)
    return result


# =============================================================================
# Translators
# =============================================================================
def _sop(kind, confidence, implementation, explanation="", limitations=(), classify=None, fallback=""):
    return translator(kind, target=T, context=CTX, confidence=confidence, implementation=implementation, explanation=explanation, limitations=limitations, classify=classify, fallback=fallback)


@_sop(
    "GEOMETRY_INPUT",
    C.EQUIVALENT,
    "object_merge + placeholder grid + switch",
    "The modifier's input geometry becomes an Object Merge you point at your own object. Until then a placeholder sized like the Blender object is used.",
    ("Set 'Use Source Object' on the geo node and the Object Merge path to use real geometry.",),
)
def _geometry_input(b: SopBuilder, op: SemanticOp) -> None:
    if b.in_subnet:
        index = op.annotations.get("subnet_input", 0)
        b.set_output(op, "geometry", f"{b.indirect_inputs}[{index}]")
        return
    source = b.node(op, "object_merge", name=f"IN_{op.display_name}_object")
    b.set(source, "objpath1", "")
    b.set(source, "xformtype", 1)
    size = b.result.document.source.get("object_dimensions") or [10.0, 10.0, 0.0]
    placeholder = b.node(op, "grid", name=f"IN_{op.display_name}_placeholder", meta=False)
    b.set(placeholder, "size", (clean_number(max(size[0], 0.01)), clean_number(max(size[1], 0.01))))
    b.menu(placeholder, "orient", "xy")
    b.set(placeholder, "r", (-90.0, 0.0, 0.0))
    b.set(placeholder, "rows", 2)
    b.set(placeholder, "cols", 2)
    switch = b.node(op, "switch", name=f"IN_{op.display_name}", meta=False)
    b.connect(switch, 0, Stream(placeholder))
    b.connect(switch, 1, Stream(source))
    b.w.line(f'nb_expr({switch}, "input", \'ch("../use_source_object")\')')
    b.note(op, source, "Point 'Object 1' at the object that carried the Blender modifier, then enable 'Use Source Object' on the geo node.")
    b.set_output(op, "geometry", switch)


@_sop("GEOMETRY_OUTPUT", C.EXACT, "null OUT (display/render)", "Final output with display and render flags.")
def _geometry_output(b: SopBuilder, op: SemanticOp) -> None:
    stream = b.stream_for(op.inputs.get("geometry"))
    if b.temp_point_attributes:
        cleanup = b.node(op, "attribdelete", name="cleanup_nodebridge_attributes", meta=False)
        b.connect(cleanup, 0, stream)
        b.set(cleanup, "ptdel", " ".join(sorted(set(b.temp_point_attributes))))
        stream = Stream(cleanup)
    if b.in_subnet:
        index = op.annotations.get("subnet_output", 0)
        var = b.node(op, "output", name=f"OUT_{op.display_name}", meta=False)
        b.set(var, "outputidx", index)
        b.connect(var, 0, stream)
        if index == 0:
            b.w.line(f"{var}.setDisplayFlag(True)")
        b.outputs.append(var)
        return
    var = b.node(op, "null", name="OUT", meta=False)
    b.connect(var, 0, stream)
    b.w.line(f"{var}.setDisplayFlag(True)")
    b.w.line(f"{var}.setRenderFlag(True)")
    b.outputs.append(var)


PRIMITIVE_SOPS = {
    "cube": "box SOP",
    "grid": "grid SOP",
    "uv_sphere": "sphere SOP (polygon mesh)",
    "ico_sphere": "sphere SOP (polygon)",
    "cylinder": "tube SOP",
    "cone": "tube SOP",
    "line": "line SOP",
    "circle": "circle SOP",
}


def _primitive_classify(op, graph, base):
    shape = op.params.get("shape")
    implementation = PRIMITIVE_SOPS.get(shape, base.implementation)
    if shape in ("cube", "grid", "line"):
        return Classification(C.EXACT, f"Native {shape} primitive with converted axes.", implementation)
    if shape == "circle" and op.params.get("fill_type", "NONE") == "NONE":
        return Classification(C.APPROXIMATE, "Blender's unfilled circle is an edge loop; Houdini's Circle SOP makes a closed polygon.", implementation)
    return Classification(C.EQUIVALENT, f"Native {shape.replace('_', ' ')} primitive; vertex layout and UVs differ.", implementation, ["Topology (vertex order, pole layout, UVs) differs from Blender."])


@_sop("PRIMITIVE", C.EXACT, "box / grid / sphere / tube / line / circle SOP", classify=_primitive_classify)
def _primitive(b: SopBuilder, op: SemanticOp) -> None:
    shape = op.params.get("shape")
    get = op.inputs.get
    if shape == "cube":
        var = b.node(op, "box")
        b.set_value(var, "size", get("size"), ValueRole.SCALE, count=3, default=[1.0, 1.0, 1.0])
        verts = [b.evaluate(get(k), 2) for k in ("vertices_x", "vertices_y", "vertices_z")]
        if any(int(v) != 2 for v in verts):
            b.set(var, "dodivs", 1)
            b.set(var, "divs", (int(verts[0]), int(verts[2]), int(verts[1])))
    elif shape == "grid":
        var = b.node(op, "grid")
        b.menu(var, "orient", "xy")
        b.set(var, "r", (-90.0, 0.0, 0.0))
        b.set_value(var, "sizex", get("size_x"), ValueRole.LENGTH, default=1.0)
        b.set_value(var, "sizey", get("size_y"), ValueRole.LENGTH, default=1.0)
        b.set_value(var, "cols", get("vertices_x"), ValueRole.INTEGER, default=3, integer=True)
        b.set_value(var, "rows", get("vertices_y"), ValueRole.INTEGER, default=3, integer=True)
    elif shape == "uv_sphere":
        var = b.node(op, "sphere")
        b.menu(var, "type", "polymesh")
        b.set_value(var, "radx", get("radius"), ValueRole.LENGTH, default=1.0)
        b.set_value(var, "rady", get("radius"), ValueRole.LENGTH, default=1.0)
        b.set_value(var, "radz", get("radius"), ValueRole.LENGTH, default=1.0)
        b.set(var, "rows", int(b.evaluate(get("rings"), 16)) + 1)
        b.set(var, "cols", int(b.evaluate(get("segments"), 32)))
    elif shape == "ico_sphere":
        var = b.node(op, "sphere")
        b.menu(var, "type", "poly")
        b.set_value(var, "radx", get("radius"), ValueRole.LENGTH, default=1.0)
        b.set_value(var, "rady", get("radius"), ValueRole.LENGTH, default=1.0)
        b.set_value(var, "radz", get("radius"), ValueRole.LENGTH, default=1.0)
        b.set(var, "freq", 2 ** max(int(b.evaluate(get("subdivisions"), 1)) - 1, 0))
    elif shape in ("cylinder", "cone"):
        var = b.node(op, "tube")
        b.menu(var, "type", "poly")
        if shape == "cylinder":
            b.set_value(var, "rad1", get("radius"), ValueRole.LENGTH, default=1.0)
            b.set_value(var, "rad2", get("radius"), ValueRole.LENGTH, default=1.0)
        else:
            b.set_value(var, "rad1", get("radius_top"), ValueRole.LENGTH, default=0.0)
            b.set_value(var, "rad2", get("radius_bottom"), ValueRole.LENGTH, default=1.0)
        b.set_value(var, "height", get("depth"), ValueRole.LENGTH, default=2.0)
        b.set(var, "cols", int(b.evaluate(get("vertices"), 32)))
        b.set(var, "rows", int(b.evaluate(get("side_segments"), 1)) + 1)
        b.set(var, "cap", 0 if op.params.get("fill_type") == "NONE" else 1)
    elif shape == "line":
        var = b.node(op, "line")
        count = int(b.evaluate(get("count"), 10))
        offset = [float(c) for c in b.evaluate(get("offset"), [0.0, 0.0, 1.0])]
        length = math.sqrt(sum(c * c for c in offset))
        b.set_value(var, "origin", get("start"), ValueRole.POSITION, count=3, default=[0.0, 0.0, 0.0])
        if b.is_constant(get("offset")):
            direction = [c / length for c in offset] if length else [0.0, 0.0, 1.0]
            b.set(var, "dir", convert_point(direction, target=HOUDINI))
            b.set(var, "dist", clean_number(length * max(count - 1, 0)))
        else:
            b.set_value(var, "dir", get("offset"), ValueRole.DIRECTION, count=3, default=[0.0, 0.0, 1.0])
            components = b.hscript.components(get("offset"), 3) or ["0", "0", "1"]
            dist = f"({_count_expr(b, get('count'))} - 1) * {_length_expr(components)}"
            b.w.line(f'nb_expr({var}, "dist", {dist!r})')
        b.set_value(var, "points", get("count"), ValueRole.INTEGER, default=10, integer=True)
    else:
        var = b.node(op, "circle")
        b.menu(var, "type", "poly")
        b.menu(var, "orient", "xy")
        b.set(var, "r", (-90.0, 0.0, 0.0))
        b.set_value(var, "radx", get("radius"), ValueRole.LENGTH, default=1.0)
        b.set_value(var, "rady", get("radius"), ValueRole.LENGTH, default=1.0)
        b.set_value(var, "divs", get("vertices"), ValueRole.INTEGER, default=32, integer=True)
    b.set_output(op, "geometry", var)


def _count_expr(b: SopBuilder, value) -> str:
    parts = b.hscript.components(value, 1)
    return parts[0] if parts else "1"


def _length_expr(components: list[str]) -> str:
    """HScript length of a vector given per-component expressions."""
    live = [c for c in components if c not in ("0", "-0", "0.0")]
    if not live:
        return "0"
    if len(live) == 1:
        return f"abs({live[0]})"
    return "sqrt(" + " + ".join(f"pow({c}, 2)" for c in live) + ")"


def _curve_classify(op, graph, base):
    if op.params.get("shape") == "line":
        return Classification(C.EXACT, "Two-point line.", "line SOP")
    if op.params.get("shape") == "spiral":
        return Classification(C.EXACT, "Spiral points generated with Blender's formula in a detail wrangle.", "attribwrangle (detail)")
    return Classification(C.EQUIVALENT, "Closed polygon circle (Houdini polygons are curves when open, faces when closed).", "circle SOP", ["Blender's cyclic curve becomes a closed polygon."])


@_sop("CURVE", C.EQUIVALENT, "line / circle SOP / VEX spiral", classify=_curve_classify)
def _curve(b: SopBuilder, op: SemanticOp) -> None:
    shape = op.params.get("shape")
    if shape == "line":
        start = [float(v) for v in b.evaluate(op.inputs.get("start"), [0.0, 0.0, 0.0])]
        end = [float(v) for v in b.evaluate(op.inputs.get("end"), [0.0, 0.0, 1.0])]
        delta = [e - s for s, e in zip(start, end)]
        length = math.sqrt(sum(d * d for d in delta)) or 1.0
        var = b.node(op, "line")
        b.set(var, "origin", convert_point(start, target=HOUDINI))
        b.set(var, "dir", convert_point([d / length for d in delta], target=HOUDINI))
        b.set(var, "dist", clean_number(length))
        b.set(var, "points", 2)
    elif shape == "circle":
        var = b.node(op, "circle")
        b.menu(var, "type", "poly")
        b.menu(var, "orient", "xy")
        b.set(var, "r", (-90.0, 0.0, 0.0))
        b.set_value(var, "radx", op.inputs.get("radius"), ValueRole.LENGTH, default=1.0)
        b.set_value(var, "rady", op.inputs.get("radius"), ValueRole.LENGTH, default=1.0)
        b.set_value(var, "divs", op.inputs.get("resolution"), ValueRole.INTEGER, default=32, integer=True)
    else:
        resolution = int(b.evaluate(op.inputs.get("resolution"), 32))
        rotations = float(b.evaluate(op.inputs.get("rotations"), 2.0))
        r0, r1 = float(b.evaluate(op.inputs.get("start_radius"), 1.0)), float(b.evaluate(op.inputs.get("end_radius"), 2.0))
        height = float(b.evaluate(op.inputs.get("height"), 2.0))
        sign = -1.0 if op.params.get("reverse") else 1.0
        code = (
            f"int total = {max(int(resolution * rotations), 1)} + 1;\n"
            + "int prim = addprim(0, \"polyline\");\n"
            + "for (int i = 0; i < total; i++) {\n"
            + "    float t = float(i) / float(total - 1);\n"
            + f"    float a = {sign} * 2.0 * PI * {rotations} * t;\n"
            + f"    float r = lerp({r0}, {r1}, t);\n"
            + f"    int pt = addpoint(0, nb_h(set(r * cos(a), r * sin(a), {height} * t)));\n"
            + "    addvertex(0, prim, pt);\n"
            + "}\n"
        )
        var = b.node(op, "attribwrangle", "_spiral")
        b.set(var, "class", 0)
        b.snippet(var, code, ("coordinates",))
    b.set_output(op, "geometry", var)


@_sop("TRANSFORM", C.EXACT, "xform SOP", "Translation, Euler rotation and scale converted to Houdini's Y-up frame (rotation order xzy).")
def _transform(b: SopBuilder, op: SemanticOp) -> None:
    var = b.node(op, "xform")
    b.connect(var, 0, b.stream_for(op.inputs.get("geometry")))
    b.menu(var, "rOrd", "xzy")
    b.set_value(var, "t", op.inputs.get("translation"), ValueRole.POSITION, count=3, default=[0.0] * 3)
    b.set_value(var, "r", op.inputs.get("rotation"), ValueRole.EULER, count=3, default=[0.0] * 3)
    b.set_value(var, "s", op.inputs.get("scale"), ValueRole.SCALE, count=3, default=[1.0] * 3)
    b.set_output(op, "geometry", var)


@_sop("MERGE", C.EXACT, "merge SOP", "Join Geometry becomes a Merge SOP.")
def _merge(b: SopBuilder, op: SemanticOp) -> None:
    var = b.node(op, "merge")
    values = op.inputs.get("geometry", ())
    values = values if isinstance(values, tuple) else (values,)
    for index, value in enumerate(v for v in values if b.stream_for(v) is not None):
        b.connect(var, index, b.stream_for(value))
    b.set_output(op, "geometry", var)


def _domain(op: SemanticOp, default: str = "POINT") -> str:
    return {"POINT": "point", "FACE": "prim", "CURVE": "prim", "INSTANCE": "prim", "CORNER": "vertex"}.get(op.params.get("domain", default), "")


def _delete_classify(op, graph, base):
    if not _domain(op):
        return Classification(C.UNSUPPORTED, f"Deleting on the {op.params.get('domain')} domain is not translated.", "none")
    if op.params.get("mode", "ALL") != "ALL":
        return Classification(C.APPROXIMATE, "Only 'All' delete mode is reproduced; edge/face-only modes delete whole elements.", base.implementation)
    return None


@_sop("DELETE_GEOMETRY", C.EXACT, "attribwrangle removepoint()/removeprim()", "Selection evaluated per element; selected elements are removed (with dependent primitives).", classify=_delete_classify)
def _delete(b: SopBuilder, op: SemanticOp) -> None:
    stream = b.stream_for(op.inputs.get("geometry"))
    selection = op.inputs.get("selection")
    if b.is_false(selection):
        b.set_output(op, "geometry", stream.var if stream else "None")
        return
    domain = _domain(op)

    def body(vc: VexCompiler) -> list[str]:
        cond = vc.value(selection, B, default=1)
        if domain == "point":
            return [f"if ({cond}) removepoint(0, @ptnum, 1);"]
        return [f"if ({cond}) removeprim(0, @primnum, 1);"]

    out = b.wrangle(op, domain, stream, body, "")
    b.set_output(op, "geometry", out.var)


@_sop("SEPARATE", C.EXACT, "two attribwrangles (keep / remove selection)", "Selection and inverted outputs become two wrangles.", classify=_delete_classify)
def _separate(b: SopBuilder, op: SemanticOp) -> None:
    stream = b.stream_for(op.inputs.get("geometry"))
    selection = op.inputs.get("selection")
    domain = _domain(op)
    remover = "removepoint(0, @ptnum, 1)" if domain == "point" else "removeprim(0, @primnum, 1)"
    selected = b.wrangle(op, domain, stream, lambda vc: [f"if (!({vc.value(selection, B, default=1)})) {remover};"], "_selection")
    inverted = b.wrangle(op, domain, stream, lambda vc: [f"if ({vc.value(selection, B, default=1)}) {remover};"], "_inverted")
    b.set_output(op, "selection", selected.var)
    b.set_output(op, "inverted", inverted.var)


def _scatter_classify(op, graph, base):
    if op.params.get("distribution_mode") == "poisson":
        return Classification(C.APPROXIMATE, "Poisson disk sampling is approximated with Scatter's point relaxation.", base.implementation, ["Minimum distance is not enforced exactly.", "Random sample positions differ from Blender."])
    return None


@_sop(
    "SCATTER",
    C.EQUIVALENT,
    "scatter SOP",
    "Distribute Points on Faces becomes a Scatter SOP driven by density per square unit.",
    ("Random sample positions differ from Blender (different random generators).",),
    classify=_scatter_classify,
)
def _scatter(b: SopBuilder, op: SemanticOp) -> None:
    source = b.stream_for(op.inputs.get("geometry"))
    stream, group = b.selection_group(op, source, "prim", "scatter")
    density = op.inputs.get("density", op.inputs.get("density_max"))
    factor = op.inputs.get("density_factor")
    density_field = density is not None and not b.is_constant(density) and not isinstance(density, Param) and b.hscript.components(density, 1) is None
    if density_field or (factor is not None and not (isinstance(factor, Const) and factor.value == 1.0)):
        def body(vc: VexCompiler) -> list[str]:
            expr = vc.value(density, F, default=10.0)
            if factor is not None:
                expr = f"({expr}) * ({vc.value(factor, F, default=1.0)})"
            return [f"f@nb_density = max({expr}, 0.0);"]

        stream = b.wrangle(op, "point", stream, body, "_density")
        b.temp_point_attributes.append("nb_density")
    var = b.node(op, "scatter")
    b.connect(var, 0, stream)
    if group:
        b.set(var, "group", group)
    b.set(var, "forcetotal", 0)
    if density_field or (factor is not None and not (isinstance(factor, Const) and factor.value == 1.0)):
        b.set(var, "usedensityattrib", 1)
        b.set(var, "densityattrib", "nb_density")
        b.set(var, "densityscale", 1.0)
    else:
        b.set_value(var, "densityscale", density, ValueRole.AREA_DENSITY, default=10.0)
    b.set_value(var, "seed", op.inputs.get("seed"), ValueRole.INTEGER, default=0, integer=True)
    b.set(var, "relaxpoints", 1 if op.params.get("distribution_mode") == "poisson" else 0)
    out = Stream(var)
    if b.graph.use_count(op.id, "normal") or b.graph.use_count(op.id, "rotation"):
        attr = f"nb_scatter_N_{snake_case(op.id)}"
        code = (
            "int nb_prim; vector nb_uv;\n"
            "xyzdist(1, @P, nb_prim, nb_uv);\n"
            f'v@{attr} = prim_normal(1, nb_prim, nb_uv.x, nb_uv.y);\n'
        )
        normals = b.node(op, "attribwrangle", "_surface_normal", meta=False)
        b.connect(normals, 0, out)
        b.connect(normals, 1, stream)
        b.set(normals, "class", 2)
        b.snippet(normals, code)
        b.temp_point_attributes.append(attr)
        b.field_attributes[(op.id, "normal")] = ("point_normal", attr, V)
        b.field_attributes[(op.id, "rotation")] = ("point_normal", attr, DataType.ROTATION)
        out = Stream(normals)
    if op.params.get("distribution_mode") == "poisson":
        b.note(op, var, "Poisson disk distribution approximated with point relaxation.")
    b.set_output(op, "points", out.var)


def _instance_classify(op, graph, base):
    if "instance_index" in op.inputs or (isinstance(op.inputs.get("pick_instance"), Const) and op.inputs["pick_instance"].value):
        return Classification(C.APPROXIMATE, "'Pick Instance' is not translated; the whole instance geometry is copied to every point.", base.implementation)
    return None


@_sop(
    "INSTANCE",
    C.EXACT,
    "copytopoints SOP (Pack and Instance)",
    "Instance on Points becomes Copy to Points with packed instances; rotation and scale fields become orient / scale point attributes.",
    classify=_instance_classify,
)
def _instance(b: SopBuilder, op: SemanticOp) -> None:
    points = b.stream_for(op.inputs.get("points"))
    rotation, scale, selection = op.inputs.get("rotation"), op.inputs.get("scale"), op.inputs.get("selection")
    needs_rotation = rotation is not None and not (isinstance(rotation, Const) and all(abs(float(v)) < 1e-9 for v in rotation.value))
    needs_scale = scale is not None and not (isinstance(scale, Const) and all(abs(float(v) - 1.0) < 1e-9 for v in (scale.value if isinstance(scale.value, (list, tuple)) else [scale.value] * 3)))
    if needs_rotation or needs_scale or not b.is_true(selection):
        def body(vc: VexCompiler) -> list[str]:
            lines = []
            if not b.is_true(selection):
                lines.append(f"if (!({vc.value(selection, B, default=1)})) {{ removepoint(0, @ptnum); return; }}")
            if needs_scale:
                lines.append(f"v@scale = nb_hs({vc.value(scale, V, default=1.0)});")
            if needs_rotation:
                lines.append(f"p@orient = nb_orient_h({vc.value(rotation, V, default=0.0)});")
            return lines

        points = b.wrangle(op, "point", points, body, "_instance_attributes")
    var = b.node(op, "copytopoints")
    b.connect(var, 0, b.stream_for(op.inputs.get("instance")))
    b.connect(var, 1, points)
    b.set(var, "pack", 1)
    b.set(var, "useimplicitn", 0)
    b.set_output(op, "instances", var)


@_sop("REALIZE_INSTANCES", C.EXACT, "unpack SOP", "Packed instances are unpacked into real geometry.")
def _realize(b: SopBuilder, op: SemanticOp) -> None:
    var = b.node(op, "unpack")
    b.connect(var, 0, b.stream_for(op.inputs.get("geometry")))
    b.set_output(op, "geometry", var)


@_sop(
    "RANDOM_TRANSFORM",
    C.EQUIVALENT,
    "attribwrangle writing orient / scale",
    "Per-point random rotation and scale ranges written as instancing attributes with NodeBridge's deterministic random.",
    ("Random values differ from Blender's sequence; ranges and distribution are preserved.",),
)
def _random_transform(b: SopBuilder, op: SemanticOp) -> None:
    stream = b.stream_for(op.inputs.get("geometry"))
    stream_offset = int(op.params.get("seed_stream", 0))

    def body(vc: VexCompiler) -> list[str]:
        vc.need("random")
        seed = vc.value(op.inputs.get("seed"), I, default=0)
        rnd = (lambda s: f"nb_random({seed}, nb_id, {s + stream_offset})") if b.options.deterministic_random else (lambda s: f"rand(set(float(nb_id), float({seed}), {s + stream_offset}.0))")
        lines = ['int nb_id = haspointattrib(0, "id") ? point(0, "id", @ptnum) : @ptnum;']
        if "rotation_min" in op.inputs or "rotation_max" in op.inputs:
            lo = vc.value(op.inputs.get("rotation_min"), V, default=0.0)
            hi = vc.value(op.inputs.get("rotation_max"), V, default=0.0)
            lines += [
                f"vector nb_rlo = {lo};",
                f"vector nb_rhi = {hi};",
                f"vector nb_euler = set(fit01({rnd(0)}, nb_rlo.x, nb_rhi.x), fit01({rnd(1)}, nb_rlo.y, nb_rhi.y), fit01({rnd(2)}, nb_rlo.z, nb_rhi.z));",
                'vector4 nb_q = haspointattrib(0, "orient") ? point(0, "orient", @ptnum) : {0, 0, 0, 1};',
                "p@orient = qmultiply(nb_q, nb_orient_h(nb_euler));",
            ]
        if "scale_min" in op.inputs or "scale_max" in op.inputs:
            if op.params.get("uniform_scale"):
                lo = vc.value(op.inputs.get("scale_min"), F, default=1.0)
                hi = vc.value(op.inputs.get("scale_max"), F, default=1.0)
                lines.append(f"float nb_s = fit01({rnd(0)}, {lo}, {hi});")
                lines.append("vector nb_scale = set(nb_s, nb_s, nb_s);")
            else:
                lo = vc.value(op.inputs.get("scale_min"), V, default=1.0)
                hi = vc.value(op.inputs.get("scale_max"), V, default=1.0)
                lines += [f"vector nb_slo = {lo};", f"vector nb_shi = {hi};", f"vector nb_scale = nb_hs(set(fit01({rnd(0)}, nb_slo.x, nb_shi.x), fit01({rnd(1)}, nb_slo.y, nb_shi.y), fit01({rnd(2)}, nb_slo.z, nb_shi.z)));"]
            lines.append('vector nb_prev = haspointattrib(0, "scale") ? point(0, "scale", @ptnum) : {1, 1, 1};')
            lines.append("v@scale = nb_prev * nb_scale;")
        return lines

    out = b.wrangle(op, "point", stream, body, "")
    b.set_output(op, "geometry", out.var)


@_sop("TRANSFORM_POINTS", C.EXACT, "attribwrangle", "Fixed per-point offset / rotation / scale.")
def _transform_points(b: SopBuilder, op: SemanticOp) -> None:
    def body(vc: VexCompiler) -> list[str]:
        lines = []
        if "offset" in op.inputs:
            lines.append(f"@P += nb_h({vc.value(op.inputs['offset'], V)});")
        if "rotation" in op.inputs:
            lines.append(f"p@orient = nb_orient_h({vc.value(op.inputs['rotation'], V)});")
        if "scale" in op.inputs:
            lines.append(f"v@scale = nb_hs({vc.value(op.inputs['scale'], V, default=1.0)});")
        return lines

    out = b.wrangle(op, "point", b.stream_for(op.inputs.get("geometry")), body, "")
    b.set_output(op, "geometry", out.var)


@_sop(
    "INSTANCE_TRANSFORM",
    C.EQUIVALENT,
    "attribwrangle on packed primitive transforms",
    "Rotate / Scale / Translate Instances edit each packed primitive's transform intrinsic.",
    ("Pivot handling follows Blender's local/global switch but is not verified for nested instances.",),
)
def _instance_transform(b: SopBuilder, op: SemanticOp) -> None:
    mode = op.params.get("mode")

    def body(vc: VexCompiler) -> list[str]:
        vc.need("primitives")
        lines = [
            f"if (!({vc.value(op.inputs.get('selection'), B, default=1)})) return;",
            'matrix3 nb_xf = primintrinsic(0, "transform", @primnum);',
            "vector nb_pos = point(0, \"P\", primpoint(0, @primnum, 0));",
            f"int nb_local = {vc.value(op.inputs.get('local_space'), B, default=1)};",
        ]
        if mode == "rotate":
            lines += [
                f"matrix3 nb_r = qconvert(nb_orient_h({vc.value(op.inputs.get('rotation'), V)}));",
                "nb_xf = nb_local ? nb_r * nb_xf : nb_xf * nb_r;",
            ]
        elif mode == "scale":
            lines += [f"vector nb_s = nb_hs({vc.value(op.inputs.get('scale'), V, default=1.0)});", "matrix3 nb_m = ident(); scale(nb_m, nb_s);", "nb_xf = nb_local ? nb_m * nb_xf : nb_xf * nb_m;"]
        else:
            lines += [f"vector nb_t = nb_h({vc.value(op.inputs.get('translation'), V)});", "if (nb_local) nb_t = nb_t * nb_xf;", "setpointattrib(0, \"P\", primpoint(0, @primnum, 0), nb_pos + nb_t);"]
        lines.append('setprimintrinsic(0, "transform", @primnum, nb_xf);')
        return lines

    out = b.wrangle(op, "prim", b.stream_for(op.inputs.get("geometry")), body, "")
    b.set_output(op, "geometry", out.var)


@_sop("SET_POSITION", C.EXACT, "attribwrangle writing @P", "Set Position evaluated per point.")
def _set_position(b: SopBuilder, op: SemanticOp) -> None:
    def body(vc: VexCompiler) -> list[str]:
        position = vc.value(op.inputs["position"], V) if "position" in op.inputs else "nb_b(v@P)"
        offset = vc.value(op.inputs.get("offset"), V, default=0.0)
        selection = op.inputs.get("selection")
        lines = [f"vector nb_new = {position} + {offset};"]
        if b.is_true(selection):
            lines.append("v@P = nb_h(nb_new);")
        else:
            lines.append(f"if ({vc.value(selection, B, default=1)}) v@P = nb_h(nb_new);")
        return lines

    out = b.wrangle(op, "point", b.stream_for(op.inputs.get("geometry")), body, "")
    b.set_output(op, "geometry", out.var)


VEX_ATTR_TYPES = {"FLOAT": "f", "INT": "i", "BOOLEAN": "i", "FLOAT_VECTOR": "v", "FLOAT_COLOR": "v", "BYTE_COLOR": "v", "QUATERNION": "p", "FLOAT2": "u", "INT8": "i"}


@_sop("ATTRIBUTE_WRITE", C.EXACT, "attribwrangle", "Store Named Attribute becomes a typed attribute write.", classify=lambda op, g, base: Classification(C.UNSUPPORTED, "Edge-domain attributes have no Houdini equivalent.", "none") if op.params.get("domain") == "EDGE" else None)
def _attribute_write(b: SopBuilder, op: SemanticOp) -> None:
    name = op.inputs.get("name")
    attr = b.attribute_name(str(name.value)) if isinstance(name, Const) else "attribute"
    data_type = op.params.get("data_type", "FLOAT")
    prefix = VEX_ATTR_TYPES.get(data_type, "f")
    want = {"f": F, "i": I, "v": V}.get(prefix, F)
    domain = _domain(op) or "point"

    def body(vc: VexCompiler) -> list[str]:
        value = vc.value(op.inputs.get("value"), want)
        if attr in ("P", "N"):
            value = f"nb_h({value})"
        line = f"{prefix}@{attr} = {value};"
        selection = op.inputs.get("selection")
        return [line] if b.is_true(selection) else [f"if ({vc.value(selection, B, default=1)}) {line}"]

    out = b.wrangle(op, domain, b.stream_for(op.inputs.get("geometry")), body, "")
    b.set_output(op, "geometry", out.var)


def _extrude_classify(op, graph, base):
    if op.params.get("mode", "FACES") != "FACES":
        return Classification(C.APPROXIMATE, f"Extruding {op.params.get('mode', '').lower()} is approximated with PolyExtrude.", base.implementation)
    if "offset" in op.inputs:
        return Classification(C.APPROXIMATE, "A custom offset vector is reduced to an extrusion distance along normals.", base.implementation)
    return None


@_sop("EXTRUDE", C.EXACT, "polyextrude SOP", "Face extrusion along normals; Top and Side become primitive groups.", classify=_extrude_classify)
def _extrude(b: SopBuilder, op: SemanticOp) -> None:
    stream, group = b.selection_group(op, b.stream_for(op.inputs.get("geometry")), "prim", "extrude")
    var = b.node(op, "polyextrude")
    b.connect(var, 0, stream)
    if group:
        b.set(var, "group", group)
    b.set_value(var, "dist", op.inputs.get("offset_scale"), ValueRole.LENGTH, default=1.0)
    individual = op.inputs.get("individual", Const(True))
    if isinstance(individual, Const):
        b.menu(var, "splittype", "elements" if individual.value else "components")
    b.set(var, "outputback", 0)
    suffix = snake_case(op.id)
    for output, toggle, parm in (("top", "outputfrontgrp", "frontgrp"), ("side", "outputsidegrp", "sidegrp")):
        if b.graph.use_count(op.id, output):
            name = f"nb_{output}_{suffix}"
            b.set(var, toggle, 1)
            b.set(var, parm, name)
            b.field_attributes[(op.id, output)] = ("prim_group", name, B)
    b.set_output(op, "geometry", var)


@_sop(
    "SUBDIVIDE",
    C.EQUIVALENT,
    "subdivide SOP",
    "Subdivision Surface becomes Catmull-Clark subdivision.",
    classify=lambda op, g, base: Classification(C.APPROXIMATE, "Blender's Subdivide Mesh is linear; Houdini's Subdivide SOP smooths (Catmull-Clark).", base.implementation) if op.params.get("method") == "simple" else None,
)
def _subdivide(b: SopBuilder, op: SemanticOp) -> None:
    var = b.node(op, "subdivide")
    b.connect(var, 0, b.stream_for(op.inputs.get("geometry")))
    b.set_value(var, "iterations", op.inputs.get("level"), ValueRole.INTEGER, default=1, integer=True)
    b.set_output(op, "geometry", var)


@_sop("CURVE_RESAMPLE", C.EQUIVALENT, "resample SOP", "Resample by segment count or length.", ("Count is converted to segments (count - 1).",))
def _resample(b: SopBuilder, op: SemanticOp) -> None:
    var = b.node(op, "resample")
    b.connect(var, 0, b.stream_for(op.inputs.get("geometry")))
    if op.params.get("mode") == "LENGTH":
        b.set(var, "dolength", 1)
        b.set_value(var, "length", op.inputs.get("length"), ValueRole.LENGTH, default=0.1)
    else:
        b.set(var, "dolength", 0)
        b.set(var, "dosegs", 1)
        b.set(var, "segs", max(int(b.evaluate(op.inputs.get("count"), 10)) - 1, 1))
    b.set_output(op, "geometry", var)


@_sop("CURVE_TO_MESH", C.APPROXIMATE, "sweep SOP", "Curve to Mesh becomes Sweep with the profile as cross-section.", ("Profile orientation conventions differ; caps are not set.",))
def _curve_to_mesh(b: SopBuilder, op: SemanticOp) -> None:
    var = b.node(op, "sweep")
    b.connect(var, 0, b.stream_for(op.inputs.get("geometry")))
    profile = b.stream_for(op.inputs.get("profile"))
    if profile is not None:
        b.connect(var, 1, profile)
        b.menu(var, "surfaceshape", "input")
    b.set_output(op, "geometry", var)


@_sop("MESH_TO_CURVE", C.EQUIVALENT, "convertline SOP", "Mesh edges become polylines.")
def _mesh_to_curve(b: SopBuilder, op: SemanticOp) -> None:
    var = b.node(op, "convertline")
    b.connect(var, 0, b.stream_for(op.inputs.get("geometry")))
    b.set_output(op, "geometry", var)


@_sop("MESH_TO_POINTS", C.EXACT, "attribwrangle removeprim()", "Vertices kept as points; primitives removed.", classify=lambda op, g, base: Classification(C.UNSUPPORTED, "Only the Vertices mode is translated.", "none") if op.params.get("mode") != "VERTICES" else None)
def _mesh_to_points(b: SopBuilder, op: SemanticOp) -> None:
    out = b.wrangle(op, "prim", b.stream_for(op.inputs.get("geometry")), lambda vc: ["removeprim(0, @primnum, 0);"], "")
    b.set_output(op, "geometry", out.var)


@_sop("BOOLEAN", C.EQUIVALENT, "boolean SOP", "Mesh boolean with the same operation.", ("Solver tolerances differ.",))
def _boolean(b: SopBuilder, op: SemanticOp) -> None:
    var = b.node(op, "boolean")
    b.connect(var, 0, b.stream_for(op.inputs.get("mesh_a")))
    others = op.inputs.get("mesh_b", ())
    others = others if isinstance(others, tuple) else (others,)
    if len(others) > 1:
        merge = b.node(op, "merge", "_operands", meta=False)
        for index, value in enumerate(others):
            b.connect(merge, index, b.stream_for(value))
        b.connect(var, 1, Stream(merge))
    elif others:
        b.connect(var, 1, b.stream_for(others[0]))
    b.menu(var, "booleanop", {"DIFFERENCE": "subtract", "UNION": "union", "INTERSECT": "intersect"}.get(op.params.get("operation"), "subtract"))
    b.set_output(op, "geometry", var)


@_sop(
    "MATERIAL_ASSIGNMENT",
    C.EQUIVALENT,
    "material SOP",
    "Set Material becomes a Material SOP pointing at /mat/<name>.",
    ("The material network is generated only when the Blender material uses nodes.",),
)
def _material(b: SopBuilder, op: SemanticOp) -> None:
    stream, group = b.selection_group(op, b.stream_for(op.inputs.get("geometry")), "prim", "material")
    material = op.inputs.get("material")
    name = material.value.get("name") if isinstance(material, Const) and isinstance(material.value, dict) else ""
    var = b.node(op, "material")
    b.connect(var, 0, stream)
    if group:
        b.set(var, "group1", group)
    if name:
        path = b.materials.get(name, f"/mat/{houdini_node_name(name)}")
        b.set(var, "shop_materialpath1", path)
    b.set_output(op, "geometry", var)


@_sop("OBJECT_REFERENCE", C.APPROXIMATE, "object_merge SOP", "Object Info becomes an Object Merge of /obj/<object name>.", ("Assumes an object with the same (sanitized) name exists in Houdini.",))
def _object_reference(b: SopBuilder, op: SemanticOp) -> None:
    ref = op.inputs.get("object")
    name = ref.value.get("name") if isinstance(ref, Const) and isinstance(ref.value, dict) else ""
    var = b.node(op, "object_merge")
    b.set(var, "objpath1", f"/obj/{houdini_node_name(name)}" if name else "")
    b.set(var, "xformtype", 1)
    b.note(op, var, f"Point this Object Merge at the Houdini equivalent of Blender object '{name}'.")
    b.set_output(op, "geometry", var)


@_sop("COLLECTION_REFERENCE", C.APPROXIMATE, "object_merge SOP", "Collection Info becomes an Object Merge placeholder.", ("Collections have no direct Houdini equivalent; point the merge at the right objects.",))
def _collection_reference(b: SopBuilder, op: SemanticOp) -> None:
    ref = op.inputs.get("collection")
    name = ref.value.get("name") if isinstance(ref, Const) and isinstance(ref.value, dict) else ""
    var = b.node(op, "object_merge")
    b.note(op, var, f"Blender collection '{name}': add the matching Houdini objects to this Object Merge.")
    b.set_output(op, "geometry", var)


@_sop("SWITCH", C.EXACT, "switch SOP / VEX ternary", "Geometry switches become a Switch SOP; field switches become a VEX ternary.")
def _switch(b, op: SemanticOp):
    if isinstance(b, VexCompiler):
        return vex_switch(b, op)
    var = b.node(op, "switch")
    b.connect(var, 0, b.stream_for(op.inputs.get("false")))
    b.connect(var, 1, b.stream_for(op.inputs.get("true")))
    b.set_value(var, "input", op.inputs.get("switch"), ValueRole.INTEGER, default=0, integer=True)
    b.set_output(op, "output", var)


@_sop("SUBGRAPH", C.EXACT, "subnet SOP with promoted parameters", "Node groups become reusable SOP subnets; group inputs become subnet parameters.")
def _subgraph(b: SopBuilder, op: SemanticOp) -> None:
    from .backend import build_subnet

    build_subnet(b, op)
