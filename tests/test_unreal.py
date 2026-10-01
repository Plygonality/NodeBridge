import ast

from nodebridge.compiler import compile_source
from nodebridge.examples.graphs import compositor_tree, scatter_tree, shader_tree


def test_scatter_generates_unreal_pcg_python():
    result = compile_source(scatter_tree(), "unreal")
    code = result.code
    ast.parse(code)
    assert "import unreal" in code
    assert "def build(" in code
    assert "PCGGraphFactory" in code
    assert "PCGSurfaceSamplerSettings" in code
    assert "points_per_squared_meter" in code
    assert "PCGStaticMeshSpawnerSettings" in code
    assert "getattr(unreal, class_name, None)" in code
    assert "add_node_of_type" in code
    assert "# operation:" in code
    assert "EditorAssetLibrary.save_asset" in code
    for record in result.records:
        assert f"# operation: {record.operation_id}" in code
    assert "Target random samples may differ" in result.report.text or "sample positions" in result.report.text


def test_shader_generates_an_unreal_material():
    result = compile_source(shader_tree(), "unreal")
    ast.parse(result.code)
    assert "MaterialFactoryNew" in result.code
    assert "MaterialEditingLibrary" in result.code
    assert "recompile_material" in result.code


def test_compositor_does_not_invent_a_compositor_graph():
    result = compile_source(compositor_tree(), "unreal")
    ast.parse(result.code)
    assert "UNSUPPORTED" in result.report.text or "Unsupported" in result.report.text
    assert "glare" in result.report.text.lower() or "Glare" in result.code
    assert "PostProcessVolume" not in result.code
