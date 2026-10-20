"""Compositor -> Houdini COP2 network in ``/img``.

COP2 has no Glare node. Bright pixels are keyed, brightened, blurred and
composited, which is the glow recipe in SideFX's compositing docs. An
ellipse mask is a Shape COP (circle, scaled into an ellipse). A vignette
is that mask, blurred, and multiplied over the image. Copernicus is not
targeted yet. Parameter names follow COP2 conventions but have not been
verified against a live Houdini session; ``nb_set`` reports mismatches.
"""

from __future__ import annotations

import math

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

    def node(self, op: SemanticOp, cop_type: str, suffix: str = "") -> str:
        label = op.display_name if not suffix else f"{op.display_name}_{suffix}"
        hname = self.names.allocate(houdini_node_name(label))
        var = self.vars.allocate(python_identifier(hname))
        self.w.line(f'{var} = nb_create(net, "{cop_type}", "{hname}")')
        return var

    def menu(self, var: str, parm: str, token: str) -> None:
        self.w.line(f'nb_set_menu({var}, "{parm}", "{token}")')

    def input(self, op: SemanticOp, key: str = "image"):
        value = op.inputs.get(key)
        return self.streams.get((value.op, value.output)) if hasattr(value, "op") else None

    def first_stream(self, op: SemanticOp):
        """First linked input that already has a COP, whatever its socket is called."""
        for value in op.inputs.values():
            if isinstance(value, tuple):
                value = value[0] if value else None
            if hasattr(value, "op"):
                found = self.streams.get((value.op, value.output))
                if found:
                    return found
        return None

    def chain(self, op: SemanticOp, var: str, key: str = "image") -> None:
        source = self.input(op, key) or self.first_stream(op)
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
        value = [float(v) for v in list(b.const(op, key, [1.0, 1.0, 1.0]))[:3]]
        if key == "lift" and op.params.get("lift_additive"):
            # Blender 5.x stores lift as the Unreal offset base_lift + (color_lift - 1).
            # Assumption, not checked in a live Houdini session: COP2 colorcorrect lift
            # matches Blender's combined lift (base_lift + color_lift), neutral at 1.
            # That is the same number the 4.x path already writes, which is offset + 1.
            value = [v + 1.0 for v in value]
        b.w.line(f'nb_set({var}, "{key}", {literal(tuple(clean_number(v) for v in value))})')
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


_MIX_COP = {
    "MIX": "blend",
    "ADD": "add",
    "SUBTRACT": "subtract",
    "MULTIPLY": "multiply",
    "SCREEN": "screen",
    "LIGHTEN": "max",
    "DARKEN": "min",
    "DIVIDE": "divide",
    "DIFFERENCE": "difference",
}


@_cop("MIX", C.APPROXIMATE, "matching COP2 blend", "Each blend mode uses the COP2 node of the same operation. Unknown modes stay a placeholder.", ("COP2 has no counterpart for every Blender blend mode.",))
def _mix(b: CopBuilder, op: SemanticOp) -> None:
    mode = str(op.params.get("blend_type", "MIX"))
    cop_type = _MIX_COP.get(mode)
    if cop_type is None:
        var = b.node(op, "null")
        b.chain(op, var, "a")
        b.note(var, f"Mix mode {mode} has no COP2 counterpart.")
        return
    var = b.node(op, cop_type)
    first, second = b.input(op, "a"), b.input(op, "b")
    if first:
        b.w.line(f"{var}.setInput(0, {first})")
    if second:
        b.w.line(f"{var}.setInput(1, {second})")
    factor = op.inputs.get("factor")
    neutral = isinstance(factor, Const) and factor.value is not None and float(factor.value) == 1.0
    if mode == "MIX":
        if isinstance(factor, Const) and factor.value is not None:
            b.w.line(f'nb_set({var}, "effect", {literal(clean_number(float(factor.value)))})')
        b.streams[(op.id, "result")] = var
        return
    if factor is not None and not neutral:
        blend = b.node(op, "blend")
        if first:
            b.w.line(f"{blend}.setInput(0, {first})")
        b.w.line(f"{blend}.setInput(1, {var})")
        if isinstance(factor, Const) and factor.value is not None:
            b.w.line(f'nb_set({blend}, "effect", {literal(clean_number(float(factor.value)))})')
        b.streams[(op.id, "result")] = blend
        return
    b.streams[(op.id, "result")] = var


def _pair(value, default: tuple[float, float]) -> tuple[float, float]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return float(value[0]), float(value[1])
    if isinstance(value, (int, float)):
        return float(value), float(value)
    return default


