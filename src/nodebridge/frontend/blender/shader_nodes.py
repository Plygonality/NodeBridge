"""Shader node lowering.

Shader graphs reuse the geometry-node math and noise lowerers. Shading
operations stay in the semantic IR as color and shader operations so a
material backend can build a native material instead of a SOP network.
"""

from __future__ import annotations

from nodebridge.frontend.blender.geometry_nodes import _map_range, _math, _noise, _vector_math
from nodebridge.frontend.blender.lower import finish, number, vector
from nodebridge.ir.graph import GraphNode, NodeTree
from nodebridge.ir.operations import field_port, make_operation, value_port
from nodebridge.ir.semantic import OperationKind
from nodebridge.ir.types import DataType


def register_all(register) -> None:
    for node_type, function in LOWERERS.items():
        register(node_type)(function)


def _principled(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.SHADER_OPERATION,
        name=node.label or node.name,
        parameters={
            "mode": "principled",
            "base_color": vector(node, "Base Color", (0.8, 0.8, 0.8)),
            "metallic": number(node, "Metallic", 0.0),
            "roughness": number(node, "Roughness", 0.5),
            "emission": vector(node, "Emission Color", (0.0, 0.0, 0.0)),
            "emission_strength": number(node, "Emission Strength", 0.0),
            "alpha": number(node, "Alpha", 1.0),
            "ior": number(node, "IOR", 1.45),
        },
        inputs={
            "base_color": field_port("base_color", DataType.COLOR),
            "metallic": field_port("metallic", DataType.FLOAT),
            "roughness": field_port("roughness", DataType.FLOAT),
            "normal": field_port("normal", DataType.VECTOR3),
            "emission": field_port("emission", DataType.COLOR),
        },
        outputs={"shader": value_port("shader", DataType.ANY)},
    )
    return finish(
        node,
        operation,
        {
            "Base Color": "base_color",
            "Metallic": "metallic",
            "Roughness": "roughness",
            "Normal": "normal",
            "Emission": "emission",
            "Emission Color": "emission",
            "Emission Strength": "emission_strength",
            "Alpha": "alpha",
            "IOR": "ior",
        },
        {"BSDF": "shader"},
    )


def _shader_output(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.SHADER_OPERATION,
        name=node.label or node.name or "Material Output",
        parameters={"mode": "material_output"},
        inputs={"surface": value_port("surface", DataType.ANY), "volume": value_port("volume", DataType.ANY), "displacement": field_port("displacement", DataType.VECTOR3)},
        outputs={},
    )
    return finish(node, operation, {"Surface": "surface", "Volume": "volume", "Displacement": "displacement"}, {})


def _color(mode: str):
    def lower(node: GraphNode, tree: NodeTree):
        parameters = {
            "mode": mode,
            "blend": str(node.properties.get("blend_type", "MIX")).lower(),
            "factor": number(node, "Factor", 0.5),
            "color": vector(node, "Color", (1.0, 1.0, 1.0)),
        }
        if "color_ramp" in node.properties:
            parameters["stops"] = node.properties["color_ramp"]
        operation = make_operation(
            id=node.id,
            kind=OperationKind.COLOR_OPERATION,
            name=node.label or node.name,
            parameters=parameters,
            inputs={
                "color": field_port("color", DataType.COLOR),
                "color_b": field_port("color_b", DataType.COLOR),
                "factor": field_port("factor", DataType.FLOAT),
            },
            outputs={"color": field_port("color", DataType.COLOR)},
        )
        return finish(
            node,
            operation,
            {"Fac": "factor", "Factor": "factor", "Color": "color", "Color1": "color", "Color2": "color_b", "A": "color", "B": "color_b"},
            {"Color": "color", "Result": "color"},
        )

    return lower


def _image(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.TEXTURE_SAMPLE,
        name=node.label or node.name,
        parameters={"image": node.properties.get("image", "")},
        inputs={"vector": field_port("vector", DataType.VECTOR3)},
        outputs={"color": field_port("color", DataType.COLOR), "alpha": field_port("alpha", DataType.FLOAT)},
    )
    return finish(node, operation, {"Vector": "vector"}, {"Color": "color", "Alpha": "alpha"})


def _tex_coord(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.ATTRIBUTE_READ,
        name=node.label or node.name,
        parameters={"attribute": "uv", "data_type": DataType.VECTOR3.value},
        outputs={
            "uv": field_port("uv", DataType.VECTOR3),
            "object": field_port("object", DataType.VECTOR3),
            "generated": field_port("generated", DataType.VECTOR3),
            "normal": field_port("normal", DataType.VECTOR3),
        },
    )
    return finish(node, operation, {}, {"UV": "uv", "Object": "object", "Generated": "generated", "Normal": "normal"})


