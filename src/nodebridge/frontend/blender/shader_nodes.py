"""Shader node lifters.

Math, Vector Math, Mix, Map Range, Clamp, Color Ramp, Combine/Separate
XYZ, Noise and Voronoi are shared with Geometry Nodes (see
``geometry_nodes.py``). ``Value`` and ``RGB`` nodes with a custom label
become exposed material parameters; unlabeled ones are constants.
"""

from __future__ import annotations

from ...common.names import python_identifier
from ...common.units import ValueRole
from ...ir.graph import GraphNode, TreeKind
from ...ir.semantic import Const, ExposedParameter, Param
from ...ir.types import DataType
from .lifting import LiftContext, LiftError, lifts

SH = (TreeKind.SHADER,)


def _expose(ctx: LiftContext, node: GraphNode, data_type: DataType, value, role: ValueRole):
    if not node.label:
        return Const(value, data_type)
    key = python_identifier(node.label, "parameter")
    existing = {p.key for p in ctx.graph.parameters}
    base, index = key, 1
    while key in existing:
        index += 1
        key = f"{base}_{index}"
    ctx.graph.parameters.append(ExposedParameter(key=key, name=node.label, data_type=data_type, role=role, default=value, identifier=node.id))
    return Param(key)


@lifts("ShaderNodeValue", kinds=SH)
def _value(ctx: LiftContext, node: GraphNode) -> None:
    value = node.outputs[0].default if node.outputs else 0.0
    ctx.bind(node, "Value", _expose(ctx, node, DataType.FLOAT, value, ValueRole.SCALAR))


@lifts("ShaderNodeRGB", kinds=SH)
def _rgb(ctx: LiftContext, node: GraphNode) -> None:
    value = node.outputs[0].default if node.outputs else [1.0, 1.0, 1.0, 1.0]
    ctx.bind(node, "Color", _expose(ctx, node, DataType.COLOR, value, ValueRole.COLOR))


@lifts("ShaderNodeOutputMaterial", kinds=SH)
def _material_output(ctx: LiftContext, node: GraphNode) -> None:
    if node.parameters.get("is_active_output") is False:
        return
    ctx.emit(
        "MATERIAL_OUTPUT",
        node,
        {"surface": ctx.input(node, "Surface"), "displacement": ctx.input(node, "Displacement") if ctx.has_link(node, "Displacement") else None},
        {"material": ctx.tree.metadata.get("material", ctx.tree.name), "target": ctx.prop(node, "target", "ALL")},
    )
    if ctx.has_link(node, "Volume"):
        ctx.warn("lift.volume", f"{node.display_name}: volume shading is not translated.", node)


_PRINCIPLED = {
    "base_color": "Base Color",
    "metallic": "Metallic",
    "roughness": "Roughness",
    "ior": "IOR",
    "alpha": "Alpha",
    "specular": "Specular IOR Level",
    "emission_color": "Emission Color",
    "emission_strength": "Emission Strength",
    "transmission": "Transmission Weight",
    "coat": "Coat Weight",
    "coat_roughness": "Coat Roughness",
    "sheen": "Sheen Weight",
    "subsurface": "Subsurface Weight",
}


@lifts("ShaderNodeBsdfPrincipled", kinds=SH)
def _principled(ctx: LiftContext, node: GraphNode) -> None:
    inputs = {key: ctx.input(node, name) for key, name in _PRINCIPLED.items()}
    if ctx.has_link(node, "Normal"):
        inputs["normal"] = ctx.input(node, "Normal")
    ctx.emit("SHADER_BSDF", node, inputs, {"model": "principled", "distribution": ctx.prop(node, "distribution", "MULTI_GGX")}, {"shader": "BSDF"})


@lifts("ShaderNodeBsdfDiffuse", kinds=SH)
def _diffuse(ctx: LiftContext, node: GraphNode) -> None:
    inputs = {"base_color": ctx.input(node, "Color"), "roughness": ctx.input(node, "Roughness")}
    if ctx.has_link(node, "Normal"):
        inputs["normal"] = ctx.input(node, "Normal")
    ctx.emit("SHADER_BSDF", node, inputs, {"model": "diffuse"}, {"shader": "BSDF"})


