from nodebridge.compiler.analyzer import analyze
from nodebridge.compiler.rewrite import apply_rewrites
from nodebridge.frontend.blender import BlenderFrontend
from nodebridge.ir.semantic import OperationKind
from tests.factory import link, noise_mask_tree, node, scatter_tree, socket, tree


def test_scatter_tree_lowers_to_semantic_operations():
    frontend = BlenderFrontend()
    parsed = frontend.parse(scatter_tree())
    assert parsed.system.value == "geometry_nodes"
    assert len(parsed.nodes) == 8
    semantic = frontend.lower(parsed)
    kinds = {operation.kind for operation in semantic.operations}
    assert OperationKind.SCATTER in kinds
    assert OperationKind.INSTANCE in kinds
    assert OperationKind.RANDOM in kinds
    assert OperationKind.PRIMITIVE in kinds
    assert OperationKind.REALIZE_INSTANCES in kinds
    scatter = next(operation for operation in semantic.operations if operation.kind is OperationKind.SCATTER)
    assert scatter.parameters["density"] == 25.0
    assert scatter.parameters["seed"] == 3
    assert scatter.source.node_types == ("GeometryNodeDistributePointsOnFaces",)
    assert semantic.interface[0].name == "Density"


def test_reroute_is_not_a_semantic_operation():
    cube = node("GeometryNodeMeshCube", "Cube", outputs=[socket("Mesh")])
    reroute = node("NodeReroute", "Reroute", inputs=[socket("Input")], outputs=[socket("Output")])
    output = node("NodeGroupOutput", "Group Output", inputs=[socket("Geometry")])
    parsed = BlenderFrontend().parse(
        tree("Reroute", [cube, reroute, output], [link(cube, "Mesh", reroute, "Input"), link(reroute, "Output", output, "Geometry")])
    )
    semantic = BlenderFrontend().lower(parsed)
    assert all(operation.kind is not OperationKind.REROUTE for operation in semantic.operations)
    assert any(edge.from_operation == "cube" and edge.to_operation == "group_output" for edge in semantic.edges)


def test_nested_group_becomes_a_subgraph():
    inner_cube = node("GeometryNodeMeshCube", "Inner", outputs=[socket("Mesh")])
    inner_out = node("NodeGroupOutput", "Group Output", inputs=[socket("Geometry")])
    inner = tree("Facade", [inner_cube, inner_out], [link(inner_cube, "Mesh", inner_out, "Geometry")])
    group = node("GeometryNodeGroup", "Facade Group", inputs=[], outputs=[socket("Geometry")], node_tree=inner)
    output = node("NodeGroupOutput", "Group Output", inputs=[socket("Geometry")])
    parsed = BlenderFrontend().parse(tree("Outer", [group, output], [link(group, "Geometry", output, "Geometry")]))
    semantic = BlenderFrontend().lower(parsed)
    subgraph = next(operation for operation in semantic.operations if operation.kind is OperationKind.SUBGRAPH)
    assert subgraph.subgraph is not None
    assert any(operation.kind is OperationKind.PRIMITIVE for operation in subgraph.subgraph.operations)


def test_simulation_zone_is_unsupported_and_kept():
    sim = node("GeometryNodeSimulationInput", "Simulation Input", outputs=[socket("Geometry")])
    output = node("NodeGroupOutput", "Group Output", inputs=[socket("Geometry")])
    parsed = BlenderFrontend().parse(tree("Sim", [sim, output], [link(sim, "Geometry", output, "Geometry")]))
    semantic = BlenderFrontend().lower(parsed)
    unsupported = next(operation for operation in semantic.operations if operation.kind is OperationKind.UNSUPPORTED)
    assert "Simulation" in unsupported.parameters["reason"]


def test_dead_node_and_cycle_analysis():
    cube = node("GeometryNodeMeshCube", "Cube", outputs=[socket("Mesh")])
    noise = node("ShaderNodeTexNoise", "Unused Noise", outputs=[socket("Fac", "NodeSocketFloat")])
    output = node("NodeGroupOutput", "Group Output", inputs=[socket("Geometry")])
    parsed = BlenderFrontend().parse(tree("Dead", [cube, noise, output], [link(cube, "Mesh", output, "Geometry")]))
    analysis = analyze(parsed)
    assert "unused_noise" in analysis.dead_nodes
    assert "cube" in analysis.order
    a = node("ShaderNodeMath", "A", inputs=[socket("Value", "NodeSocketFloat")], outputs=[socket("Value", "NodeSocketFloat")])
    b = node("ShaderNodeMath", "B", inputs=[socket("Value", "NodeSocketFloat")], outputs=[socket("Value", "NodeSocketFloat")])
    cyclic = BlenderFrontend().parse(tree("Cycle", [a, b], [link(a, "Value", b, "Value"), link(b, "Value", a, "Value")]))
    cycle = analyze(cyclic)
    assert cycle.cycles
    assert cycle.errors


def test_noise_compare_chain_rewrites_to_one_mask():
    semantic = BlenderFrontend().lower(BlenderFrontend().parse(noise_mask_tree()))
    rewritten = apply_rewrites(semantic)
    kinds = [operation.kind for operation in rewritten.operations]
    assert OperationKind.SPATIAL_NOISE_MASK in kinds
    assert OperationKind.NOISE not in kinds
    assert OperationKind.COMPARE not in kinds
