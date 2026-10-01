import ast

from nodebridge.compiler import CompileOptions, compile_source
from nodebridge.examples.graphs import building_tree, scatter_tree
from nodebridge.frontend.blender import BlenderFrontend
from nodebridge.ir.semantic import OperationKind
from nodebridge.translation.confidence import Strictness
from tests.factory import link, node, socket, tree


def test_scatter_generates_a_native_sop_network():
    result = compile_source(scatter_tree(), "houdini")
    code = result.code
    ast.parse(code)
    assert "import hou" in code
    assert "def build(" in code
    assert "createNode('geo'" in code
    assert "createNode('scatter::2.0'" in code
    assert "forcetotal" in code
    assert 'ch("../density")' in code
    assert "createNode('box'" in code
    assert "createNode('copytopoints::2.0'" in code
    assert "createNode('unpack'" in code
    assert "setDisplayFlag(True)" in code
    assert "setRenderFlag(True)" in code
    assert "moveToGoodPosition()" in code
    assert "layoutChildren()" in code
    assert "FloatParmTemplate('density'" in code
    assert "nb_rand" in code
    assert "@pscale" in code
    assert "lerp(0.400000, 1.200000" in code
    assert "6.283180" in code
    assert "createNode('file'" not in code
    assert code.count("\n") > 20
    assert not result.issues
    assert "EXACT:" in result.report.text
    assert "EQUIVALENT:" in result.report.text
    assert "Target random samples may differ" in result.report.text


def test_exact_only_does_not_emit_scatter():
    options = CompileOptions(strictness=Strictness.EXACT_ONLY)
    result = compile_source(scatter_tree(), "houdini", options)
    assert "createNode('scatter::2.0'" not in result.code
    assert any(record.operation == "scatter" and not record.classification.emitted for record in result.records)


def test_building_exposes_height_and_joins_geometry():
    result = compile_source(building_tree(), "houdini")
    ast.parse(result.code)
    assert "createNode('grid'" in result.code
    assert "createNode('polyextrude::2.0'" in result.code or "createNode('polyextrude'" in result.code
    assert "createNode('merge'" in result.code
    assert "FloatParmTemplate('height'" in result.code
    assert "createNode('file'" not in result.code


def test_nested_group_becomes_a_subnet():
    inner_in = node("NodeGroupInput", "Group Input", outputs=[socket("Geometry")])
    inner_cube = node("GeometryNodeMeshCube", "Inner", outputs=[socket("Mesh")])
    inner_join = node(
        "GeometryNodeJoinGeometry",
        "Join",
        inputs=[socket("Geometry", "NodeSocketGeometry", multi=True)],
        outputs=[socket("Geometry")],
    )
    inner_out = node("NodeGroupOutput", "Group Output", inputs=[socket("Geometry")])
    inner = tree(
        "Facade",
        [inner_in, inner_cube, inner_join, inner_out],
        [
            link(inner_in, "Geometry", inner_join, "Geometry"),
            link(inner_cube, "Mesh", inner_join, "Geometry"),
            link(inner_join, "Geometry", inner_out, "Geometry"),
        ],
    )
    group = node("GeometryNodeGroup", "Facade Group", inputs=[socket("Geometry")], outputs=[socket("Geometry")], node_tree=inner)
    cube = node("GeometryNodeMeshCube", "Outer Cube", outputs=[socket("Mesh")])
    output = node("NodeGroupOutput", "Group Output", inputs=[socket("Geometry")])
    result = compile_source(
        tree(
            "Outer",
            [cube, group, output],
            [link(cube, "Mesh", group, "Geometry"), link(group, "Geometry", output, "Geometry")],
        ),
        "houdini",
    )
    ast.parse(result.code)
    assert "createNode('subnet'" in result.code
    assert "indirectInputs" in result.code


def test_simulation_is_reported_and_kept_in_the_script():
    sim = node("GeometryNodeSimulationInput", "Simulation Input", outputs=[socket("Geometry")])
    output = node("NodeGroupOutput", "Group Output", inputs=[socket("Geometry")])
    result = compile_source(tree("Sim", [sim, output], [link(sim, "Geometry", output, "Geometry")]), "houdini")
    ast.parse(result.code)
    assert "UNSUPPORTED:" in result.report.text
    assert "Simulation" in result.report.text
    assert any(record.operation == "unsupported" for record in result.records)
    assert "# operation:" in result.code
    semantic = BlenderFrontend().lower(result.tree)
    assert any(operation.kind is OperationKind.UNSUPPORTED for operation in semantic.operations)
