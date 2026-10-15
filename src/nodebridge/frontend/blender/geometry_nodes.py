"""Geometry Nodes lowering.

Each Blender node type is a function that builds a semantic operation.
The node type string is stored as source metadata and is not the translation key.
"""

from __future__ import annotations

from nodebridge.frontend.blender.lower import finish, integer, number, text, vector
from nodebridge.ir.graph import GraphNode, NodeTree
from nodebridge.ir.operations import field_port, geometry_port, make_operation, value_port
from nodebridge.ir.semantic import OperationKind
from nodebridge.ir.types import DataType


def register_all(register) -> None:
    for node_type, function in LOWERERS.items():
        register(node_type)(function)


def _scatter(node: GraphNode, tree: NodeTree):
    method = str(node.properties.get("distribute_method", "RANDOM")).upper()
    operation = make_operation(
        id=node.id,
        kind=OperationKind.SCATTER,
        name=node.label or node.name,
        parameters={
            "distribution_mode": "distance" if method == "POISSON" else "density",
            "density": number(node, "Density", 10.0),
            "seed": integer(node, "Seed", 0),
            "distance_min": number(node, "Distance Min", 0.1),
            "density_attribute": "",
            "normal_alignment": True,
        },
        inputs={
            "geometry": geometry_port("geometry", DataType.MESH),
            "selection": field_port("selection", DataType.BOOL),
            "density": field_port("density", DataType.FLOAT),
        },
        outputs={
            "points": geometry_port("points", DataType.POINTS),
            "normal": field_port("normal", DataType.VECTOR3),
            "rotation": field_port("rotation", DataType.VECTOR3),
        },
    )
    return finish(
        node,
        operation,
        {"Mesh": "geometry", "Geometry": "geometry", "Selection": "selection", "Density": "density", "Distance Min": "distance_min", "Seed": "seed"},
        {"Points": "points", "Normal": "normal", "Rotation": "rotation"},
    )


def _primitive(kind: str):
    def lower(node: GraphNode, tree: NodeTree):
        size = vector(node, "Size", (1.0, 1.0, 1.0))
        if kind == "grid":
            size = (number(node, "Size X", 1.0), number(node, "Size Y", 1.0), 0.0)
        operation = make_operation(
            id=node.id,
            kind=OperationKind.PRIMITIVE,
            name=node.label or node.name,
            parameters={
                "primitive": kind,
                "size": size,
                "radius": number(node, "Radius", 1.0),
                "depth": number(node, "Depth", number(node, "Height", 1.0)),
                "vertices": (
                    integer(node, "Vertices X", integer(node, "Vertices", 16)),
                    integer(node, "Vertices Y", integer(node, "Segments", 8)),
                    integer(node, "Vertices Z", integer(node, "Rings", 8)),
                ),
            },
            inputs={"size": value_port("size", DataType.VECTOR3)},
            outputs={"geometry": geometry_port("geometry", DataType.MESH)},
        )
        return finish(
            node,
            operation,
            {"Size": "size", "Size X": "size_x", "Size Y": "size_y", "Radius": "radius", "Depth": "depth", "Vertices": "vertices"},
            {"Mesh": "geometry", "Geometry": "geometry"},
        )

    return lower


def _curve(kind: str):
    def lower(node: GraphNode, tree: NodeTree):
        operation = make_operation(
            id=node.id,
            kind=OperationKind.CURVE,
            name=node.label or node.name,
            parameters={
                "primitive": kind,
                "radius": number(node, "Radius", 1.0),
                "resolution": integer(node, "Resolution", 16),
            },
            outputs={"geometry": geometry_port("geometry", DataType.CURVE)},
        )
        return finish(node, operation, {"Radius": "radius", "Resolution": "resolution"}, {"Curve": "geometry"})

    return lower


def _transform(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.TRANSFORM,
        name=node.label or node.name,
        parameters={
            "translation": vector(node, "Translation"),
            "rotation": vector(node, "Rotation"),
            "scale": vector(node, "Scale", (1.0, 1.0, 1.0)),
            "mode": "geometry",
        },
        inputs={
            "geometry": geometry_port("geometry"),
            "translation": field_port("translation", DataType.VECTOR3),
            "rotation": field_port("rotation", DataType.VECTOR3),
            "scale": field_port("scale", DataType.VECTOR3),
        },
        outputs={"geometry": geometry_port("geometry")},
    )
    return finish(
        node,
        operation,
        {"Geometry": "geometry", "Translation": "translation", "Rotation": "rotation", "Scale": "scale"},
        {"Geometry": "geometry"},
    )


