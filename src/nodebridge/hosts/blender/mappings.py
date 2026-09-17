"""Blender Geometry Nodes ↔ semantic operation mappings.

Native ``bl_idname`` values never become IR operation names. They are
recorded as provenance. Mapping is parameter-aware: one Blender node type
can resolve to several semantic operations.
"""

from __future__ import annotations

from nodebridge.core.diagnostics import TranslationStatus
from nodebridge.core.node import IRNode
from nodebridge.core.values import JSONValue
from nodebridge.hosts.native import NativeGraph, NativeNode
from nodebridge.hosts.recipes import NodeTemplate, Recipe

MATH_OPERATIONS = {
    "ADD": "math.add",
    "SUBTRACT": "math.subtract",
    "MULTIPLY": "math.multiply",
    "DIVIDE": "math.divide",
    "POWER": "math.power",
    "MINIMUM": "math.min",
    "MAXIMUM": "math.max",
}

VECTOR_OPERATIONS = {
    "ADD": "vector.add",
    "SUBTRACT": "vector.subtract",
    "MULTIPLY": "vector.scale",
    "NORMALIZE": "vector.normalize",
    "CROSS_PRODUCT": "vector.cross",
    "DOT_PRODUCT": "vector.dot",
    "DISTANCE": "vector.distance",
    "SCALE": "vector.scale",
}

RANDOM_TYPES = {
    "FLOAT": "random.float",
    "INT": "random.integer",
    "INTEGER": "random.integer",
    "FLOAT_VECTOR": "random.vector",
    "VECTOR": "random.vector",
}

STATIC_OPERATIONS = {
    "NodeGroupInput": "graph.input",
    "NodeGroupOutput": "graph.output",
    "GeometryNodeTransform": "geometry.transform",
    "GeometryNodeJoinGeometry": "geometry.join",
    "GeometryNodeSeparateGeometry": "geometry.separate",
    "GeometryNodeRealizeInstances": "geometry.realize_instances",
    "GeometryNodeInstanceOnPoints": "geometry.instance",
    "GeometryNodeDistributePointsOnFaces": "points.distribute",
    "GeometryNodeSetPosition": "geometry.modify_position",
    "GeometryNodeDeleteGeometry": "geometry.delete",
    "GeometryNodeMeshCube": "geometry.primitive",
    "GeometryNodeMeshGrid": "geometry.primitive",
    "GeometryNodeMeshIcoSphere": "geometry.primitive",
    "GeometryNodeMeshUVSphere": "geometry.primitive",
    "GeometryNodeMeshCircle": "geometry.primitive",
    "GeometryNodeMeshCone": "geometry.primitive",
    "GeometryNodeMeshCylinder": "geometry.primitive",
    "GeometryNodeMeshLine": "geometry.primitive",
    "GeometryNodeInputNamedAttribute": "attribute.read",
    "GeometryNodeStoreNamedAttribute": "attribute.write",
    "GeometryNodeSampleIndex": "attribute.transfer",
    "FunctionNodeCompare": "selection.compare",
    "ShaderNodeClamp": "math.clamp",
    "ShaderNodeMapRange": "math.map_range",
    "ShaderNodeTexNoise": "procedural.noise",
    "ShaderNodeTexVoronoi": "procedural.voronoi",
    "ShaderNodeMix": "color.mix",
    "ShaderNodeValToRGB": "color.ramp",
    "ShaderNodeBsdfPrincipled": "shader.principled_surface",
    "ShaderNodeTexImage": "texture.sample",
}

PRIMITIVE_KINDS = {
    "GeometryNodeMeshCube": "cube",
    "GeometryNodeMeshGrid": "grid",
    "GeometryNodeMeshIcoSphere": "ico_sphere",
    "GeometryNodeMeshUVSphere": "uv_sphere",
    "GeometryNodeMeshCircle": "circle",
    "GeometryNodeMeshCone": "cone",
    "GeometryNodeMeshCylinder": "cylinder",
    "GeometryNodeMeshLine": "line",
}


