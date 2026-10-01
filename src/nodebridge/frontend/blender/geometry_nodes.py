"""Geometry Nodes lifters: Blender node syntax -> semantic operations.

Socket names below were verified against Blender 4.2 LTS and 4.5 LTS.
Lookups use socket *names* with a preference for enabled sockets, so
nodes with per-data-type socket variants (Random Value, Compare, Map
Range) resolve to the socket Blender actually uses.
"""

from __future__ import annotations

from ...ir.graph import GraphNode, TreeKind
from ...ir.semantic import Const
from ...ir.types import DataType
from .lifting import LiftContext, LiftError, lifts

GN = (TreeKind.GEOMETRY,)
ANY_KIND = (TreeKind.GEOMETRY, TreeKind.SHADER, TreeKind.COMPOSITOR)


# --- constants and built-in fields --------------------------------------
@lifts("ShaderNodeValue", kinds=(TreeKind.GEOMETRY, TreeKind.COMPOSITOR))
def _value(ctx: LiftContext, node: GraphNode) -> None:
    ctx.bind(node, "Value", Const(node.outputs[0].default if node.outputs else 0.0, DataType.FLOAT))


@lifts("FunctionNodeInputVector", kinds=GN)
def _vector(ctx: LiftContext, node: GraphNode) -> None:
    ctx.bind(node, "Vector", Const(ctx.prop(node, "vector", [0.0, 0.0, 0.0]), DataType.VECTOR3))


@lifts("FunctionNodeInputInt", kinds=GN)
def _int(ctx: LiftContext, node: GraphNode) -> None:
    ctx.bind(node, "Integer", Const(ctx.prop(node, "integer", 0), DataType.INT))


@lifts("FunctionNodeInputBool", kinds=GN)
def _bool(ctx: LiftContext, node: GraphNode) -> None:
    ctx.bind(node, "Boolean", Const(ctx.prop(node, "boolean", False), DataType.BOOL))


@lifts("FunctionNodeInputColor", kinds=GN)
def _color(ctx: LiftContext, node: GraphNode) -> None:
    ctx.bind(node, "Color", Const(ctx.prop(node, "value", [1.0, 1.0, 1.0, 1.0]), DataType.COLOR))


@lifts("FunctionNodeInputString", kinds=GN)
def _string(ctx: LiftContext, node: GraphNode) -> None:
    ctx.bind(node, "String", Const(ctx.prop(node, "string", ""), DataType.STRING))


_FIELDS = {
    "GeometryNodeInputPosition": ("position", "Position", DataType.VECTOR3),
    "GeometryNodeInputNormal": ("normal", "Normal", DataType.VECTOR3),
    "GeometryNodeInputIndex": ("index", "Index", DataType.INT),
    "GeometryNodeInputID": ("id", "ID", DataType.INT),
}


@lifts(*_FIELDS, kinds=GN)
def _field_input(ctx: LiftContext, node: GraphNode) -> None:
    field, socket, data_type = _FIELDS[node.type]
    ctx.emit("FIELD_INPUT", node, params={"field": field}, outputs={"value": socket}, output_types={"value": data_type})


# --- math / logic (shared by all tree kinds) ----------------------------
@lifts("ShaderNodeMath", "CompositorNodeMath", kinds=ANY_KIND)
def _math(ctx: LiftContext, node: GraphNode) -> None:
    inputs = [s for s in node.inputs if s.enabled]
    values = {key: _input_by_identifier(ctx, node, s.identifier) for key, s in zip("abc", inputs)}
    ctx.emit("MATH", node, values, {"operation": ctx.prop(node, "operation", "ADD"), "clamp": bool(ctx.prop(node, "use_clamp", False))}, {"value": "Value"})


def _input_by_identifier(ctx: LiftContext, node: GraphNode, identifier: str):
    edges = ctx.edges_into(node, identifier)
    if edges:
        return ctx._resolve(edges[0])
    socket = node.input(identifier)
    return Const(socket.default, socket.data_type) if socket is not None else None