def _instance_transform(mode: str):
    def lower(node: GraphNode, tree: NodeTree):
        operation = make_operation(
            id=node.id,
            kind=OperationKind.TRANSFORM,
            name=node.label or node.name,
            parameters={
                "mode": mode,
                "rotation": vector(node, "Rotation"),
                "scale": vector(node, "Scale", (1.0, 1.0, 1.0)),
                "pivot": vector(node, "Pivot Point"),
            },
            inputs={
                "geometry": geometry_port("geometry", DataType.INSTANCES),
                "selection": field_port("selection", DataType.BOOL),
                "rotation": field_port("rotation", DataType.VECTOR3),
                "scale": field_port("scale", DataType.VECTOR3),
            },
            outputs={"geometry": geometry_port("geometry", DataType.INSTANCES)},
        )
        return finish(
            node,
            operation,
            {"Instances": "geometry", "Selection": "selection", "Rotation": "rotation", "Scale": "scale", "Pivot Point": "pivot"},
            {"Instances": "geometry"},
        )

    return lower


def _set_position(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.TRANSFORM_POINTS,
        name=node.label or node.name,
        parameters={"position": vector(node, "Position"), "offset": vector(node, "Offset")},
        inputs={
            "geometry": geometry_port("geometry"),
            "selection": field_port("selection", DataType.BOOL),
            "position": field_port("position", DataType.VECTOR3),
            "offset": field_port("offset", DataType.VECTOR3),
        },
        outputs={"geometry": geometry_port("geometry")},
    )
    return finish(
        node,
        operation,
        {"Geometry": "geometry", "Selection": "selection", "Position": "position", "Offset": "offset"},
        {"Geometry": "geometry"},
    )


def _attribute(attribute: str, data_type: DataType):
    def lower(node: GraphNode, tree: NodeTree):
        operation = make_operation(
            id=node.id,
            kind=OperationKind.ATTRIBUTE_READ,
            name=node.label or node.name,
            parameters={"attribute": attribute, "data_type": data_type.value},
            outputs={"value": field_port("value", data_type)},
        )
        output_name = {"position": "Position", "normal": "Normal", "index": "Index", "id": "ID"}[attribute]
        return finish(node, operation, {}, {output_name: "value", "Value": "value"})

    return lower


def _math(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.MATH,
        name=node.label or node.name,
        parameters={
            "operation": str(node.properties.get("operation", "ADD")).lower(),
            "a": number(node, "Value", 0.0),
            "b": number(node, "Value_001", 0.0),
            "c": number(node, "Value_002", 0.0),
            "use_clamp": bool(node.properties.get("use_clamp", False)),
        },
        inputs={
            "a": field_port("a", DataType.FLOAT),
            "b": field_port("b", DataType.FLOAT),
            "c": field_port("c", DataType.FLOAT),
        },
        outputs={"value": field_port("value", DataType.FLOAT)},
    )
    return finish(node, operation, {"Value": "a", "Value_001": "b", "Value_002": "c"}, {"Value": "value"})


def _vector_math(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.VECTOR_MATH,
        name=node.label or node.name,
        parameters={
            "operation": str(node.properties.get("operation", "ADD")).lower(),
            "a": vector(node, "Vector"),
            "b": vector(node, "Vector_001"),
            "c": number(node, "Scale", 1.0),
        },
        inputs={
            "a": field_port("a", DataType.VECTOR3),
            "b": field_port("b", DataType.VECTOR3),
            "c": field_port("c", DataType.FLOAT),
        },
        outputs={"vector": field_port("vector", DataType.VECTOR3), "value": field_port("value", DataType.FLOAT)},
    )
    return finish(
        node,
        operation,
        {"Vector": "a", "Vector_001": "b", "Scale": "c"},
        {"Vector": "vector", "Value": "value"},
    )