@_cop(
    "GLARE",
    C.APPROXIMATE,
    "lumakey + bright + blur + over",
    "COP2 has no Glare node. Bright pixels are keyed, brightened, blurred, and composited over the image (SideFX glow recipe).",
    ("Streaks, ghosts, and fog glow all become the same soft glow.", "Glare quality is not translated."),
)
def _glare(b: CopBuilder, op: SemanticOp) -> None:
    source = b.input(op, "image")
    key = b.node(op, "lumakey", "key")
    if source:
        b.w.line(f"{key}.setInput(0, {source})")
    threshold = float(b.const(op, "threshold", 1.0))
    b.w.line(f'nb_set({key}, "domin", 1)')
    b.w.line(f'nb_set({key}, "minlum", {literal(clean_number(threshold))})')
    bright = b.node(op, "bright", "gain")
    b.w.line(f"{bright}.setInput(0, {key})")
    strength = float(b.const(op, "strength", 1.0))
    b.w.line(f'nb_set({bright}, "bright", {literal(clean_number(1.0 + max(strength, 0.0)))})')
    blur = b.node(op, "blur", "spread")
    b.w.line(f"{blur}.setInput(0, {bright})")
    size = _pair(b.const(op, "size", 8), (8.0, 8.0))
    b.w.line(f'nb_set({blur}, "size", {literal(clean_number(max(size)))})')
    over = b.node(op, "over", "glow")
    if source:
        b.w.line(f"{over}.setInput(0, {source})")
    b.w.line(f"{over}.setInput(1, {blur})")
    for name in op.outputs:
        b.streams[(op.id, name)] = over
    b.note(over, "Approximate glow. Streaks, ghosts and fog glow are not reproduced.")


@_cop(
    "ELLIPSE_MASK",
    C.APPROXIMATE,
    "shape COP (circle)",
    "An elliptical mask is a Shape COP circle, scaled and moved in UV.",
    ("Shape COP draws a circle scaled into an ellipse, not a true analytic ellipse.",),
)
def _ellipse(b: CopBuilder, op: SemanticOp) -> None:
    var = b.node(op, "shape")
    b.menu(var, "shapetype", "circle")
    width, height = _pair(b.const(op, "size", [0.2, 0.1]), (0.2, 0.1))
    x, y = _pair(b.const(op, "position", [0.5, 0.5]), (0.5, 0.5))
    b.w.line(f'nb_set({var}, "sx", {literal(clean_number(width))})')
    b.w.line(f'nb_set({var}, "sy", {literal(clean_number(height))})')
    b.w.line(f'nb_set({var}, "tx", {literal(clean_number(x - 0.5))})')
    b.w.line(f'nb_set({var}, "ty", {literal(clean_number(y - 0.5))})')
    b.w.line(f'nb_set({var}, "rz", {literal(clean_number(math.degrees(float(b.const(op, "rotation", 0.0)))))})')
    for name in op.outputs:
        b.streams[(op.id, name)] = var
    b.note(var, "Ellipse mask as a scaled circle. Outside the shape stays black.")


@_cop(
    "VIGNETTE",
    C.APPROXIMATE,
    "shape + blur + multiply",
    "Ellipse mask, blur and multiply become a circle, a blur, and a multiply over the image.",
    ("The falloff is a blurred circle, not a lens vignette profile.",),
)
def _vignette(b: CopBuilder, op: SemanticOp) -> None:
    source = b.input(op, "image")
    shape = b.node(op, "shape", "mask")
    b.menu(shape, "shapetype", "circle")
    width, height = _pair(b.const(op, "size", [0.5, 0.5]), (0.5, 0.5))
    b.w.line(f'nb_set({shape}, "sx", {literal(clean_number(width))})')
    b.w.line(f'nb_set({shape}, "sy", {literal(clean_number(height))})')
    blur = b.node(op, "blur", "falloff")
    b.w.line(f"{blur}.setInput(0, {shape})")
    soft_x, soft_y = _pair(b.const(op, "softness", [0.0, 0.0]), (0.0, 0.0))
    b.w.line(f'nb_set({blur}, "size", {literal(clean_number(max(soft_x, soft_y, 0.0)))})')
    mask = blur
    intensity = float(b.const(op, "intensity", 1.0))
    if abs(intensity - 1.0) > 1e-6:
        amount = b.node(op, "bright", "amount")
        b.w.line(f"{amount}.setInput(0, {blur})")
        b.w.line(f'nb_set({amount}, "bright", {literal(clean_number(intensity))})')
        mask = amount
    mult = b.node(op, "multiply")
    if source:
        b.w.line(f"{mult}.setInput(0, {source})")
    b.w.line(f"{mult}.setInput(1, {mask})")
    for name in op.outputs:
        b.streams[(op.id, name)] = mult
    b.note(mult, "Vignette: blurred circular mask multiplied over the image.")