@lifts("ShaderNodeVectorMath", kinds=ANY_KIND)
def _vector_math(ctx: LiftContext, node: GraphNode) -> None:
    sockets = {s.identifier: s for s in node.inputs if s.enabled}
    values = {}
    for key, identifier in (("a", "Vector"), ("b", "Vector_001"), ("c", "Vector_002"), ("scale", "Scale")):
        if identifier in sockets:
            values[key] = _input_by_identifier(ctx, node, identifier)
    ctx.emit("VECTOR_MATH", node, values, {"operation": ctx.prop(node, "operation", "ADD")}, {"vector": "Vector", "value": "Value"}, output_types={"vector": DataType.VECTOR3, "value": DataType.FLOAT})


@lifts("ShaderNodeClamp", kinds=ANY_KIND)
def _clamp(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit(
        "MATH",
        node,
        {"a": ctx.input(node, "Value"), "b": ctx.input(node, "Min"), "c": ctx.input(node, "Max")},
        {"operation": "CLAMP_RANGE" if ctx.prop(node, "clamp_type") == "RANGE" else "CLAMP_MINMAX"},
        {"value": "Result"},
    )


@lifts("FunctionNodeFloatToInt", kinds=GN)
def _float_to_int(ctx: LiftContext, node: GraphNode) -> None:
    mode = {"ROUND": "ROUND", "FLOOR": "FLOOR", "CEILING": "CEIL", "TRUNCATE": "TRUNC"}[ctx.prop(node, "rounding_mode", "ROUND")]
    ctx.emit("MATH", node, {"a": ctx.input(node, "Float")}, {"operation": mode}, {"value": "Integer"}, output_types={"value": DataType.INT})


@lifts("ShaderNodeMapRange", kinds=ANY_KIND)
def _map_range(ctx: LiftContext, node: GraphNode) -> None:
    vector = ctx.prop(node, "data_type", "FLOAT") == "FLOAT_VECTOR"
    first = "Vector" if vector else "Value"
    inputs = {"value": ctx.input(node, first)}
    for key, name in (("from_min", "From Min"), ("from_max", "From Max"), ("to_min", "To Min"), ("to_max", "To Max"), ("steps", "Steps")):
        inputs[key] = ctx.input(node, name)
    out = "Vector" if vector else "Result"
    ctx.emit(
        "MAP_RANGE",
        node,
        inputs,
        {"interpolation": ctx.prop(node, "interpolation_type", "LINEAR"), "clamp": bool(ctx.prop(node, "clamp", True)), "data_type": ctx.prop(node, "data_type", "FLOAT")},
        {"result": out},
        output_types={"result": DataType.VECTOR3 if vector else DataType.FLOAT},
    )


@lifts("FunctionNodeCompare", kinds=GN)
def _compare(ctx: LiftContext, node: GraphNode) -> None:
    inputs = {"a": ctx.input(node, "A"), "b": ctx.input(node, "B")}
    for key, name in (("c", "C"), ("angle", "Angle"), ("epsilon", "Epsilon")):
        socket = node.find_input(name)
        if socket is not None and socket.enabled:
            inputs[key] = ctx.input(node, name)
    ctx.emit(
        "COMPARE",
        node,
        inputs,
        {"operation": ctx.prop(node, "operation", "GREATER_THAN"), "data_type": ctx.prop(node, "data_type", "FLOAT"), "mode": ctx.prop(node, "mode", "ELEMENT")},
        {"result": "Result"},
        output_types={"result": DataType.BOOL},
    )


@lifts("FunctionNodeBooleanMath", kinds=GN)
def _boolean_math(ctx: LiftContext, node: GraphNode) -> None:
    sockets = [s for s in node.inputs if s.enabled]
    values = {key: _input_by_identifier(ctx, node, s.identifier) for key, s in zip("ab", sockets)}
    ctx.emit("BOOLEAN_MATH", node, values, {"operation": ctx.prop(node, "operation", "AND")}, {"value": "Boolean"}, output_types={"value": DataType.BOOL})


@lifts("ShaderNodeCombineXYZ", kinds=ANY_KIND)
def _combine(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit("COMBINE_VECTOR", node, {k: ctx.input(node, k.upper()) for k in "xyz"}, outputs={"vector": "Vector"})


@lifts("ShaderNodeSeparateXYZ", kinds=ANY_KIND)
def _separate(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit("SEPARATE_VECTOR", node, {"vector": ctx.input(node, "Vector")}, outputs={k: k.upper() for k in "xyz"})


@lifts("ShaderNodeMix", kinds=ANY_KIND)
def _mix(ctx: LiftContext, node: GraphNode) -> None:
    data_type = ctx.prop(node, "data_type", "FLOAT")
    suffix = {"FLOAT": "Float", "VECTOR": "Vector", "RGBA": "Color", "ROTATION": "Rotation"}.get(data_type, "Float")
    factor_id = "Factor_Vector" if data_type == "VECTOR" and ctx.prop(node, "factor_mode") == "NON_UNIFORM" else "Factor_Float"
    ctx.emit(
        "MIX",
        node,
        {"factor": _input_by_identifier(ctx, node, factor_id), "a": _input_by_identifier(ctx, node, f"A_{suffix}"), "b": _input_by_identifier(ctx, node, f"B_{suffix}")},
        {
            "data_type": data_type,
            "blend_type": ctx.prop(node, "blend_type", "MIX"),
            "clamp_factor": bool(ctx.prop(node, "clamp_factor", True)),
            "clamp_result": bool(ctx.prop(node, "clamp_result", False)),
        },
        {"result": "Result"},
        output_types={"result": {"FLOAT": DataType.FLOAT, "VECTOR": DataType.VECTOR3, "RGBA": DataType.COLOR}.get(data_type, DataType.FLOAT)},
    )


@lifts("ShaderNodeValToRGB", kinds=ANY_KIND)
def _color_ramp(ctx: LiftContext, node: GraphNode) -> None:
    ramp = ctx.prop(node, "color_ramp", {}) or {}
    ctx.emit(
        "COLOR_RAMP",
        node,
        {"fac": ctx.input(node, "Fac")},
        {"stops": ramp.get("elements", []), "interpolation": ramp.get("interpolation", "LINEAR"), "color_mode": ramp.get("color_mode", "RGB")},
        {"color": "Color", "alpha": "Alpha"},
    )


@lifts("FunctionNodeRandomValue", kinds=GN)
def _random(ctx: LiftContext, node: GraphNode) -> None:
    data_type = ctx.prop(node, "data_type", "FLOAT")
    inputs = {"id": ctx.input(node, "ID", implicit="id"), "seed": ctx.input(node, "Seed")}
    if data_type == "BOOLEAN":
        inputs["probability"] = ctx.input(node, "Probability")
    else:
        inputs["min"] = ctx.input(node, "Min")
        inputs["max"] = ctx.input(node, "Max")
    out_type = {"FLOAT": DataType.FLOAT, "INT": DataType.INT, "FLOAT_VECTOR": DataType.VECTOR3, "BOOLEAN": DataType.BOOL}[data_type]
    ctx.emit("RANDOM", node, inputs, {"data_type": data_type}, {"value": "Value"}, output_types={"value": out_type})


@lifts("GeometryNodeSwitch", kinds=GN)
def _switch(ctx: LiftContext, node: GraphNode) -> None:
    input_type = ctx.prop(node, "input_type", "GEOMETRY")
    if input_type == "MENU":
        raise LiftError("Menu Switch is not lifted yet.")
    out_socket = node.find_output("Output")
    ctx.emit(
        "SWITCH",
        node,
        {"switch": ctx.input(node, "Switch"), "false": ctx.input(node, "False"), "true": ctx.input(node, "True")},
        {"input_type": input_type},
        {"output": "Output"},
        output_types={"output": out_socket.data_type if out_socket else DataType.ANY},
    )


@lifts("ShaderNodeTexNoise", kinds=(TreeKind.GEOMETRY, TreeKind.SHADER))
def _noise(ctx: LiftContext, node: GraphNode) -> None:
    implicit = "position" if ctx.kind == TreeKind.GEOMETRY else "generated"
    inputs = {"vector": ctx.input(node, "Vector", implicit=implicit)}
    for key, name in (("w", "W"), ("scale", "Scale"), ("detail", "Detail"), ("roughness", "Roughness"), ("lacunarity", "Lacunarity"), ("distortion", "Distortion")):
        socket = node.find_input(name)
        if socket is not None and socket.enabled:
            inputs[key] = ctx.input(node, name)
    ctx.emit(
        "NOISE",
        node,
        inputs,
        {"dimensions": ctx.prop(node, "noise_dimensions", "3D"), "noise_type": ctx.prop(node, "noise_type", "FBM"), "normalize": bool(ctx.prop(node, "normalize", True))},
        {"fac": "Fac", "color": "Color"},
    )


@lifts("ShaderNodeTexVoronoi", kinds=(TreeKind.GEOMETRY, TreeKind.SHADER))
def _voronoi(ctx: LiftContext, node: GraphNode) -> None:
    implicit = "position" if ctx.kind == TreeKind.GEOMETRY else "generated"
    inputs = {"vector": ctx.input(node, "Vector", implicit=implicit), "scale": ctx.input(node, "Scale"), "randomness": ctx.input(node, "Randomness")}
    if node.find_input("Detail") is not None:
        inputs["detail"] = ctx.input(node, "Detail")
    ctx.emit(
        "VORONOI",
        node,
        inputs,
        {"dimensions": ctx.prop(node, "voronoi_dimensions", "3D"), "feature": ctx.prop(node, "feature", "F1"), "distance": ctx.prop(node, "distance", "EUCLIDEAN")},
        {"distance": "Distance", "color": "Color", "position": "Position"},
    )


# --- geometry ------------------------------------------------------------
@lifts("GeometryNodeJoinGeometry", kinds=GN)
def _join(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit("MERGE", node, {"geometry": ctx.multi_input(node, "Geometry")}, outputs={"geometry": "Geometry"})


@lifts("GeometryNodeTransform", kinds=GN)
def _transform(ctx: LiftContext, node: GraphNode) -> None:
    if ctx.prop(node, "mode", "COMPONENTS") != "COMPONENTS":
        raise LiftError("Transform Geometry in Matrix mode is not lifted yet.")
    ctx.emit(
        "TRANSFORM",
        node,
        {"geometry": ctx.input(node, "Geometry"), "translation": ctx.input(node, "Translation"), "rotation": ctx.input(node, "Rotation"), "scale": ctx.input(node, "Scale")},
        outputs={"geometry": "Geometry"},
    )


@lifts("GeometryNodeSetPosition", kinds=GN)
def _set_position(ctx: LiftContext, node: GraphNode) -> None:
    inputs = {"geometry": ctx.input(node, "Geometry"), "selection": ctx.input(node, "Selection"), "offset": ctx.input(node, "Offset")}
    if ctx.has_link(node, "Position"):
        inputs["position"] = ctx.input(node, "Position")
    ctx.emit("SET_POSITION", node, inputs, outputs={"geometry": "Geometry"})


_PRIMITIVES = {
    "GeometryNodeMeshCube": ("cube", {"size": "Size", "vertices_x": "Vertices X", "vertices_y": "Vertices Y", "vertices_z": "Vertices Z"}),
    "GeometryNodeMeshGrid": ("grid", {"size_x": "Size X", "size_y": "Size Y", "vertices_x": "Vertices X", "vertices_y": "Vertices Y"}),
    "GeometryNodeMeshUVSphere": ("uv_sphere", {"segments": "Segments", "rings": "Rings", "radius": "Radius"}),
    "GeometryNodeMeshIcoSphere": ("ico_sphere", {"radius": "Radius", "subdivisions": "Subdivisions"}),
    "GeometryNodeMeshCylinder": ("cylinder", {"vertices": "Vertices", "side_segments": "Side Segments", "fill_segments": "Fill Segments", "radius": "Radius", "depth": "Depth"}),
    "GeometryNodeMeshCone": (
        "cone",
        {"vertices": "Vertices", "side_segments": "Side Segments", "fill_segments": "Fill Segments", "radius_top": "Radius Top", "radius_bottom": "Radius Bottom", "depth": "Depth"},
    ),
    "GeometryNodeMeshLine": ("line", {"count": "Count", "start": "Start Location", "offset": "Offset"}),
    "GeometryNodeMeshCircle": ("circle", {"vertices": "Vertices", "radius": "Radius"}),
}


@lifts(*_PRIMITIVES, kinds=GN)
def _primitive(ctx: LiftContext, node: GraphNode) -> None:
    shape, sockets = _PRIMITIVES[node.type]
    params = {"shape": shape}
    if "fill_type" in node.parameters:
        params["fill_type"] = node.parameters["fill_type"]
    if shape == "line":
        params["mode"] = ctx.prop(node, "mode", "OFFSET")
        if params["mode"] != "OFFSET" or ctx.prop(node, "count_mode", "TOTAL") != "TOTAL":
            raise LiftError("Mesh Line is lifted only in Offset / Total count mode.")
    ctx.emit("PRIMITIVE", node, {key: ctx.input(node, name) for key, name in sockets.items()}, params, {"geometry": "Mesh", "uv": "UV Map"})


@lifts("GeometryNodeCurvePrimitiveLine", kinds=GN)
def _curve_line(ctx: LiftContext, node: GraphNode) -> None:
    if ctx.prop(node, "mode", "POINTS") != "POINTS":
        raise LiftError("Curve Line is lifted only in Points mode.")
    ctx.emit("CURVE", node, {"start": ctx.input(node, "Start"), "end": ctx.input(node, "End")}, {"shape": "line"}, {"geometry": "Curve"})


@lifts("GeometryNodeCurvePrimitiveCircle", kinds=GN)
def _curve_circle(ctx: LiftContext, node: GraphNode) -> None:
    if ctx.prop(node, "mode", "RADIUS") != "RADIUS":
        raise LiftError("Curve Circle is lifted only in Radius mode.")
    ctx.emit("CURVE", node, {"resolution": ctx.input(node, "Resolution"), "radius": ctx.input(node, "Radius")}, {"shape": "circle"}, {"geometry": "Curve"})


@lifts("GeometryNodeCurveSpiral", kinds=GN)
def _curve_spiral(ctx: LiftContext, node: GraphNode) -> None:
    keys = {"resolution": "Resolution", "rotations": "Rotations", "start_radius": "Start Radius", "end_radius": "End Radius", "height": "Height"}
    ctx.emit("CURVE", node, {k: ctx.input(node, n) for k, n in keys.items()}, {"shape": "spiral", "reverse": bool(ctx.prop(node, "reverse", False))}, {"geometry": "Curve"})


@lifts("GeometryNodeDistributePointsOnFaces", kinds=GN)
def _distribute(ctx: LiftContext, node: GraphNode) -> None:
    method = ctx.prop(node, "distribute_method", "RANDOM")
    inputs = {"geometry": ctx.input(node, "Mesh"), "selection": ctx.input(node, "Selection"), "seed": ctx.input(node, "Seed")}
    if method == "RANDOM":
        inputs["density"] = ctx.input(node, "Density")
    else:
        inputs["distance_min"] = ctx.input(node, "Distance Min")
        inputs["density_max"] = ctx.input(node, "Density Max")
        inputs["density_factor"] = ctx.input(node, "Density Factor")
    ctx.emit(
        "SCATTER",
        node,
        inputs,
        {"distribution_mode": "random" if method == "RANDOM" else "poisson", "normal_alignment": False},
        {"points": "Points", "normal": "Normal", "rotation": "Rotation"},
        output_types={"points": DataType.POINTS, "normal": DataType.VECTOR3, "rotation": DataType.ROTATION},
    )


@lifts("GeometryNodeInstanceOnPoints", kinds=GN)
def _instance(ctx: LiftContext, node: GraphNode) -> None:
    names = {"points": "Points", "selection": "Selection", "instance": "Instance", "pick_instance": "Pick Instance", "instance_index": "Instance Index", "rotation": "Rotation", "scale": "Scale"}
    inputs = {key: ctx.input(node, name) for key, name in names.items()}
    if not ctx.has_link(node, "Instance Index") and inputs.get("pick_instance") == Const(False, DataType.BOOL):
        inputs.pop("instance_index", None)
    ctx.emit("INSTANCE", node, inputs, outputs={"instances": "Instances"}, output_types={"instances": DataType.INSTANCES})


@lifts("GeometryNodeRealizeInstances", kinds=GN)
def _realize(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit("REALIZE_INSTANCES", node, {"geometry": ctx.input(node, "Geometry")}, outputs={"geometry": "Geometry"})


@lifts("GeometryNodeRotateInstances", "GeometryNodeScaleInstances", "GeometryNodeTranslateInstances", kinds=GN)
def _instance_transform(ctx: LiftContext, node: GraphNode) -> None:
    mode = {"GeometryNodeRotateInstances": "rotate", "GeometryNodeScaleInstances": "scale", "GeometryNodeTranslateInstances": "translate"}[node.type]
    inputs = {"geometry": ctx.input(node, "Instances"), "selection": ctx.input(node, "Selection"), "local_space": ctx.input(node, "Local Space")}
    if mode == "rotate":
        inputs.update(rotation=ctx.input(node, "Rotation"), pivot=ctx.input(node, "Pivot Point"))
    elif mode == "scale":
        inputs.update(scale=ctx.input(node, "Scale"), pivot=ctx.input(node, "Center"))
    else:
        inputs.update(translation=ctx.input(node, "Translation"))
    ctx.emit("INSTANCE_TRANSFORM", node, inputs, {"mode": mode}, {"geometry": "Instances"}, output_types={"geometry": DataType.INSTANCES})


@lifts("GeometryNodeSetMaterial", kinds=GN)
def _set_material(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit(
        "MATERIAL_ASSIGNMENT",
        node,
        {"geometry": ctx.input(node, "Geometry"), "selection": ctx.input(node, "Selection"), "material": ctx.input(node, "Material")},
        outputs={"geometry": "Geometry"},
    )


@lifts("GeometryNodeExtrudeMesh", kinds=GN)
def _extrude(ctx: LiftContext, node: GraphNode) -> None:
    inputs = {
        "geometry": ctx.input(node, "Mesh"),
        "selection": ctx.input(node, "Selection"),
        "offset_scale": ctx.input(node, "Offset Scale"),
    }
    if ctx.has_link(node, "Offset"):
        inputs["offset"] = ctx.input(node, "Offset")
    individual = node.find_input("Individual")
    if individual is not None and individual.enabled:
        inputs["individual"] = ctx.input(node, "Individual")
    ctx.emit("EXTRUDE", node, inputs, {"mode": ctx.prop(node, "mode", "FACES")}, {"geometry": "Mesh", "top": "Top", "side": "Side"}, output_types={"top": DataType.BOOL, "side": DataType.BOOL})


@lifts("GeometryNodeSubdivideMesh", "GeometryNodeSubdivisionSurface", kinds=GN)
def _subdivide(ctx: LiftContext, node: GraphNode) -> None:
    method = "simple" if node.type == "GeometryNodeSubdivideMesh" else "catmull_clark"
    ctx.emit("SUBDIVIDE", node, {"geometry": ctx.input(node, "Mesh"), "level": ctx.input(node, "Level")}, {"method": method}, {"geometry": "Mesh"})


@lifts("GeometryNodeDeleteGeometry", kinds=GN)
def _delete(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit(
        "DELETE_GEOMETRY",
        node,
        {"geometry": ctx.input(node, "Geometry"), "selection": ctx.input(node, "Selection")},
        {"domain": ctx.prop(node, "domain", "POINT"), "mode": ctx.prop(node, "mode", "ALL")},
        {"geometry": "Geometry"},
    )


@lifts("GeometryNodeSeparateGeometry", kinds=GN)
def _separate_geometry(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit(
        "SEPARATE",
        node,
        {"geometry": ctx.input(node, "Geometry"), "selection": ctx.input(node, "Selection")},
        {"domain": ctx.prop(node, "domain", "POINT")},
        {"selection": "Selection", "inverted": "Inverted"},
    )


@lifts("GeometryNodeProximity", kinds=GN)
def _proximity(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit(
        "PROXIMITY",
        node,
        {"target": ctx.input(node, "Target"), "source_position": ctx.input(node, "Source Position", implicit="position")},
        {"target_element": ctx.prop(node, "target_element", "FACES")},
        {"position": "Position", "distance": "Distance", "is_valid": "Is Valid"},
        output_types={"position": DataType.VECTOR3, "distance": DataType.FLOAT, "is_valid": DataType.BOOL},
    )


@lifts("GeometryNodeRaycast", kinds=GN)
def _raycast(ctx: LiftContext, node: GraphNode) -> None:
    if ctx.has_link(node, "Attribute"):
        ctx.warn("lift.raycast_attribute", f"{node.display_name}: the Attribute sampling of Raycast is not translated.", node)
    ctx.emit(
        "RAYCAST",
        node,
        {
            "target": ctx.input(node, "Target Geometry"),
            "source_position": ctx.input(node, "Source Position", implicit="position"),
            "ray_direction": ctx.input(node, "Ray Direction"),
            "ray_length": ctx.input(node, "Ray Length"),
        },
        {"mapping": ctx.prop(node, "mapping", "INTERPOLATED")},
        {"is_hit": "Is Hit", "hit_position": "Hit Position", "hit_normal": "Hit Normal", "hit_distance": "Hit Distance"},
        output_types={"is_hit": DataType.BOOL, "hit_position": DataType.VECTOR3, "hit_normal": DataType.VECTOR3, "hit_distance": DataType.FLOAT},
    )


@lifts("GeometryNodeCurveToMesh", kinds=GN)
def _curve_to_mesh(ctx: LiftContext, node: GraphNode) -> None:
    inputs = {"geometry": ctx.input(node, "Curve"), "profile": ctx.input(node, "Profile Curve"), "fill_caps": ctx.input(node, "Fill Caps")}
    if node.find_input("Scale") is not None:
        inputs["scale"] = ctx.input(node, "Scale")
    ctx.emit("CURVE_TO_MESH", node, inputs, outputs={"geometry": "Mesh"})


@lifts("GeometryNodeResampleCurve", kinds=GN)
def _resample(ctx: LiftContext, node: GraphNode) -> None:
    mode = ctx.prop(node, "mode", "COUNT")
    inputs = {"geometry": ctx.input(node, "Curve"), "selection": ctx.input(node, "Selection")}
    if mode == "COUNT":
        inputs["count"] = ctx.input(node, "Count")
    elif mode == "LENGTH":
        inputs["length"] = ctx.input(node, "Length")
    ctx.emit("CURVE_RESAMPLE", node, inputs, {"mode": mode}, {"geometry": "Curve"})


@lifts("GeometryNodeMeshToCurve", kinds=GN)
def _mesh_to_curve(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit("MESH_TO_CURVE", node, {"geometry": ctx.input(node, "Mesh"), "selection": ctx.input(node, "Selection")}, outputs={"geometry": "Curve"})


@lifts("GeometryNodeMeshToPoints", kinds=GN)
def _mesh_to_points(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit(
        "MESH_TO_POINTS",
        node,
        {"geometry": ctx.input(node, "Mesh"), "selection": ctx.input(node, "Selection"), "radius": ctx.input(node, "Radius")},
        {"mode": ctx.prop(node, "mode", "VERTICES")},
        {"geometry": "Points"},
    )


@lifts("GeometryNodeMeshBoolean", kinds=GN)
def _boolean(ctx: LiftContext, node: GraphNode) -> None:
    operation = ctx.prop(node, "operation", "DIFFERENCE")
    inputs = {"mesh_b": ctx.multi_input(node, "Mesh 2")}
    if operation == "DIFFERENCE":
        inputs["mesh_a"] = ctx.input(node, "Mesh 1")
    ctx.emit("BOOLEAN", node, inputs, {"operation": operation}, {"geometry": "Mesh"})


@lifts("GeometryNodeObjectInfo", kinds=GN)
def _object_info(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit(
        "OBJECT_REFERENCE",
        node,
        {"object": ctx.input(node, "Object"), "as_instance": ctx.input(node, "As Instance")},
        {"transform_space": ctx.prop(node, "transform_space", "ORIGINAL")},
        {"geometry": "Geometry", "location": "Location", "rotation": "Rotation", "scale": "Scale"},
    )


@lifts("GeometryNodeCollectionInfo", kinds=GN)
def _collection_info(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit("COLLECTION_REFERENCE", node, {"collection": ctx.input(node, "Collection")}, outputs={"geometry": "Instances"}, output_types={"geometry": DataType.INSTANCES})


@lifts("GeometryNodeInputNamedAttribute", kinds=GN)
def _named_attribute(ctx: LiftContext, node: GraphNode) -> None:
    data_type = ctx.prop(node, "data_type", "FLOAT")
    out_type = {"FLOAT": DataType.FLOAT, "INT": DataType.INT, "FLOAT_VECTOR": DataType.VECTOR3, "FLOAT_COLOR": DataType.COLOR, "BOOLEAN": DataType.BOOL}.get(data_type, DataType.FLOAT)
    ctx.emit("ATTRIBUTE_READ", node, {"name": ctx.input(node, "Name")}, {"data_type": data_type}, {"value": "Attribute", "exists": "Exists"}, output_types={"value": out_type, "exists": DataType.BOOL})


@lifts("GeometryNodeStoreNamedAttribute", kinds=GN)
def _store_named_attribute(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit(
        "ATTRIBUTE_WRITE",
        node,
        {"geometry": ctx.input(node, "Geometry"), "selection": ctx.input(node, "Selection"), "name": ctx.input(node, "Name"), "value": ctx.input(node, "Value")},
        {"data_type": ctx.prop(node, "data_type", "FLOAT"), "domain": ctx.prop(node, "domain", "POINT")},
        {"geometry": "Geometry"},
    )


@lifts("FunctionNodeAlignEulerToVector", "FunctionNodeAlignRotationToVector", kinds=GN)
def _align(ctx: LiftContext, node: GraphNode) -> None:
    ctx.emit(
        "ALIGN_ROTATION",
        node,
        {"rotation": ctx.input(node, "Rotation"), "factor": ctx.input(node, "Factor"), "vector": ctx.input(node, "Vector")},
        {"axis": ctx.prop(node, "axis", "Z"), "pivot_axis": ctx.prop(node, "pivot_axis", "AUTO")},
        {"rotation": "Rotation"},
        output_types={"rotation": DataType.ROTATION},
    )


_ZONES = {
    "GeometryNodeSimulationInput": "Simulation zones",
    "GeometryNodeSimulationOutput": "Simulation zones",
    "GeometryNodeRepeatInput": "Repeat zones",
    "GeometryNodeRepeatOutput": "Repeat zones",
    "GeometryNodeForeachGeometryElementInput": "For Each Element zones",
    "GeometryNodeForeachGeometryElementOutput": "For Each Element zones",
}


@lifts(*_ZONES, kinds=GN)
def _zone(ctx: LiftContext, node: GraphNode) -> None:
    ctx.unsupported(node, f"{_ZONES[node.type]} are not translated yet; the generated network evaluates the zone body once.")