def _map_range(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.MAP_RANGE,
        name=node.label or node.name,
        parameters={
            "clamp": bool(node.properties.get("clamp", True) or node.properties.get("use_clamp", True)),
            "value": number(node, "Value", 0.0),
            "from_min": number(node, "From Min", 0.0),
            "from_max": number(node, "From Max", 1.0),
            "to_min": number(node, "To Min", 0.0),
            "to_max": number(node, "To Max", 1.0),
        },
        inputs={name: field_port(name, DataType.FLOAT) for name in ("value", "from_min", "from_max", "to_min", "to_max")},
        outputs={"result": field_port("result", DataType.FLOAT)},
    )
    return finish(
        node,
        operation,
        {"Value": "value", "From Min": "from_min", "From Max": "from_max", "To Min": "to_min", "To Max": "to_max"},
        {"Result": "result"},
    )


def _compare(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.COMPARE,
        name=node.label or node.name,
        parameters={
            "operation": str(node.properties.get("operation", "LESS_THAN")).lower(),
            "a": number(node, "A", 0.0),
            "b": number(node, "B", 0.0),
        },
        inputs={"a": field_port("a", DataType.FLOAT), "b": field_port("b", DataType.FLOAT)},
        outputs={"result": field_port("result", DataType.BOOL)},
    )
    return finish(node, operation, {"A": "a", "B": "b", "A_001": "a"}, {"Result": "result"})


def _boolean_math(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.BOOLEAN_MATH,
        name=node.label or node.name,
        parameters={"operation": str(node.properties.get("operation", "AND")).lower(), "a": False, "b": False},
        inputs={"a": field_port("a", DataType.BOOL), "b": field_port("b", DataType.BOOL)},
        outputs={"result": field_port("result", DataType.BOOL)},
    )
    return finish(node, operation, {"Boolean": "a", "Boolean_001": "b"}, {"Boolean": "result"})


def _switch(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.SWITCH,
        name=node.label or node.name,
        parameters={"switch": bool(node.input("Switch").default) if node.input("Switch") and isinstance(node.input("Switch").default, bool) else False},
        inputs={
            "switch": field_port("switch", DataType.BOOL),
            "false": geometry_port("false"),
            "true": geometry_port("true"),
        },
        outputs={"output": geometry_port("output")},
    )
    return finish(node, operation, {"Switch": "switch", "False": "false", "True": "true"}, {"Output": "output"})


def _noise(noise_type: str):
    def lower(node: GraphNode, tree: NodeTree):
        operation = make_operation(
            id=node.id,
            kind=OperationKind.NOISE,
            name=node.label or node.name,
            parameters={
                "noise_type": noise_type,
                "scale": number(node, "Scale", 5.0),
                "detail": number(node, "Detail", 2.0),
                "roughness": number(node, "Roughness", 0.5),
                "distortion": number(node, "Distortion", 0.0),
                "dimensions": str(node.properties.get("noise_dimensions", "3D")),
                "vector": vector(node, "Vector"),
            },
            inputs={
                "vector": field_port("vector", DataType.VECTOR3),
                "scale": field_port("scale", DataType.FLOAT),
                "detail": field_port("detail", DataType.FLOAT),
                "roughness": field_port("roughness", DataType.FLOAT),
                "distortion": field_port("distortion", DataType.FLOAT),
            },
            outputs={"fac": field_port("fac", DataType.FLOAT), "color": field_port("color", DataType.COLOR)},
        )
        return finish(
            node,
            operation,
            {"Vector": "vector", "W": "w", "Scale": "scale", "Detail": "detail", "Roughness": "roughness", "Distortion": "distortion"},
            {"Fac": "fac", "Color": "color", "Distance": "fac"},
        )

    return lower


def _random(node: GraphNode, tree: NodeTree):
    data_type = str(node.properties.get("data_type", "FLOAT")).lower()
    minimum = node.parameter("Min", 0.0)
    maximum = node.parameter("Max", 1.0)
    operation = make_operation(
        id=node.id,
        kind=OperationKind.RANDOM,
        name=node.label or node.name,
        parameters={
            "data_type": data_type,
            "minimum": minimum,
            "maximum": maximum,
            "seed": integer(node, "Seed", 0),
        },
        inputs={
            "minimum": field_port("minimum", DataType.FLOAT),
            "maximum": field_port("maximum", DataType.FLOAT),
            "seed": value_port("seed", DataType.INT),
            "id": field_port("id", DataType.INT),
        },
        outputs={"value": field_port("value", DataType.FLOAT if "vector" not in data_type else DataType.VECTOR3)},
    )
    return finish(node, operation, {"Min": "minimum", "Max": "maximum", "Seed": "seed", "ID": "id"}, {"Value": "value"})