@lifts("ShaderNodeEmission", kinds=SH)
def _emission(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit("SHADER_BSDF", node, {"emission_color": ctx.input(node, "Color"), "emission_strength": ctx.input(node, "Strength")}, {"model": "emission"}, {"shader": "Emission"})


@lifts("ShaderNodeMixShader", "ShaderNodeAddShader", kinds=SH)
def _mix_shader(ctx: LiftContext, node: GraphNode) -> None:
    shaders = [s for s in node.inputs if s.data_type == DataType.SHADER]
    values = []
    for socket in shaders:
        edges = ctx.edges_into(node, socket.identifier)
        values.append(ctx._resolve(edges[0]) if edges else None)
    inputs = {"a": values[0] if values else None, "b": values[1] if len(values) > 1 else None}
    if node.type == "ShaderNodeMixShader":
        inputs["factor"] = ctx.input(node, "Fac")
    ctx.emit("SHADER_MIX", node, inputs, {"mode": "MIX" if node.type == "ShaderNodeMixShader" else "ADD"}, {"shader": "Shader"})


@lifts("ShaderNodeTexImage", kinds=SH)
def _image(ctx: LiftContext, node: GraphNode) -> None:
    image = ctx.prop(node, "image")
    ctx.emit(
        "TEXTURE_SAMPLE",
        node,
        {"vector": ctx.input(node, "Vector", implicit="uv"), "image": Const(image, DataType.IMAGE)},
        {"interpolation": ctx.prop(node, "interpolation", "Linear"), "extension": ctx.prop(node, "extension", "REPEAT"), "projection": ctx.prop(node, "projection", "FLAT")},
        {"color": "Color", "alpha": "Alpha"},
    )


_COORDS = {"Generated": "generated", "Normal": "normal", "UV": "uv", "Object": "object", "Camera": "camera", "Window": "window", "Reflection": "reflection"}


@lifts("ShaderNodeTexCoord", kinds=SH)
def _texcoord(ctx: LiftContext, node: GraphNode) -> None:
    linked = {e.from_socket for e in ctx.tree.outgoing(node.id)}
    for socket_name, field in _COORDS.items():
        socket = node.find_output(socket_name)
        if socket is not None and socket.identifier in linked:
            ctx.emit("FIELD_INPUT", node, params={"field": field}, outputs={"value": socket_name}, output_types={"value": DataType.VECTOR3}, name=f"{node.display_name} {socket_name}")


@lifts("ShaderNodeUVMap", kinds=SH)
def _uvmap(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit("FIELD_INPUT", node, params={"field": "uv", "uv_map": ctx.prop(node, "uv_map", "")}, outputs={"value": "UV"}, output_types={"value": DataType.VECTOR3})


_GEOMETRY_FIELDS = {"Position": "world_position", "Normal": "normal", "Tangent": "tangent", "Incoming": "camera"}


@lifts("ShaderNodeNewGeometry", kinds=SH)
def _geometry(ctx: LiftContext, node: GraphNode) -> None:
    linked = {e.from_socket for e in ctx.tree.outgoing(node.id)}
    for socket_name, field in _GEOMETRY_FIELDS.items():
        socket = node.find_output(socket_name)
        if socket is not None and socket.identifier in linked:
            ctx.emit("FIELD_INPUT", node, params={"field": field}, outputs={"value": socket_name}, output_types={"value": DataType.VECTOR3}, name=f"{node.display_name} {socket_name}")
    for socket_name in ("Parametric", "Backfacing", "Pointiness", "Random Per Island", "True Normal"):
        socket = node.find_output(socket_name)
        if socket is not None and socket.identifier in linked:
            raise LiftError(f"Geometry output {socket_name!r} is not translated.")


@lifts("ShaderNodeMapping", kinds=SH)
def _mapping(ctx: LiftContext, node: GraphNode) -> None:
    vector_type = ctx.prop(node, "vector_type", "POINT")
    inputs = {"vector": ctx.input(node, "Vector", implicit="generated"), "scale": ctx.input(node, "Scale")}
    if vector_type in ("POINT", "TEXTURE"):
        inputs["location"] = ctx.input(node, "Location")
    inputs["rotation"] = ctx.input(node, "Rotation")
    ctx.emit("MAPPING", node, inputs, {"vector_type": vector_type}, {"vector": "Vector"})


@lifts("ShaderNodeBump", kinds=SH)
def _bump(ctx: LiftContext, node: GraphNode) -> None:
    inputs = {"strength": ctx.input(node, "Strength"), "distance": ctx.input(node, "Distance"), "height": ctx.input(node, "Height")}
    if ctx.has_link(node, "Normal"):
        inputs["normal"] = ctx.input(node, "Normal")
    ctx.emit("BUMP", node, inputs, {"invert": bool(ctx.prop(node, "invert", False))}, {"normal": "Normal"})


@lifts("ShaderNodeNormalMap", kinds=SH)
def _normal_map(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit("NORMAL_MAP", node, {"strength": ctx.input(node, "Strength"), "color": ctx.input(node, "Color")}, {"space": ctx.prop(node, "space", "TANGENT")}, {"normal": "Normal"})


_COLOR_OPS = {
    "ShaderNodeInvert": ("invert", {"factor": "Fac", "color": "Color"}),
    "ShaderNodeHueSaturation": ("hue_saturation", {"a": "Hue", "b": "Saturation", "c": "Value", "factor": "Fac", "color": "Color"}),
    "ShaderNodeGamma": ("gamma", {"color": "Color", "a": "Gamma"}),
    "ShaderNodeBrightContrast": ("bright_contrast", {"color": "Color", "a": "Bright", "b": "Contrast"}),
    "ShaderNodeRGBToBW": ("rgb_to_bw", {"color": "Color"}),
}


@lifts(*_COLOR_OPS, kinds=SH)
def _color_op(ctx: LiftContext, node: GraphNode) -> None:
    operation, sockets = _COLOR_OPS[node.type]
    outputs = {"value": "Val"} if operation == "rgb_to_bw" else {"color": "Color"}
    ctx.emit("COLOR_OPERATION", node, {k: ctx.input(node, n) for k, n in sockets.items()}, {"operation": operation}, outputs)


@lifts("ShaderNodeSeparateColor", kinds=SH)
def _separate_color(ctx: LiftContext, node: GraphNode) -> None:
    if ctx.prop(node, "mode", "RGB") != "RGB":
        raise LiftError("Separate Color is lifted only in RGB mode.")
    ctx.emit("COLOR_OPERATION", node, {"color": ctx.input(node, "Color")}, {"operation": "separate_rgb"}, {"r": "Red", "g": "Green", "b": "Blue"})


@lifts("ShaderNodeCombineColor", kinds=SH)
def _combine_color(ctx: LiftContext, node: GraphNode) -> None:
    if ctx.prop(node, "mode", "RGB") != "RGB":
        raise LiftError("Combine Color is lifted only in RGB mode.")
    ctx.emit("COLOR_OPERATION", node, {"a": ctx.input(node, "Red"), "b": ctx.input(node, "Green"), "c": ctx.input(node, "Blue")}, {"operation": "combine_rgb"}, {"color": "Color"})


_PROCEDURAL = {"ShaderNodeTexGradient": "gradient", "ShaderNodeTexChecker": "checker", "ShaderNodeTexWave": "wave"}


@lifts(*_PROCEDURAL, kinds=SH)
def _procedural(ctx: LiftContext, node: GraphNode) -> None:
    inputs = {"vector": ctx.input(node, "Vector", implicit="generated")}
    if node.find_input("Scale") is not None:
        inputs["scale"] = ctx.input(node, "Scale")
    params = {"texture": _PROCEDURAL[node.type]}
    for key in ("gradient_type", "wave_type", "bands_direction", "wave_profile"):
        if key in node.parameters:
            params[key] = node.parameters[key]
    ctx.emit("PROCEDURAL_TEXTURE", node, inputs, params, {"fac": "Fac", "color": "Color"})
