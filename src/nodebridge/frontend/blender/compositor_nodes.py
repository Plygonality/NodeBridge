"""Compositor node lifters.

Blender 4.5 moved several node properties (Glare threshold, Color
Balance lift/gamma/gain, Ellipse Mask position/size, Blur size) to
sockets. ``socket_or_prop`` reads whichever exists.
"""

from __future__ import annotations

from ...ir.graph import GraphNode, TreeKind
from ...ir.semantic import Const
from ...ir.types import DataType
from .lifting import LiftContext, lifts

CMP = (TreeKind.COMPOSITOR,)


@lifts("CompositorNodeRLayers", kinds=CMP)
def _render_layer(ctx: LiftContext, node: GraphNode) -> None:
    scene = ctx.prop(node, "scene") or {}
    ctx.emit("RENDER_LAYER", node, params={"layer": ctx.prop(node, "layer", ""), "scene": scene.get("name", "") if isinstance(scene, dict) else ""}, outputs={"image": "Image", "alpha": "Alpha"})


@lifts("CompositorNodeImage", kinds=CMP)
def _image(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit("IMAGE_INPUT", node, {"image_ref": Const(ctx.prop(node, "image"), DataType.IMAGE)}, outputs={"image": "Image", "alpha": "Alpha"})


@lifts("CompositorNodeComposite", "CompositorNodeViewer", kinds=CMP)
def _composite(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit("COMPOSITE_OUTPUT", node, {"image": ctx.input(node, "Image")}, {"viewer": node.type == "CompositorNodeViewer"})


@lifts("CompositorNodeGlare", kinds=CMP)
def _glare(ctx: LiftContext, node: GraphNode) -> None:
    inputs = {
        "image": ctx.input(node, "Image"),
        "threshold": ctx.socket_or_prop(node, "Highlights Threshold", "threshold", 1.0),
        "size": ctx.socket_or_prop(node, "Size", "size", 8),
    }
    if node.find_input("Strength") is not None:
        inputs["strength"] = ctx.input(node, "Strength")
    else:
        mix = float(ctx.prop(node, "mix", 0.0))
        inputs["strength"] = Const((mix + 1.0) / 2.0, DataType.FLOAT)
    ctx.emit("GLARE", node, inputs, {"glare_type": ctx.prop(node, "glare_type", "STREAKS"), "quality": ctx.prop(node, "quality", "MEDIUM")}, {"image": "Image"})


def _graded(ctx: LiftContext, node: GraphNode, base: str, color: str, prop: str):
    if node.find_input(color) is not None:
        base_value = ctx.input(node, base)
        color_value = ctx.input(node, color)
        if isinstance(base_value, Const) and isinstance(color_value, Const):
            scale = float(base_value.value or 0.0)
            rgb = list(color_value.value or [1.0, 1.0, 1.0])[:3]
            return Const([c * scale for c in rgb], DataType.COLOR)
        return color_value
    return Const(list(ctx.prop(node, prop, [1.0, 1.0, 1.0]))[:3], DataType.COLOR)


@lifts("CompositorNodeColorBalance", kinds=CMP)
def _color_balance(ctx: LiftContext, node: GraphNode) -> None:
    method = ctx.prop(node, "correction_method", "LIFT_GAMMA_GAIN")
    ctx.emit(
        "COLOR_BALANCE",
        node,
        {
            "image": ctx.input(node, "Image"),
            "factor": ctx.input(node, "Fac"),
            "lift": _graded(ctx, node, "Base Lift", "Color Lift", "lift"),
            "gamma": _graded(ctx, node, "Base Gamma", "Color Gamma", "gamma"),
            "gain": _graded(ctx, node, "Base Gain", "Color Gain", "gain"),
        },
        {"method": method},
        {"image": "Image"},
    )


@lifts("CompositorNodeEllipseMask", kinds=CMP)
def _ellipse(ctx: LiftContext, node: GraphNode) -> None:
    if node.find_input("Position") is not None:
        position, size = ctx.input(node, "Position"), ctx.input(node, "Size")
        rotation = ctx.input(node, "Rotation")
    else:
        position = Const([ctx.prop(node, "x", 0.5), ctx.prop(node, "y", 0.5)], DataType.VECTOR2)
        size = Const([ctx.prop(node, "mask_width", 0.2), ctx.prop(node, "mask_height", 0.1)], DataType.VECTOR2)
        rotation = Const(ctx.prop(node, "rotation", 0.0), DataType.FLOAT)
    ctx.emit(
        "ELLIPSE_MASK",
        node,
        {"mask": ctx.input(node, "Mask"), "value": ctx.input(node, "Value"), "position": position, "size": size, "rotation": rotation},
        {"mask_type": ctx.prop(node, "mask_type", "ADD")},
        {"mask": "Mask"},
    )


@lifts("CompositorNodeBlur", kinds=CMP)
def _blur(ctx: LiftContext, node: GraphNode) -> None:
    socket = node.find_input("Size")
    if socket is not None and socket.data_type == DataType.VECTOR3:
        size = ctx.input(node, "Size")
    else:
        size = Const([ctx.prop(node, "size_x", 0), ctx.prop(node, "size_y", 0)], DataType.VECTOR2)
    ctx.emit("BLUR", node, {"image": ctx.input(node, "Image"), "size": size}, {"filter_type": ctx.prop(node, "filter_type", "GAUSS"), "relative": bool(ctx.prop(node, "use_relative", False))}, {"image": "Image"})


@lifts("CompositorNodeMixRGB", kinds=CMP)
def _mix(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit(
        "MIX",
        node,
        {"factor": ctx.input(node, "Fac"), "a": ctx.input(node, "Image"), "b": _second_image(ctx, node)},
        {"data_type": "RGBA", "blend_type": ctx.prop(node, "blend_type", "MIX"), "clamp_factor": True, "clamp_result": bool(ctx.prop(node, "use_clamp", False))},
        {"result": "Image"},
        output_types={"result": DataType.COLOR},
    )


def _second_image(ctx: LiftContext, node: GraphNode):
    edges = ctx.edges_into(node, "Image_001")
    if edges:
        return ctx._resolve(edges[0])
    socket = node.input("Image_001")
    return Const(socket.default, DataType.COLOR) if socket else None


_SIMPLE = {
    "CompositorNodeBrightContrast": ("BRIGHT_CONTRAST", {"image": "Image", "bright": "Bright", "contrast": "Contrast"}),
    "CompositorNodeHueSat": ("HUE_SATURATION", {"image": "Image", "hue": "Hue", "saturation": "Saturation", "value": "Value", "factor": "Fac"}),
    "CompositorNodeGamma": ("GAMMA", {"image": "Image", "gamma": "Gamma"}),
    "CompositorNodeExposure": ("EXPOSURE", {"image": "Image", "exposure": "Exposure"}),
    "CompositorNodeLensdist": ("LENS_DISTORTION", {"image": "Image", "distortion": "Distortion", "dispersion": "Dispersion"}),
    "CompositorNodeInvert": ("INVERT", {"image": "Color", "factor": "Fac"}),
}


@lifts(*_SIMPLE, kinds=CMP)
def _simple(ctx: LiftContext, node: GraphNode) -> None:
    kind, sockets = _SIMPLE[node.type]
    out = "Color" if node.type == "CompositorNodeInvert" else "Image"
    ctx.emit(kind, node, {k: ctx.input(node, n) for k, n in sockets.items()}, outputs={"image": out})


@lifts("CompositorNodeRGB", kinds=CMP)
def _rgb(ctx: LiftContext, node: GraphNode) -> None:
    ctx.bind(node, "RGBA", Const(node.outputs[0].default if node.outputs else [1, 1, 1, 1], DataType.COLOR))