def _instance(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.INSTANCE,
        name=node.label or node.name,
        parameters={
            "scale": vector(node, "Scale", (1.0, 1.0, 1.0)),
            "rotation": vector(node, "Rotation"),
            "pick_instance": bool(node.parameter("Pick Instance", False)),
        },
        inputs={
            "points": geometry_port("points", DataType.POINTS),
            "instance": geometry_port("instance"),
            "selection": field_port("selection", DataType.BOOL),
            "rotation": field_port("rotation", DataType.VECTOR3),
            "scale": field_port("scale", DataType.VECTOR3),
        },
        outputs={"instances": geometry_port("instances", DataType.INSTANCES)},
    )
    return finish(
        node,
        operation,
        {"Points": "points", "Instance": "instance", "Selection": "selection", "Rotation": "rotation", "Scale": "scale"},
        {"Instances": "instances"},
    )


def _passthrough(kind: OperationKind, data_type: DataType = DataType.GEOMETRY):
    def lower(node: GraphNode, tree: NodeTree):
        operation = make_operation(
            id=node.id,
            kind=kind,
            name=node.label or node.name,
            inputs={"geometry": geometry_port("geometry", data_type)},
            outputs={"geometry": geometry_port("geometry", data_type)},
        )
        return finish(node, operation, {"Geometry": "geometry", "Instances": "geometry", "Curve": "geometry", "Mesh": "geometry"}, {"Geometry": "geometry", "Instances": "geometry", "Curve": "geometry", "Mesh": "geometry"})

    return lower


def _merge(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.MERGE,
        name=node.label or node.name,
        outputs={"geometry": geometry_port("geometry")},
    )
    return finish(node, operation, {}, {"Geometry": "geometry"})


def _material(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.MATERIAL_ASSIGNMENT,
        name=node.label or node.name,
        parameters={"material": text(node, "Material", "")},
        inputs={"geometry": geometry_port("geometry"), "selection": field_port("selection", DataType.BOOL), "material": value_port("material", DataType.MATERIAL)},
        outputs={"geometry": geometry_port("geometry")},
    )
    return finish(node, operation, {"Geometry": "geometry", "Selection": "selection", "Material": "material"}, {"Geometry": "geometry"})


def _extrude(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.EXTRUDE,
        name=node.label or node.name,
        parameters={
            "mode": str(node.properties.get("mode", "FACES")).lower(),
            "offset_scale": number(node, "Offset Scale", 1.0),
            "offset": vector(node, "Offset", (0.0, 0.0, 1.0)),
            "individual": bool(node.properties.get("individual", False) if "individual" in node.properties else False),
        },
        inputs={"geometry": geometry_port("geometry", DataType.MESH), "selection": field_port("selection", DataType.BOOL)},
        outputs={"geometry": geometry_port("geometry", DataType.MESH)},
    )
    return finish(node, operation, {"Mesh": "geometry", "Selection": "selection", "Offset": "offset", "Offset Scale": "offset_scale"}, {"Mesh": "geometry"})


def _subdivide(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.SUBDIVIDE,
        name=node.label or node.name,
        parameters={"level": integer(node, "Level", 1)},
        inputs={"geometry": geometry_port("geometry", DataType.MESH)},
        outputs={"geometry": geometry_port("geometry", DataType.MESH)},
    )
    return finish(node, operation, {"Mesh": "geometry", "Level": "level"}, {"Mesh": "geometry"})


def _delete(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.DELETE_GEOMETRY,
        name=node.label or node.name,
        parameters={"domain": str(node.properties.get("domain", "FACE")).lower(), "mode": str(node.properties.get("mode", "ALL")).lower()},
        inputs={"geometry": geometry_port("geometry"), "selection": field_port("selection", DataType.BOOL)},
        outputs={"geometry": geometry_port("geometry")},
    )
    return finish(node, operation, {"Geometry": "geometry", "Selection": "selection"}, {"Geometry": "geometry"})


