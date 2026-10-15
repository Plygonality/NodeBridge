"""Compositor -> Houdini COP2 network in ``/img``.

COP2 has meaningful counterparts for blur, brightness, gamma, HSV and
color correction. Glare and vignettes have no single COP2 node and are
reported. Houdini 20.5's Copernicus context is not targeted yet.
Parameter names below follow COP2 conventions but have not been
verified against a live Houdini session; ``nb_set`` reports mismatches.
"""

from __future__ import annotations

from ...backend.codegen import PyWriter, clean_number, literal
from ...common.names import NameAllocator, houdini_node_name, python_identifier
from ...ir.semantic import Const, SemanticOp
from ...translation.confidence import Confidence as C
from ...translation.registry import translator

T, CTX = "houdini", "cop2"
COP2_NOTE = "COP2 parameter names are not verified against a live Houdini session."


class CopBuilder:
    def __init__(self, backend, result, w: PyWriter) -> None:
        self.backend, self.result, self.w = backend, result, w
        self.graph = result.semantic
        self.vars = NameAllocator({"net", "img"})
        self.names = NameAllocator()
        self.streams: dict[tuple[str, str], str] = {}

    def node(self, op: SemanticOp, cop_type: str) -> str:
        hname = self.names.allocate(houdini_node_name(op.display_name))
        var = self.vars.allocate(python_identifier(hname))
        self.w.line(f'{var} = nb_create(net, "{cop_type}", "{hname}")')
        return var

    def input(self, op: SemanticOp, key: str = "image"):
        value = op.inputs.get(key)
        return self.streams.get((value.op, value.output)) if hasattr(value, "op") else None

    def chain(self, op: SemanticOp, var: str, key: str = "image") -> None:
        source = self.input(op, key)
        if source:
            self.w.line(f"{var}.setInput(0, {source})")
        for name in op.outputs:
            self.streams[(op.id, name)] = var

    def const(self, op: SemanticOp, key: str, default):
        value = op.inputs.get(key)
        return value.value if isinstance(value, Const) and value.value is not None else default

    def note(self, var: str, text: str) -> None:
        if self.result.options.include_comments:
            self.w.line(f"nb_note(net, {text!r}, {var})")


def write_compositor(backend, result, w: PyWriter) -> None:
    w.blank()
    w.line("def build():")
    w.indent()
    w.line('img = hou.node("/img")')
    w.line(f'net = nb_create(img, "img", "{houdini_node_name("nb_" + result.semantic.name)}")')
    builder = CopBuilder(backend, result, w)
    for op in result.semantic.topological_order():
        item = backend.translator(op, CTX)
        c = result.classification(result.semantic, op)
        w.blank()
        if result.options.include_comments:
            w.comment(f"{op.display_name}: {op.kind} [{c.confidence.value}]")
        if item is None or c.confidence == C.UNSUPPORTED or result.is_blocked(result.semantic, op):
            var = builder.node(op, "null")
            builder.chain(op, var)
            builder.note(var, f"'{op.display_name}' ({op.kind}) was not translated: {c.explanation}")
            continue
        item.fn(builder, op)
    w.line("net.layoutChildren()")
    w.line("nb_place_notes()")
    w.line("return net")
    w.dedent()
    w.blank()
    w.line("net = build()")
    w.line('print("NodeBridge: created", net.path())')


def _cop(kind, confidence, implementation, explanation, limitations=()):
    return translator(kind, target=T, context=CTX, confidence=confidence, implementation=implementation, explanation=explanation, limitations=tuple(limitations) + (COP2_NOTE,))


@_cop("RENDER_LAYER", C.APPROXIMATE, "file COP", "A rendered image is read from disk; Houdini has no Blender view layer.", ("Point the File COP at your rendered frames.",))
def _render_layer(b: CopBuilder, op: SemanticOp) -> None:
    var = b.node(op, "file")
    b.w.line(f'nb_set({var}, "filename1", "$HIP/render/$F4.exr")')
    b.note(var, "Set this File COP to the rendered image sequence.")
    b.chain(op, var)


@_cop("IMAGE_INPUT", C.EQUIVALENT, "file COP", "Image file input with the same path.")
def _image(b: CopBuilder, op: SemanticOp) -> None:
    var = b.node(op, "file")
    image = b.const(op, "image_ref", {}) or {}
    b.w.line(f'nb_set({var}, "filename1", {image.get("filepath", "")!r})')
    b.chain(op, var)


