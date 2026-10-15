"""Blender lifting (syntax -> meaning), nested groups and rewrite rules."""

from helpers import B, F, G, I, V, geometry_passthrough, load_example, socket

from nodebridge.compiler.diagnostics import DiagnosticBag
from nodebridge.compiler.rewrite import RewriteEngine, eliminate_dead_operations, registered_rules
from nodebridge.compiler.subgraphs import inline_where
from nodebridge.frontend.blender.frontend import BlenderFrontend
from nodebridge.frontend.blender.lifting import supported_node_types
from nodebridge.ir.graph import TreeKind
from nodebridge.ir.semantic import Const, Link, Param
from nodebridge.ir.validation import validate_semantic


def lift(document):
    bag = DiagnosticBag()
    graph = BlenderFrontend().lift(document, bag)
    assert validate_semantic(graph) == []
    return graph, bag


def kinds(graph):
    return [op.kind for op in graph.ops.values()]


def test_scatter_lifts_to_semantic_operations_not_node_names():
    graph, _ = lift(load_example("scatter"))
    assert {"SCATTER", "INSTANCE", "INSTANCE_TRANSFORM", "RANDOM", "NOISE", "MAP_RANGE", "COMPARE", "DELETE_GEOMETRY", "MERGE"} <= set(kinds(graph))
    scatter = next(op for op in graph.ops.values() if op.kind == "SCATTER")
    assert scatter.inputs["density"] == Param("density") and scatter.inputs["seed"] == Param("seed")
    assert scatter.params["distribution_mode"] == "random"
    assert scatter.source.types == ["GeometryNodeDistributePointsOnFaces"]
    random = next(op for op in graph.ops.values() if op.kind == "RANDOM" and op.params["data_type"] == "FLOAT")
    assert random.outputs["value"].field, "Random Value with an implicit ID is a field"
    assert graph.ops[random.inputs["id"].op].params["field"] == "id"


def test_exposed_parameters_keep_roles_and_modifier_values():
    graph, _ = lift(load_example("building"))
    params = {p.key: p for p in graph.parameters}
    assert list(params) == ["width", "depth", "floors", "floor_height", "window_density", "seed"]
    assert params["width"].role.value == "length" and params["floors"].role.value == "integer"
    assert params["floor_height"].current == 3.0


def test_nested_group_is_a_semantic_subgraph():
    graph, _ = lift(load_example("building"))
    subgraph = next(op for op in graph.ops.values() if op.kind == "SUBGRAPH")
    assert subgraph.params["graph"] == "FloorSlab"
    sub = graph.subgraphs["FloorSlab"]
    assert sub.is_subgraph and [p.key for p in sub.parameters] == ["width", "depth", "thickness"]
    assert {"PRIMITIVE", "EXTRUDE"} <= set(kinds(sub))
    assert not any(ref.field for ref in subgraph.outputs.values())


def test_inlining_a_subgraph_preserves_meaning():
    graph, bag = lift(load_example("building"))
    inline_where(graph, lambda g, op: True, bag)
    assert "SUBGRAPH" not in kinds(graph) and not graph.subgraphs
    grid = next(op for op in graph.ops.values() if op.annotations.get("inlined_from") == "FloorSlab" and op.kind == "PRIMITIVE")
    assert isinstance(grid.inputs["size_x"], Link), "group input Width now comes from the parent's Math node"
    assert validate_semantic(graph) == []


def test_unknown_nodes_become_unsupported_operations():
    builder = geometry_passthrough()
    builder.node("Weird", "GeometryNodeSomethingNew", inputs=[socket("Geometry", G)], outputs=[socket("Geometry", G, output=True)])
    builder.link("Group Input", "Socket_0", "Weird", "Geometry").link("Weird", "Geometry", "Group Output", "Socket_1")
    graph, bag = lift(builder.document())
    op = next(op for op in graph.ops.values() if op.kind == "UNSUPPORTED_OPERATION")
    assert op.params["source_type"] == "GeometryNodeSomethingNew"
    assert any(d.code == "lift.unsupported" for d in bag)


def test_simulation_zone_is_reported_not_dropped():
    builder = geometry_passthrough()
    builder.node("Simulation Input", "GeometryNodeSimulationInput", inputs=[socket("Geometry", G)], outputs=[socket("Delta Time", F, output=True), socket("Geometry", G, output=True)])
    builder.node("Simulation Output", "GeometryNodeSimulationOutput", inputs=[socket("Geometry", G)], outputs=[socket("Geometry", G, output=True)])
    builder.link("Group Input", "Socket_0", "Simulation Input", "Geometry").link("Simulation Input", "Geometry", "Simulation Output", "Geometry").link("Simulation Output", "Geometry", "Group Output", "Socket_1")
    graph, bag = lift(builder.document())
    reasons = [op.params["reason"] for op in graph.ops.values() if op.kind == "UNSUPPORTED_OPERATION"]
    assert len(reasons) == 2 and all("Simulation zones" in r for r in reasons)