def _separate(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.SEPARATE,
        name=node.label or node.name,
        parameters={"domain": str(node.properties.get("domain", "POINT")).lower()},
        inputs={"geometry": geometry_port("geometry"), "selection": field_port("selection", DataType.BOOL)},
        outputs={"selected": geometry_port("selected"), "inverted": geometry_port("inverted")},
    )
    return finish(node, operation, {"Geometry": "geometry", "Selection": "selection"}, {"Selection": "selected", "Inverted": "inverted"})


def _resample(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.CURVE_RESAMPLE,
        name=node.label or node.name,
        parameters={"mode": str(node.properties.get("mode", "LENGTH")).lower(), "length": number(node, "Length", 0.1), "count": integer(node, "Count", 16)},
        inputs={"geometry": geometry_port("geometry", DataType.CURVE)},
        outputs={"geometry": geometry_port("geometry", DataType.CURVE)},
    )
    return finish(node, operation, {"Curve": "geometry", "Length": "length", "Count": "count"}, {"Curve": "geometry"})


def _curve_to_mesh(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.CURVE_TO_MESH,
        name=node.label or node.name,
        parameters={"radius": number(node, "Scale", 1.0)},
        inputs={"curve": geometry_port("curve", DataType.CURVE), "profile": geometry_port("profile", DataType.CURVE)},
        outputs={"geometry": geometry_port("geometry", DataType.MESH)},
    )
    return finish(node, operation, {"Curve": "curve", "Profile Curve": "profile"}, {"Mesh": "geometry"})


def _proximity(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.PROXIMITY,
        name=node.label or node.name,
        parameters={"target_element": str(node.properties.get("target_element", "FACES")).lower()},
        inputs={"source": geometry_port("source"), "target": geometry_port("target")},
        outputs={"distance": field_port("distance", DataType.FLOAT), "position": field_port("position", DataType.VECTOR3)},
    )
    return finish(node, operation, {"Source Position": "source_position", "Target": "target"}, {"Distance": "distance", "Position": "position"})


def _raycast(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.RAYCAST,
        name=node.label or node.name,
        parameters={"ray_direction": vector(node, "Ray Direction", (0.0, 0.0, -1.0)), "ray_length": number(node, "Ray Length", 100.0)},
        inputs={"geometry": geometry_port("geometry"), "target": geometry_port("target")},
        outputs={"is_hit": field_port("is_hit", DataType.BOOL), "hit_position": field_port("hit_position", DataType.VECTOR3), "hit_normal": field_port("hit_normal", DataType.VECTOR3)},
    )
    return finish(
        node,
        operation,
        {"Target Geometry": "target", "Attribute": "attribute", "Source Position": "source_position", "Ray Direction": "ray_direction", "Ray Length": "ray_length"},
        {"Is Hit": "is_hit", "Hit Position": "hit_position", "Hit Normal": "hit_normal"},
    )


def _boolean(node: GraphNode, tree: NodeTree):
    operation = make_operation(
        id=node.id,
        kind=OperationKind.BOOLEAN,
        name=node.label or node.name,
        parameters={"operation": str(node.properties.get("operation", "DIFFERENCE")).lower()},
        inputs={"a": geometry_port("a", DataType.MESH), "b": geometry_port("b", DataType.MESH)},
        outputs={"geometry": geometry_port("geometry", DataType.MESH)},
    )
    return finish(node, operation, {"Mesh 1": "a", "Mesh 2": "b", "Mesh": "a"}, {"Mesh": "geometry"})


def _group_input(node: GraphNode, tree: NodeTree):
    from nodebridge.ir.semantic import Operation

    outputs = {}
    names = {}
    defaults = {}
    labels = {}
    interface_defaults = {item.identifier: item.default for item in tree.interface}
    interface_names = {item.identifier: item.name for item in tree.interface}
    for socket in node.outputs:
        if not socket.identifier:
            continue
        port_type = socket.data_type
        role_port = geometry_port(socket.identifier, port_type) if port_type in {DataType.GEOMETRY, DataType.MESH, DataType.CURVE, DataType.POINTS, DataType.INSTANCES} else field_port(socket.identifier, port_type)
        outputs[socket.identifier] = role_port
        names[socket.identifier] = socket.identifier
        defaults[socket.identifier] = interface_defaults.get(socket.identifier, socket.default)
        labels[socket.identifier] = interface_names.get(socket.identifier, socket.name)
    operation = Operation(
        id=node.id,
        kind=OperationKind.GROUP_INPUT,
        name=node.label or node.name or "Group Input",
        parameters={"defaults": defaults, "labels": labels},
        outputs=outputs,
    )
    return finish(node, operation, {}, names)


