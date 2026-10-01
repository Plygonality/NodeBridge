import json
from pathlib import Path

from nodebridge.cli.main import main
from nodebridge.compiler import compile_source
from nodebridge.examples.graphs import scatter_tree
from nodebridge.frontend.blender import BlenderFrontend
from nodebridge.ir.serialization import dump


def test_cli_compiles_the_scatter_example(tmp_path: Path, capsys):
    code_path = tmp_path / "scatter.py"
    report_path = tmp_path / "scatter.txt"
    status = main(["compile", "--example", "scatter", "--target", "houdini", "--output", str(code_path), "--report", str(report_path)])
    assert status == 0
    code = code_path.read_text(encoding="utf-8")
    report = report_path.read_text(encoding="utf-8")
    assert "createNode('scatter::2.0'" in code
    assert "Geometry Nodes / ScatterBuildings" in report
    captured = capsys.readouterr()
    assert captured.out == ""


def test_cli_compiles_serialized_graph_ir(tmp_path: Path):
    tree = BlenderFrontend().parse(scatter_tree())
    path = tmp_path / "scatter.json"
    dump(tree, str(path))
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["__type__"] == "NodeTree"
    output = tmp_path / "out.py"
    status = main(["compile", "--input", str(path), "--target", "unreal", "--output", str(output)])
    assert status == 0
    assert "PCGGraphFactory" in output.read_text(encoding="utf-8")
    direct = compile_source(scatter_tree(), "unreal")
    assert "PCGSurfaceSamplerSettings" in direct.code
