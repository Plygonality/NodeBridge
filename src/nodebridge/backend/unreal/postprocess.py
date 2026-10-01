"""Compositor -> an unbound Unreal Post Process Volume.

Unreal has no node-based compositor that Python can build, but the
*intent* of a typical grading chain (bloom, color balance, vignette,
exposure) maps onto Post Process Volume settings. Arbitrary image
operations (blur, masks, generic mixes) would need a post-process
material and are reported as UNSUPPORTED.
"""

from __future__ import annotations

from ...backend.codegen import PyWriter, clean_number, literal
from ...common.names import unreal_asset_name
from ...ir.semantic import Const, SemanticOp
from ...translation.confidence import Confidence as C
from ...translation.registry import translator

T, CTX = "unreal", "postprocess"


class PostProcessBuilder:
    def __init__(self, result, w: PyWriter) -> None:
        self.result, self.w = result, w
        self.graph = result.semantic

    def const(self, op: SemanticOp, key: str, default):
        value = op.inputs.get(key)
        return value.value if isinstance(value, Const) and value.value is not None else default

    def setting(self, name: str, expression: str) -> None:
        self.w.line(f'nb_setting(settings, "{name}", {expression})')

    def vector4(self, values, w: float = 1.0) -> str:
        items = list(values) if isinstance(values, (list, tuple)) else [values] * 3
        x, y, z = (clean_number(float(v)) for v in (items + [1.0, 1.0, 1.0])[:3])
        return f"unreal.Vector4({literal(x)}, {literal(y)}, {literal(z)}, {literal(w)})"


HELPER = '''

def nb_setting(settings, name, value):
    """Set a post-process value and enable its override flag."""
    if nb_prop(settings, name, value):
        nb_prop(settings, "override_" + name, True)
'''


def write_postprocess(backend, result, w: PyWriter) -> None:
    w.block(HELPER)
    w.blank()
    w.line("def build():")
    w.indent()
    w.line("actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)")
    w.line("volume = actors.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0.0, 0.0, 0.0))")
    w.line(f'volume.set_actor_label("{unreal_asset_name(result.semantic.name, "NB_")}")')
    w.line('nb_prop(volume, "unbound", True)')
    w.line('settings = volume.get_editor_property("settings")')
    builder = PostProcessBuilder(result, w)
    for op in result.semantic.topological_order():
        item = backend.translator(op, CTX)
        c = result.classification(result.semantic, op)
        if result.options.include_comments:
            w.comment(f"{op.display_name}: {op.kind} [{c.confidence.value}]")
        if item is None or c.confidence == C.UNSUPPORTED or result.is_blocked(result.semantic, op):
            w.line(f"NB_WARNINGS.append({f'Not translated: {op.display_name} ({op.kind}). {c.explanation}'!r})")
            continue
        item.fn(builder, op)
    w.line('volume.set_editor_property("settings", settings)')
    w.line("return volume")
    w.dedent()


def _pp(kind, confidence, implementation, explanation, limitations=()):
    return translator(kind, target=T, context=CTX, confidence=confidence, implementation=implementation, explanation=explanation, limitations=limitations)


@_pp("RENDER_LAYER", C.EQUIVALENT, "rendered scene", "The volume grades the rendered scene, like a Render Layers input.")
def _render_layer(b: PostProcessBuilder, op: SemanticOp) -> None:
    return None


@_pp("COMPOSITE_OUTPUT", C.EQUIVALENT, "unbound Post Process Volume", "The final composite becomes an unbound volume affecting the whole level.")
def _output(b: PostProcessBuilder, op: SemanticOp) -> None:
    return None


@_pp("GLARE", C.APPROXIMATE, "Bloom intensity / threshold", "Glare becomes Unreal bloom; streaks and ghosts map to bloom as well.", ("Glare shape (streaks, ghosts, star) is not reproduced.",))
def _glare(b: PostProcessBuilder, op: SemanticOp) -> None:
    b.setting("bloom_intensity", literal(clean_number(float(b.const(op, "strength", 0.5)) * 2.0)))
    b.setting("bloom_threshold", literal(clean_number(float(b.const(op, "threshold", 1.0)))))


@_pp("COLOR_BALANCE", C.APPROXIMATE, "Color grading gain / gamma / offset", "Lift / gamma / gain mapped onto global color grading.", ("Blender's lift formula differs from Unreal's offset.",))
def _balance(b: PostProcessBuilder, op: SemanticOp) -> None:
    b.setting("color_gain", b.vector4(b.const(op, "gain", [1, 1, 1])))
    b.setting("color_gamma", b.vector4(b.const(op, "gamma", [1, 1, 1])))
    lift = [float(v) - 1.0 for v in list(b.const(op, "lift", [1, 1, 1]))[:3]]
    b.setting("color_offset", b.vector4(lift, 0.0))


@_pp("COLOR_CORRECTION", C.APPROXIMATE, "Color grading saturation / contrast / gamma / gain", "Master color correction mapped onto global grading.")
def _correction(b: PostProcessBuilder, op: SemanticOp) -> None:
    for key, name in (("saturation", "color_saturation"), ("contrast", "color_contrast"), ("gamma", "color_gamma"), ("gain", "color_gain")):
        b.setting(name, b.vector4(b.const(op, key, 1.0)))


@_pp("VIGNETTE", C.APPROXIMATE, "Vignette intensity", "Ellipse mask + blur + multiply recognized as a vignette.", ("Vignette shape and softness use Unreal's built-in falloff.",))
def _vignette(b: PostProcessBuilder, op: SemanticOp) -> None:
    b.setting("vignette_intensity", literal(clean_number(float(b.const(op, "intensity", 0.4)))))


@_pp("HUE_SATURATION", C.APPROXIMATE, "Color saturation", "Saturation maps onto global color saturation.", ("Hue shift and value are not translated.",))
def _hue_sat(b: PostProcessBuilder, op: SemanticOp) -> None:
    b.setting("color_saturation", b.vector4(b.const(op, "saturation", 1.0)))


@_pp("BRIGHT_CONTRAST", C.APPROXIMATE, "Color contrast / offset", "Brightness and contrast map onto global grading.", ("Blender's contrast curve differs.",))
def _bright(b: PostProcessBuilder, op: SemanticOp) -> None:
    b.setting("color_contrast", b.vector4(1.0 + float(b.const(op, "contrast", 0.0)) / 100.0))
    bright = float(b.const(op, "bright", 0.0)) / 100.0
    b.setting("color_offset", b.vector4([bright] * 3, 0.0))


@_pp("GAMMA", C.EQUIVALENT, "Color gamma", "Gamma maps onto global color gamma.")
def _gamma(b: PostProcessBuilder, op: SemanticOp) -> None:
    b.setting("color_gamma", b.vector4(b.const(op, "gamma", 1.0)))


@_pp("EXPOSURE", C.EQUIVALENT, "Exposure compensation", "Exposure in stops maps onto exposure compensation.")
def _exposure(b: PostProcessBuilder, op: SemanticOp) -> None:
    b.setting("auto_exposure_bias", literal(clean_number(float(b.const(op, "exposure", 0.0)))))


@_pp("LENS_DISTORTION", C.APPROXIMATE, "Chromatic aberration", "Dispersion maps onto scene fringe; distortion is not translated.", ("Barrel / pincushion distortion has no post-process setting.",))
def _lens(b: PostProcessBuilder, op: SemanticOp) -> None:
    b.setting("scene_fringe_intensity", literal(clean_number(float(b.const(op, "dispersion", 0.0)) * 5.0)))