def test_supported_node_lists_cover_the_initial_subset():
    geometry = supported_node_types(TreeKind.GEOMETRY)
    for node_type in (
        "GeometryNodeJoinGeometry", "GeometryNodeTransform", "GeometryNodeSetPosition", "GeometryNodeInputPosition", "GeometryNodeInputNormal",
        "GeometryNodeInputIndex", "GeometryNodeInputID", "ShaderNodeMath", "ShaderNodeVectorMath", "ShaderNodeMapRange", "FunctionNodeCompare",
        "FunctionNodeBooleanMath", "GeometryNodeSwitch", "ShaderNodeTexNoise", "ShaderNodeTexVoronoi", "FunctionNodeRandomValue",
        "GeometryNodeDistributePointsOnFaces", "GeometryNodeInstanceOnPoints", "GeometryNodeRealizeInstances", "GeometryNodeRotateInstances",
        "GeometryNodeScaleInstances", "GeometryNodeSetMaterial", "GeometryNodeMeshCube", "GeometryNodeMeshGrid", "GeometryNodeCurvePrimitiveLine",
        "GeometryNodeCurvePrimitiveCircle", "GeometryNodeCurveToMesh", "GeometryNodeResampleCurve", "GeometryNodeExtrudeMesh",
        "GeometryNodeSubdivideMesh", "GeometryNodeDeleteGeometry", "GeometryNodeSeparateGeometry", "GeometryNodeProximity", "GeometryNodeRaycast",
    ):
        assert node_type in geometry, node_type
    assert "ShaderNodeBsdfPrincipled" in supported_node_types(TreeKind.SHADER)
    assert "CompositorNodeGlare" in supported_node_types(TreeKind.COMPOSITOR)


def rewrite(document):
    graph, bag = lift(document)
    engine = RewriteEngine()
    engine.run(graph, bag)
    eliminate_dead_operations(graph, bag)
    assert validate_semantic(graph) == []
    return graph, [name for name, _ in engine.applied]


def test_scatter_rewrites_into_random_transforms_and_noise_mask():
    graph, applied = rewrite(load_example("scatter"))
    assert applied.count("random_instance_attributes") == 1
    assert "random_instance_transform" in applied and "spatial_noise_mask" in applied
    assert not {"RANDOM", "INSTANCE_TRANSFORM", "NOISE", "COMPARE", "MAP_RANGE"} & set(kinds(graph))
    transforms = [op for op in graph.ops.values() if op.kind == "RANDOM_TRANSFORM"]
    scale = next(t for t in transforms if "scale_min" in t.inputs)
    assert scale.inputs["scale_min"] == Param("scale_min") and scale.params["uniform_scale"]
    rotation = next(t for t in transforms if "rotation_max" in t.inputs)
    assert rotation.inputs["rotation_max"].value[2] > 6.28
    instance = next(op for op in graph.ops.values() if op.kind == "INSTANCE")
    chain = graph.resolve(instance.inputs["points"])
    assert chain.kind == "RANDOM_TRANSFORM"
    mask = next(op for op in graph.ops.values() if op.kind == "SPATIAL_NOISE_MASK")
    assert mask.params["remap"]["from_min"] == 0.3 and mask.inputs["threshold"] == Param("coverage")


def test_rotate_instances_is_not_folded_when_pivot_is_offset():
    document = load_example("scatter")
    rotate = document.root_tree.nodes["Random Yaw"]
    rotate.input("Pivot Point").default = [1.0, 0.0, 0.0]
    graph, applied = rewrite(document)
    assert "random_instance_transform" not in applied
    assert "INSTANCE_TRANSFORM" in kinds(graph)


def test_constant_folding_and_switch_folding():
    builder = geometry_passthrough()
    builder.node("A", "ShaderNodeMath", inputs=[socket("Value", F, 2.0), socket("Value_001", F, 3.0)], outputs=[socket("Value", F, output=True)], operation="MULTIPLY")
    builder.node("Line", "GeometryNodeMeshLine", inputs=[socket("Count", I, 4), socket("Start Location", V, [0, 0, 0]), socket("Offset", V, [0, 0, 1])], outputs=[socket("Mesh", G, output=True)], mode="OFFSET", count_mode="TOTAL")
    builder.node("Cube", "GeometryNodeMeshCube", inputs=[socket("Size", V, [1, 1, 1])], outputs=[socket("Mesh", G, output=True)])
    builder.node("Switch", "GeometryNodeSwitch", inputs=[socket("Switch", B, True), socket("False", G), socket("True", G)], outputs=[socket("Output", G, output=True)], input_type="GEOMETRY")
    builder.link("A", "Value", "Line", "Count").link("Line", "Mesh", "Switch", "True").link("Cube", "Mesh", "Switch", "False").link("Switch", "Output", "Group Output", "Socket_1")
    graph, applied = rewrite(builder.document())
    assert {"fold_constants", "fold_switch"} <= set(applied)
    line = next(op for op in graph.ops.values() if op.kind == "PRIMITIVE")
    assert line.inputs["count"] == Const(6.0, F) and "SWITCH" not in kinds(graph)
    assert not any(op.params.get("shape") == "cube" for op in graph.ops.values())


def test_vignette_rule_on_compositor_example():
    graph, applied = rewrite(load_example("compositor"))
    assert "vignette" in applied and "VIGNETTE" in kinds(graph)
    assert not {"ELLIPSE_MASK", "BLUR", "MIX"} & set(kinds(graph))


def test_rules_are_registered_with_metadata():
    rules = {rule.name: rule for rule in registered_rules()}
    assert {"fold_constants", "fold_switch", "identity_transform", "random_instance_attributes", "random_instance_transform", "spatial_noise_mask", "vignette"} <= set(rules)
    assert rules["vignette"].kinds == (TreeKind.COMPOSITOR,)
