import ast

from nodebridge.compiler import compile_source
from nodebridge.compiler.capabilities import blender_node_types, capability_matrix, render_markdown
from nodebridge.examples.graphs import compositor_tree, shader_tree
from nodebridge.translation.registry import REGISTRY
from nodebridge.backend.houdini.mappings import load


def test_shader_houdini_material_is_python():
    result = compile_source(shader_tree(), "houdini")
    ast.parse(result.code)
    assert "materialbuilder" in result.code
    assert "principledshader" in result.code
    assert "import hou" in result.code
    for record in result.records:
        assert f"# operation: {record.operation_id}" in result.code


def test_compositor_houdini_uses_cop_lookup():
    result = compile_source(compositor_tree(), "houdini")
    ast.parse(result.code)
    assert "cop2NodeTypeCategory" in result.code
    assert "createNode('cop2net'" in result.code
    assert "UNSUPPORTED" in result.report.text
    assert "Glare" in result.report.text or "glare" in result.report.text


def test_capability_matrix_is_data():
    rows = {row.operation: row for row in capability_matrix()}
    assert rows["scatter"].blender == "yes"
    assert rows["scatter"].houdini == "equivalent"
    assert rows["scatter"].unreal == "equivalent"
    assert rows["transform"].houdini == "exact"
    assert "GeometryNodeDistributePointsOnFaces" in blender_node_types()
    assert "ShaderNodeBsdfPrincipled" in blender_node_types()
    assert "CompositorNodeGlare" in blender_node_types()
    table = render_markdown()
    assert "| scatter |" in table
    load()
    assert REGISTRY.get(rows and __import__("nodebridge.ir.semantic", fromlist=["OperationKind"]).OperationKind.SCATTER, "houdini") is not None