def resolve_blender_node(node: NativeNode, graph: NativeGraph) -> tuple[str, dict[str, object]]:
    """Return ``(semantic_operation, extras)`` for a Blender native node."""
    del graph
    bl_type = node.type
    extras: dict[str, object] = {}
    if bl_type in {"ShaderNodeMath", "FunctionNodeIntegerMath"}:
        operation = str(node.parameters.get("operation") or "ADD").upper()
        return MATH_OPERATIONS.get(operation, "math.add"), extras
    if bl_type == "ShaderNodeVectorMath":
        operation = str(node.parameters.get("operation") or "ADD").upper()
        return VECTOR_OPERATIONS.get(operation, "vector.add"), extras
    if bl_type == "FunctionNodeRandomValue":
        data_type = str(node.parameters.get("data_type") or "FLOAT").upper()
        return RANDOM_TYPES.get(data_type, "random.float"), extras
    if bl_type in PRIMITIVE_KINDS:
        extras["parameters"] = {
            "primitive": PRIMITIVE_KINDS[bl_type],
            "size": node.parameters.get("size", 1.0),
        }
        return "geometry.primitive", extras
    if bl_type in STATIC_OPERATIONS:
        return STATIC_OPERATIONS[bl_type], extras
    return "unknown", extras


def _params_from_ir(node: IRNode) -> dict[str, JSONValue]:
    return {name: parameter.value for name, parameter in node.parameters.items()}


def _math_params(node: IRNode) -> dict[str, JSONValue]:
    inverse = {value: key for key, value in MATH_OPERATIONS.items()}
    params = _params_from_ir(node)
    params.setdefault("operation", inverse.get(node.operation, "ADD"))
    for socket in node.inputs.values():
        if socket.default is not None:
            params.setdefault(socket.name, socket.default)
    return params


def _vector_params(node: IRNode) -> dict[str, JSONValue]:
    inverse = {value: key for key, value in VECTOR_OPERATIONS.items()}
    params = _params_from_ir(node)
    params.setdefault("operation", inverse.get(node.operation, "ADD"))
    return params


def _random_params(node: IRNode) -> dict[str, JSONValue]:
    inverse = {
        "random.float": "FLOAT",
        "random.integer": "INT",
        "random.vector": "FLOAT_VECTOR",
    }
    params = _params_from_ir(node)
    params.setdefault("data_type", inverse.get(node.operation, "FLOAT"))
    for socket in node.inputs.values():
        if socket.default is not None:
            params.setdefault(socket.name, socket.default)
    return params


def _primitive_params(node: IRNode) -> dict[str, JSONValue]:
    params = _params_from_ir(node)
    params.setdefault("primitive", "cube")
    return params


def _recipe(
    operation: str,
    native_type: str,
    *,
    fidelity: TranslationStatus = TranslationStatus.EXACT,
    inputs: tuple[str, ...] = ("Geometry",),
    outputs: tuple[str, ...] = ("Geometry",),
    expose_inputs: dict[str, tuple[str, str]] | None = None,
    expose_outputs: dict[str, tuple[str, str]] | None = None,
    note: str = "",
    parameter_builder=None,
) -> Recipe:
    local = "node"
    return Recipe(
        operation=operation,
        fidelity=fidelity,
        nodes=(
            NodeTemplate(
                local_id=local,
                native_type=native_type,
                inputs=inputs,
                outputs=outputs,
            ),
        ),
        expose_inputs=expose_inputs or {"geometry": (local, inputs[0] if inputs else "Geometry")},
        expose_outputs=expose_outputs
        or {"geometry": (local, outputs[0] if outputs else "Geometry")},
        note=note,
        parameter_builder=parameter_builder,
    )