def _group_output(node: GraphNode, tree: NodeTree):
    from nodebridge.ir.semantic import Operation

    inputs = {}
    names = {}
    for socket in node.inputs:
        if not socket.identifier:
            continue
        port_type = socket.data_type
        inputs[socket.identifier] = geometry_port(socket.identifier, port_type) if port_type in {DataType.GEOMETRY, DataType.MESH, DataType.CURVE, DataType.POINTS, DataType.INSTANCES} else field_port(socket.identifier, port_type)
        names[socket.identifier] = socket.identifier
    operation = Operation(id=node.id, kind=OperationKind.GROUP_OUTPUT, name=node.label or node.name or "Group Output", inputs=inputs)
    return finish(node, operation, names, {})


LOWERERS = {
    "NodeGroupInput": _group_input,
    "NodeGroupOutput": _group_output,
    "GeometryNodeJoinGeometry": _merge,
    "GeometryNodeTransform": _transform,
    "GeometryNodeSetPosition": _set_position,
    "GeometryNodeInputPosition": _attribute("position", DataType.VECTOR3),
    "GeometryNodeInputNormal": _attribute("normal", DataType.VECTOR3),
    "GeometryNodeInputIndex": _attribute("index", DataType.INT),
    "GeometryNodeInputID": _attribute("id", DataType.INT),
    "ShaderNodeMath": _math,
    "ShaderNodeVectorMath": _vector_math,
    "ShaderNodeMapRange": _map_range,
    "FunctionNodeCompare": _compare,
    "FunctionNodeBooleanMath": _boolean_math,
    "GeometryNodeSwitch": _switch,
    "ShaderNodeTexNoise": _noise("noise"),
    "ShaderNodeTexVoronoi": _noise("voronoi"),
    "FunctionNodeRandomValue": _random,
    "GeometryNodeDistributePointsOnFaces": _scatter,
    "GeometryNodeInstanceOnPoints": _instance,
    "GeometryNodeRealizeInstances": _passthrough(OperationKind.REALIZE_INSTANCES, DataType.INSTANCES),
    "GeometryNodeRotateInstances": _instance_transform("instance_rotation"),
    "GeometryNodeScaleInstances": _instance_transform("instance_scale"),
    "GeometryNodeSetMaterial": _material,
    "GeometryNodeMeshCube": _primitive("cube"),
    "GeometryNodeMeshGrid": _primitive("grid"),
    "GeometryNodeMeshUVSphere": _primitive("uv_sphere"),
    "GeometryNodeMeshIcoSphere": _primitive("ico_sphere"),
    "GeometryNodeMeshCylinder": _primitive("cylinder"),
    "GeometryNodeMeshCone": _primitive("cone"),
    "GeometryNodeMeshCircle": _primitive("circle"),
    "GeometryNodeMeshLine": _primitive("line"),
    "GeometryNodeCurvePrimitiveCircle": _curve("circle"),
    "GeometryNodeCurvePrimitiveLine": _curve("line"),
    "GeometryNodeCurvePrimitiveQuadrilateral": _curve("quadrilateral"),
    "GeometryNodeCurvePrimitiveBezierSegment": _curve("bezier"),
    "GeometryNodeCurveStar": _curve("star"),
    "GeometryNodeCurveSpiral": _curve("spiral"),
    "GeometryNodeCurveArc": _curve("arc"),
    "GeometryNodeCurveToMesh": _curve_to_mesh,
    "GeometryNodeMeshToCurve": _passthrough(OperationKind.MESH_TO_CURVE, DataType.MESH),
    "GeometryNodeResampleCurve": _resample,
    "GeometryNodeExtrudeMesh": _extrude,
    "GeometryNodeSubdivideMesh": _subdivide,
    "GeometryNodeDeleteGeometry": _delete,
    "GeometryNodeSeparateGeometry": _separate,
    "GeometryNodeProximity": _proximity,
    "GeometryNodeRaycast": _raycast,
    "GeometryNodeMeshBoolean": _boolean,
}