@_cop("COMPOSITE_OUTPUT", C.EQUIVALENT, "null OUT (display)", "Final composite marked with the display flag.")
def _output(b: CopBuilder, op: SemanticOp) -> None:
    var = b.node(op, "null")
    b.chain(op, var)
    b.w.line(f"{var}.setDisplayFlag(True)")


@_cop("BLUR", C.EQUIVALENT, "blur COP", "Gaussian blur with the same pixel size.", ("Filter type is not mapped.",))
def _blur(b: CopBuilder, op: SemanticOp) -> None:
    var = b.node(op, "blur")
    size = b.const(op, "size", [0, 0])
    b.w.line(f'nb_set({var}, "size", {literal(clean_number(max(float(size[0]), float(size[1]))))})')
    b.chain(op, var)


@_cop("BRIGHT_CONTRAST", C.APPROXIMATE, "bright COP", "Brightness offset; contrast is approximated.", ("Blender's contrast curve differs.",))
def _bright(b: CopBuilder, op: SemanticOp) -> None:
    var = b.node(op, "bright")
    b.w.line(f'nb_set({var}, "bright", {literal(clean_number(1.0 + float(b.const(op, "bright", 0.0))))})')
    b.chain(op, var)


@_cop("GAMMA", C.EXACT, "gamma COP", "Per-channel gamma.")
def _gamma(b: CopBuilder, op: SemanticOp) -> None:
    var = b.node(op, "gamma")
    b.w.line(f'nb_set({var}, "gamma", {literal(clean_number(float(b.const(op, "gamma", 1.0))))})')
    b.chain(op, var)


@_cop("HUE_SATURATION", C.EQUIVALENT, "hsv COP", "Hue shift / saturation / value adjustment.", ("Hue is converted from Blender's 0..1 (0.5 = no shift) to degrees.",))
def _hsv(b: CopBuilder, op: SemanticOp) -> None:
    var = b.node(op, "hsv")
    b.w.line(f'nb_set({var}, "hueshift", {literal(clean_number((float(b.const(op, "hue", 0.5)) - 0.5) * 360.0))})')
    b.w.line(f'nb_set({var}, "saturation", {literal(clean_number(float(b.const(op, "saturation", 1.0))))})')
    b.w.line(f'nb_set({var}, "value", {literal(clean_number(float(b.const(op, "value", 1.0))))})')
    b.chain(op, var)


@_cop("COLOR_BALANCE", C.APPROXIMATE, "colorcorrect COP", "Lift / gamma / gain mapped onto Color Correct.", ("Blender's lift formula differs from COP2's.",))
def _balance(b: CopBuilder, op: SemanticOp) -> None:
    var = b.node(op, "colorcorrect")
    for key in ("lift", "gamma", "gain"):
        value = b.const(op, key, [1.0, 1.0, 1.0])
        b.w.line(f'nb_set({var}, "{key}", {literal(tuple(clean_number(float(v)) for v in list(value)[:3]))})')
    b.chain(op, var)


@_cop("EXPOSURE", C.EXACT, "bright COP", "Exposure in stops as a 2^stops multiplier.")
def _exposure(b: CopBuilder, op: SemanticOp) -> None:
    var = b.node(op, "bright")
    b.w.line(f'nb_set({var}, "bright", {literal(clean_number(2.0 ** float(b.const(op, "exposure", 0.0))))})')
    b.chain(op, var)


@_cop("INVERT", C.EXACT, "invert COP", "Color inversion.")
def _invert(b: CopBuilder, op: SemanticOp) -> None:
    var = b.node(op, "invert")
    b.chain(op, var)


@_cop("MIX", C.APPROXIMATE, "over / multiply / add COP", "Two-input blend; the factor is not translated.", ("Mix factor is ignored.",))
def _mix(b: CopBuilder, op: SemanticOp) -> None:
    cop_type = {"MULTIPLY": "multiply", "ADD": "add", "SUBTRACT": "subtract"}.get(op.params.get("blend_type"), "over")
    var = b.node(op, cop_type)
    first, second = b.input(op, "a"), b.input(op, "b")
    if first:
        b.w.line(f"{var}.setInput(0, {first})")
    if second:
        b.w.line(f"{var}.setInput(1, {second})")
    b.streams[(op.id, "result")] = var