BLENDER_RECIPES: dict[str, Recipe] = {
    "graph.input": _recipe(
        "graph.input",
        "NodeGroupInput",
        inputs=(),
        outputs=("Geometry",),
        expose_inputs={},
        expose_outputs={"geometry": ("node", "Geometry")},
    ),
    "graph.output": _recipe(
        "graph.output",
        "NodeGroupOutput",
        inputs=("Geometry",),
        outputs=(),
        expose_inputs={"geometry": ("node", "Geometry")},
        expose_outputs={},
    ),
    "geometry.transform": _recipe(
        "geometry.transform",
        "GeometryNodeTransform",
        inputs=("Geometry", "Translation", "Rotation", "Scale"),
        outputs=("Geometry",),
        expose_inputs={
            "geometry": ("node", "Geometry"),
            "translation": ("node", "Translation"),
            "rotation": ("node", "Rotation"),
            "scale": ("node", "Scale"),
        },
    ),
    "geometry.join": _recipe(
        "geometry.join",
        "GeometryNodeJoinGeometry",
        inputs=("Geometry",),
        outputs=("Geometry",),
    ),
    "geometry.separate": _recipe(
        "geometry.separate",
        "GeometryNodeSeparateGeometry",
        inputs=("Geometry", "Selection"),
        outputs=("Selection", "Inverted"),
        expose_inputs={"geometry": ("node", "Geometry"), "selection": ("node", "Selection")},
        expose_outputs={"true": ("node", "Selection"), "false": ("node", "Inverted")},
    ),
    "geometry.realize_instances": _recipe(
        "geometry.realize_instances",
        "GeometryNodeRealizeInstances",
    ),
    "geometry.instance": _recipe(
        "geometry.instance",
        "GeometryNodeInstanceOnPoints",
        inputs=("Points", "Instance", "Scale", "Rotation"),
        outputs=("Instances",),
        expose_inputs={
            "points": ("node", "Points"),
            "instance": ("node", "Instance"),
            "scale": ("node", "Scale"),
            "rotation": ("node", "Rotation"),
        },
        expose_outputs={"instances": ("node", "Instances"), "geometry": ("node", "Instances")},
    ),
    "points.distribute": _recipe(
        "points.distribute",
        "GeometryNodeDistributePointsOnFaces",
        inputs=("Mesh", "Density", "Seed"),
        outputs=("Points",),
        expose_inputs={
            "geometry": ("node", "Mesh"),
            "density": ("node", "Density"),
            "seed": ("node", "Seed"),
        },
        expose_outputs={"points": ("node", "Points"), "geometry": ("node", "Points")},
        parameter_builder=_params_from_ir,
    ),
    "geometry.modify_position": _recipe(
        "geometry.modify_position",
        "GeometryNodeSetPosition",
        inputs=("Geometry", "Position", "Offset", "Selection"),
        outputs=("Geometry",),
        expose_inputs={
            "geometry": ("node", "Geometry"),
            "position": ("node", "Position"),
            "offset": ("node", "Offset"),
            "selection": ("node", "Selection"),
        },
    ),
    "geometry.delete": _recipe(
        "geometry.delete",
        "GeometryNodeDeleteGeometry",
        inputs=("Geometry", "Selection"),
        outputs=("Geometry",),
        expose_inputs={"geometry": ("node", "Geometry"), "selection": ("node", "Selection")},
    ),
    "geometry.primitive": _recipe(
        "geometry.primitive",
        "GeometryNodeMeshCube",
        inputs=(),
        outputs=("Mesh",),
        expose_inputs={},
        expose_outputs={"geometry": ("node", "Mesh")},
        parameter_builder=_primitive_params,
        note="Primitive kind selects the Blender mesh primitive node.",
    ),
    "attribute.read": _recipe(
        "attribute.read",
        "GeometryNodeInputNamedAttribute",
        inputs=(),
        outputs=("Attribute",),
        expose_inputs={},
        expose_outputs={"value": ("node", "Attribute")},
        parameter_builder=_params_from_ir,
    ),
    "attribute.write": _recipe(
        "attribute.write",
        "GeometryNodeStoreNamedAttribute",
        inputs=("Geometry", "Value", "Selection"),
        outputs=("Geometry",),
        expose_inputs={
            "geometry": ("node", "Geometry"),
            "value": ("node", "Value"),
            "selection": ("node", "Selection"),
        },
        parameter_builder=_params_from_ir,
    ),
    "math.clamp": _recipe(
        "math.clamp",
        "ShaderNodeClamp",
        inputs=("Value", "Min", "Max"),
        outputs=("Result",),
        expose_inputs={
            "value": ("node", "Value"),
            "min": ("node", "Min"),
            "max": ("node", "Max"),
            "a": ("node", "Value"),
        },
        expose_outputs={"value": ("node", "Result")},
        parameter_builder=_params_from_ir,
    ),
    "math.map_range": _recipe(
        "math.map_range",
        "ShaderNodeMapRange",
        inputs=("Value", "From Min", "From Max", "To Min", "To Max"),
        outputs=("Result",),
        expose_inputs={
            "value": ("node", "Value"),
            "from_min": ("node", "From Min"),
            "from_max": ("node", "From Max"),
            "to_min": ("node", "To Min"),
            "to_max": ("node", "To Max"),
        },
        expose_outputs={"value": ("node", "Result")},
        parameter_builder=_params_from_ir,
    ),
    "selection.compare": _recipe(
        "selection.compare",
        "FunctionNodeCompare",
        inputs=("A", "B"),
        outputs=("Result",),
        expose_inputs={"a": ("node", "A"), "b": ("node", "B")},
        expose_outputs={"result": ("node", "Result")},
        parameter_builder=_params_from_ir,
    ),
}