def _normal_node(mode: str):
    def lower(node: GraphNode, tree: NodeTree):
        operation = make_operation(
            id=node.id,
            kind=OperationKind.SHADER_OPERATION,
            name=node.label or node.name,
            parameters={"mode": mode, "strength": number(node, "Strength", 1.0), "distance": number(node, "Distance", 0.1)},
            inputs={"normal": field_port("normal", DataType.VECTOR3), "height": field_port("height", DataType.FLOAT), "color": field_port("color", DataType.COLOR)},
            outputs={"normal": field_port("normal", DataType.VECTOR3)},
        )
        return finish(node, operation, {"Normal": "normal", "Height": "height", "Color": "color", "Strength": "strength"}, {"Normal": "normal"})

    return lower


def _value(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.FIELD,
        name=node.label or node.name,
        parameters={"value": number(node, "Value", 0.0) if node.output("Value") is None else _output_default(node), "data_type": "float"},
        outputs={"value": field_port("value", DataType.FLOAT)},
    )
    return finish(node, operation, {}, {"Value": "value"})


def _output_default(node: GraphNode) -> float:
    socket = node.output("Value")
    if socket is not None and isinstance(socket.default, (int, float)):
        return float(socket.default)
    return 0.0


def _rgb(node: GraphNode, tree: NodeTree):
    color = (1.0, 1.0, 1.0)
    socket = node.output("Color")
    if socket is not None and isinstance(socket.default, (list, tuple)):
        values = list(socket.default) + [1.0, 1.0, 1.0]
        color = (float(values[0]), float(values[1]), float(values[2]))
    operation = make_operation(
        id=node.id,
        kind=OperationKind.COLOR_OPERATION,
        name=node.label or node.name,
        parameters={"mode": "constant", "value": color, "color": color},
        outputs={"color": field_port("color", DataType.COLOR)},
    )
    return finish(node, operation, {}, {"Color": "color"})


def _emission(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.SHADER_OPERATION,
        name=node.label or node.name,
        parameters={"mode": "emission", "color": vector(node, "Color", (1.0, 1.0, 1.0)), "strength": number(node, "Strength", 1.0)},
        inputs={"color": field_port("color", DataType.COLOR), "strength": field_port("strength", DataType.FLOAT)},
        outputs={"shader": value_port("shader", DataType.ANY)},
    )
    return finish(node, operation, {"Color": "color", "Strength": "strength"}, {"Emission": "shader"})


def _bsdf(mode: str):
    def lower(node: GraphNode, tree: NodeTree):
        operation = make_operation(
            id=node.id,
            kind=OperationKind.SHADER_OPERATION,
            name=node.label or node.name,
            parameters={"mode": mode, "color": vector(node, "Color", (0.8, 0.8, 0.8)), "roughness": number(node, "Roughness", 0.5)},
            inputs={"color": field_port("color", DataType.COLOR), "roughness": field_port("roughness", DataType.FLOAT), "normal": field_port("normal", DataType.VECTOR3)},
            outputs={"shader": value_port("shader", DataType.ANY)},
        )
        return finish(node, operation, {"Color": "color", "Roughness": "roughness", "Normal": "normal"}, {"BSDF": "shader"})

    return lower


LOWERERS = {
    "ShaderNodeBsdfPrincipled": _principled,
    "ShaderNodeOutputMaterial": _shader_output,
    "ShaderNodeTexNoise": _noise("noise"),
    "ShaderNodeTexVoronoi": _noise("voronoi"),
    "ShaderNodeTexImage": _image,
    "ShaderNodeTexChecker": _color("checker"),
    "ShaderNodeMix": _color("mix"),
    "ShaderNodeMixRGB": _color("mix"),
    "ShaderNodeValToRGB": _color("ramp"),
    "ShaderNodeBump": _normal_node("bump"),
    "ShaderNodeNormalMap": _normal_node("normal_map"),
    "ShaderNodeMath": _math,
    "ShaderNodeVectorMath": _vector_math,
    "ShaderNodeMapRange": _map_range,
    "ShaderNodeRGB": _rgb,
    "ShaderNodeValue": _value,
    "ShaderNodeSeparateColor": _color("separate"),
    "ShaderNodeCombineColor": _color("combine"),
    "ShaderNodeMapping": _vector_math,
    "ShaderNodeTexCoord": _tex_coord,
    "ShaderNodeFresnel": _bsdf("fresnel"),
    "ShaderNodeHueSaturation": _color("hue"),
    "ShaderNodeBrightContrast": _color("brightness"),
    "ShaderNodeInvert": _color("invert"),
    "ShaderNodeEmission": _emission,
    "ShaderNodeBsdfDiffuse": _bsdf("diffuse"),
    "ShaderNodeBsdfGlossy": _bsdf("glossy"),
    "NodeGroupInput": None,  # geometry module registers the shared group nodes
    "NodeGroupOutput": None,
}

LOWERERS = {key: value for key, value in LOWERERS.items() if value is not None}