for _math_op in (
    "math.add",
    "math.subtract",
    "math.multiply",
    "math.divide",
    "math.power",
    "math.min",
    "math.max",
):
    BLENDER_RECIPES[_math_op] = _recipe(
        _math_op,
        "ShaderNodeMath",
        inputs=("Value", "Value_001"),
        outputs=("Value",),
        expose_inputs={"a": ("node", "Value"), "b": ("node", "Value_001")},
        expose_outputs={"value": ("node", "Value")},
        parameter_builder=_math_params,
    )

for _vec_op, _inputs, _out, _in_map, _out_map in (
    (
        "vector.add",
        ("Vector", "Vector_001"),
        ("Vector",),
        {"a": ("node", "Vector"), "b": ("node", "Vector_001"), "vector": ("node", "Vector")},
        {"vector": ("node", "Vector")},
    ),
    (
        "vector.subtract",
        ("Vector", "Vector_001"),
        ("Vector",),
        {"a": ("node", "Vector"), "b": ("node", "Vector_001")},
        {"vector": ("node", "Vector")},
    ),
    (
        "vector.scale",
        ("Vector", "Scale"),
        ("Vector",),
        {"vector": ("node", "Vector"), "a": ("node", "Vector"), "scale": ("node", "Scale")},
        {"vector": ("node", "Vector")},
    ),
    (
        "vector.normalize",
        ("Vector",),
        ("Vector",),
        {"vector": ("node", "Vector"), "a": ("node", "Vector")},
        {"vector": ("node", "Vector")},
    ),
    (
        "vector.cross",
        ("Vector", "Vector_001"),
        ("Vector",),
        {"a": ("node", "Vector"), "b": ("node", "Vector_001")},
        {"vector": ("node", "Vector")},
    ),
    (
        "vector.dot",
        ("Vector", "Vector_001"),
        ("Value",),
        {"a": ("node", "Vector"), "b": ("node", "Vector_001")},
        {"value": ("node", "Value")},
    ),
    (
        "vector.distance",
        ("Vector", "Vector_001"),
        ("Value",),
        {"a": ("node", "Vector"), "b": ("node", "Vector_001")},
        {"value": ("node", "Value")},
    ),
):
    BLENDER_RECIPES[_vec_op] = _recipe(
        _vec_op,
        "ShaderNodeVectorMath",
        inputs=_inputs,
        outputs=_out,
        expose_inputs=dict(_in_map),
        expose_outputs=dict(_out_map),
        parameter_builder=_vector_params,
    )

BLENDER_RECIPES["random.float"] = _recipe(
    "random.float",
    "FunctionNodeRandomValue",
    inputs=("Min", "Max", "ID", "Seed"),
    outputs=("Value",),
    expose_inputs={
        "min": ("node", "Min"),
        "max": ("node", "Max"),
        "id": ("node", "ID"),
        "seed": ("node", "Seed"),
    },
    expose_outputs={"value": ("node", "Value")},
    parameter_builder=_random_params,
)
BLENDER_RECIPES["random.integer"] = _recipe(
    "random.integer",
    "FunctionNodeRandomValue",
    inputs=("Min", "Max", "ID", "Seed"),
    outputs=("Value",),
    expose_inputs={
        "min": ("node", "Min"),
        "max": ("node", "Max"),
        "id": ("node", "ID"),
        "seed": ("node", "Seed"),
    },
    expose_outputs={"value": ("node", "Value")},
    parameter_builder=_random_params,
)
BLENDER_RECIPES["random.vector"] = _recipe(
    "random.vector",
    "FunctionNodeRandomValue",
    inputs=("Min", "Max", "ID", "Seed"),
    outputs=("Value",),
    expose_inputs={
        "min": ("node", "Min"),
        "max": ("node", "Max"),
        "id": ("node", "ID"),
        "seed": ("node", "Seed"),
    },
    expose_outputs={"vector": ("node", "Value"), "value": ("node", "Value")},
    parameter_builder=_random_params,
)

PRIMITIVE_BACKEND_TYPES = {
    "cube": "GeometryNodeMeshCube",
    "grid": "GeometryNodeMeshGrid",
    "ico_sphere": "GeometryNodeMeshIcoSphere",
    "uv_sphere": "GeometryNodeMeshUVSphere",
    "circle": "GeometryNodeMeshCircle",
    "cone": "GeometryNodeMeshCone",
    "cylinder": "GeometryNodeMeshCylinder",
    "line": "GeometryNodeMeshLine",
}
