"""Acceptance tests for generated-code safety and compiler diagnostics.

Each case is written against the behaviour the compiler must have: a payload
cannot become a statement, bad input cannot raise, and dishonest translations
are reported.
"""

from __future__ import annotations

import ast
import contextlib
import importlib
import io
import json
import math
import sys

import pytest

from nodebridge.backend.registry import get_backend
from nodebridge.cli import main
from nodebridge.compiler.evaluate import MATH, NotConstant, evaluate
from nodebridge.compiler.pipeline import analyze, compile_document
from nodebridge.compiler.report import TranslationReport
from nodebridge.frontend.blender.lifting import LiftError
from nodebridge.frontend.blender.parser import apply_modifier_values
from nodebridge.ir.graph import GraphDocument, GraphEdge, TreeKind
from nodebridge.ir.serialization import dumps_graph, loads_graph
from nodebridge.ir.types import DataType
from nodebridge.translation.confidence import Confidence

from helpers import B, F, G, I, V, TreeBuilder, geometry_passthrough, run_script, socket

COLOR = DataType.COLOR
S = DataType.STRING


def _assigned_names(code: str) -> set[str]:
    tree = ast.parse(code)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _exec(code: str, module: str):
    fake = importlib.import_module(f"fakes.fake_{module}")
    fake.reset()
    previous = sys.modules.get(module)
    sys.modules[module] = fake
    namespace = {"__name__": "__main__"}
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(code, f"<generated {module}>", "exec"), namespace)
    finally:
        if previous is None:
            sys.modules.pop(module, None)
        else:
            sys.modules[module] = previous
    return namespace, fake


def _codes(result) -> set[str]:
    return {item.code for item in result.diagnostics}


def test_display_name_cannot_escape_the_docstring():
    builder = geometry_passthrough("Injected")
    document = builder.document(display_name='x"""\nMARKER = 123\n"""', application="Blender")
    for target, module in (("houdini", "hou"), ("unreal", "unreal")):
        result = compile_document(document, target)
        code = result.code.code
        assert get_backend(target).validate_script(code) == []
        assert "MARKER" not in _assigned_names(code)
        namespace, _fake = _exec(code, module)
        assert "MARKER" not in namespace
        assert namespace.get("MARKER") is None


def test_parameter_label_stays_inside_a_comment():
    builder = TreeBuilder("Labels")
    builder.interface("Socket_0", "Geometry", "INPUT", G)
    builder.interface("Socket_1", "Density\nMARKER = 123\n#", "INPUT", F, default=1.5)
    builder.interface("Socket_2", "Geometry", "OUTPUT", G)
    builder.group_io().link("Group Input", "Socket_0", "Group Output", "Socket_2")
    result = compile_document(builder.document(), "unreal")
    code = result.code.code
    assert get_backend("unreal").validate_script(code) == []
    assert "MARKER" not in _assigned_names(code)
    namespace, _fake = _exec(code, "unreal")
    assert namespace.get("MARKER") is None
    assert "Density" in code


def test_attribute_name_stays_inside_a_vex_string():
    builder = geometry_passthrough("Attrs")
    builder.node(
        "Store",
        "GeometryNodeStoreNamedAttribute",
        inputs=[
            socket("Geometry", G),
            socket("Selection", B, True),
            socket("Name", S, 'pwn");\n@P = {0,0,0}; //'),
            socket("Value", F, 1.0),
        ],
        outputs=[socket("Geometry", G, output=True)],
        data_type="FLOAT",
        domain="POINT",
    )
    builder.link("Group Input", "Socket_0", "Store", "Geometry").link("Store", "Geometry", "Group Output", "Socket_1")
    result = compile_document(builder.document(), "houdini")
    code = result.code.code
    assert get_backend("houdini").validate_script(code) == []
    _namespace, fake = _exec(code, "hou")
    snippets = [node.parm_values.get("snippet", "") for node in fake.all_nodes() if node.parm_values.get("snippet")]
    assert snippets
    for snippet in snippets:
        # Shared VEX libraries are real statements. The payload must not add another one.
        assert "setpointattrib" in snippet
        assert not any(line.lstrip().startswith("@P") for line in snippet.splitlines())
        assert 'pwn");' not in snippet
        assert "\\x22" in snippet and "\\x0a" in snippet


def test_unicode_labels_remain_labels():
    builder = geometry_passthrough("Cafe")
    node = builder.node(
        "Move",
        "GeometryNodeTransform",
        inputs=[socket("Geometry", G), socket("Translation", V, [1, 0, 0]), socket("Rotation", V, [0, 0, 0]), socket("Scale", V, [1, 1, 1])],
        outputs=[socket("Geometry", G, output=True)],
    )
    node.label = "Café"
    builder.link("Group Input", "Socket_0", "Move", "Geometry").link("Move", "Geometry", "Group Output", "Socket_1")
    code = compile_document(builder.document(), "houdini").code.code
    assert "Café" in code


def test_round_half_away_from_zero():
    assert MATH["ROUND"](-1.5, 0, 0) == -2.0
    assert isinstance(MATH["ROUND"](-1.5, 0, 0), float)
    from nodebridge.backend.houdini.hscript import MATH as HSCRIPT_MATH
    from nodebridge.backend.houdini.vex import MATH_VEX
    from nodebridge.backend.unreal.pyexpr import MATH as PY_MATH

    assert "-floor" in MATH_VEX["ROUND"]
    assert "-floor" in HSCRIPT_MATH["ROUND"]
    assert "copysign" in PY_MATH["ROUND"]
    builder = TreeBuilder("Round")
    builder.interface("Socket_0", "Value", "INPUT", F, default=0.0)
    builder.interface("Socket_1", "Value", "OUTPUT", F)
    builder.group_io()
    builder.node("Round", "ShaderNodeMath", inputs=[socket("Value", F, -1.5)], outputs=[socket("Value", F, output=True)], operation="ROUND")
    builder.link("Round", "Value", "Group Output", "Socket_1")
    folded = compile_document(builder.document(), "houdini")
    value = folded.semantic.outputs[0].value.value
    assert value == -2.0
    assert isinstance(value, float)


def test_omitted_defaults_do_not_raise():
    builder = geometry_passthrough("Omitted")
    builder.node("Math", "ShaderNodeMath", inputs=[socket("Value", F, None), socket("Value_001", F, None)], outputs=[socket("Value", F, output=True)], operation="ADD")
    builder.node(
        "Move",
        "GeometryNodeTransform",
        inputs=[socket("Geometry", G)],
        outputs=[socket("Geometry", G, output=True)],
    )
    builder.link("Group Input", "Socket_0", "Move", "Geometry").link("Move", "Geometry", "Group Output", "Socket_1")
    result = compile_document(builder.document(), "houdini")
    assert result.code is not None
    assert get_backend("houdini").validate_script(result.code.code) == []


def test_unknown_boolean_is_unsupported_not_a_crash():
    builder = geometry_passthrough("Banana")
    builder.node("Logic", "FunctionNodeBooleanMath", inputs=[socket("Boolean", B, True), socket("Boolean_001", B, False)], outputs=[socket("Boolean", B, output=True)], operation="BANANA")
    builder.node(
        "Delete",
        "GeometryNodeDeleteGeometry",
        inputs=[socket("Geometry", G), socket("Selection", B)],
        outputs=[socket("Geometry", G, output=True)],
        domain="POINT",
    )
    builder.link("Logic", "Boolean", "Delete", "Selection").link("Group Input", "Socket_0", "Delete", "Geometry").link("Delete", "Geometry", "Group Output", "Socket_1")
    result = compile_document(builder.document(), "houdini")
    entry = next(item for item in result.report.entries if item.kind == "BOOLEAN_MATH")
    assert entry.classification.confidence == Confidence.UNSUPPORTED
    assert "compiler.unsupported_operation" in _codes(result) or entry.classification.confidence == Confidence.UNSUPPORTED
    assert result.code is not None


def test_recursive_group_is_a_placeholder():
    builder = TreeBuilder("Loop")
    builder.interface("Socket_0", "Geometry", "INPUT", G).interface("Socket_1", "Geometry", "OUTPUT", G).group_io()
    node = builder.node("Again", "GeometryNodeGroup", inputs=[socket("Geometry", G)], outputs=[socket("Geometry", G, output=True)])
    node.group_tree = "Loop"
    builder.link("Group Input", "Socket_0", "Again", "Geometry").link("Again", "Geometry", "Group Output", "Socket_1")
    try:
        result = compile_document(builder.document(), "houdini")
    except LiftError as exc:  # pragma: no cover - the assertion is the point
        raise AssertionError(exc) from exc
    assert "graph.recursive_group" in _codes(result)
    assert any(op.kind == "UNSUPPORTED_OPERATION" for op in result.semantic.ops.values())


def test_group_nest_stops_at_the_depth_limit():
    trees = []
    for index in range(500):
        builder = TreeBuilder(f"G{index}", is_group=index != 0)
        builder.interface("Socket_0", "Geometry", "INPUT", G).interface("Socket_1", "Geometry", "OUTPUT", G).group_io()
        if index < 499:
            node = builder.node("Inner", "GeometryNodeGroup", inputs=[socket("Geometry", G)], outputs=[socket("Geometry", G, output=True)])
            node.group_tree = f"G{index + 1}"
            builder.link("Group Input", "Socket_0", "Inner", "Geometry").link("Inner", "Geometry", "Group Output", "Socket_1")
        else:
            builder.link("Group Input", "Socket_0", "Group Output", "Socket_1")
        trees.append(builder.tree)
    document = GraphDocument(root="G0", trees={tree.name: tree for tree in trees}, source={"display_name": "Deep"})
    result = compile_document(document, "houdini")
    assert "graph.depth" in _codes(result)


def test_expression_chain_stops_at_the_depth_limit():
    builder = geometry_passthrough("Chain")
    builder.interface("Socket_2", "Offset", "INPUT", V, default=[1, 0, 0])
    # Rebuild group input so the new socket exists. geometry_passthrough already called group_io.
    builder.tree.nodes.pop("Group Input")
    builder.tree.nodes.pop("Group Output")
    builder.group_io()
    previous = ("Group Input", "Socket_2")
    for index in range(400):
        builder.node(
            f"V{index}",
            "ShaderNodeVectorMath",
            inputs=[socket("Vector", V), socket("Vector_001", V, [0, 1, 0])],
            outputs=[socket("Vector", V, output=True), socket("Value", F, output=True)],
            operation="ADD",
        )
        builder.link(previous[0], previous[1], f"V{index}", "Vector")
        previous = (f"V{index}", "Vector")
    builder.node(
        "Scatter",
        "GeometryNodeDistributePointsOnFaces",
        inputs=[socket("Mesh", G), socket("Density", F, 1.0)],
        outputs=[socket("Points", DataType.POINTS, output=True)],
        distribute_method="RANDOM",
    )
    builder.node(
        "Move",
        "GeometryNodeSetPosition",
        inputs=[socket("Geometry", G), socket("Offset", V)],
        outputs=[socket("Geometry", G, output=True)],
    )
    builder.link("Group Input", "Socket_0", "Scatter", "Mesh")
    builder.link("Scatter", "Points", "Move", "Geometry")
    builder.link(previous[0], previous[1], "Move", "Offset")
    builder.link("Move", "Geometry", "Group Output", "Socket_1")
    houdini = compile_document(builder.document(), "houdini")
    unreal = compile_document(builder.document(), "unreal")
    assert "compiler.depth" in _codes(houdini)
    assert "compiler.depth" in _codes(unreal)
    link = next(op.inputs["offset"] for op in houdini.semantic.ops.values() if op.kind == "SET_POSITION")
    with pytest.raises(NotConstant):
        evaluate(houdini.semantic, link)


def test_multiple_links_and_duplicate_trees_are_reported():
    builder = geometry_passthrough("Links")
    builder.node("A", "ShaderNodeMath", inputs=[socket("Value", F, 1.0)], outputs=[socket("Value", F, output=True)], operation="ADD")
    builder.link("Group Input", "Socket_0", "Group Output", "Socket_1")
    builder.link("Group Input", "Socket_0", "Group Output", "Socket_1")
    analyzed = analyze(builder.document(), "houdini")
    assert "graph.multiple_links" in _codes(analyzed)
    payload = json.loads(dumps_graph(builder.document()))
    payload["trees"].append(payload["trees"][0])
    document = loads_graph(json.dumps(payload))
    assert document.duplicate_trees
    assert "graph.duplicate_tree" in _codes(analyze(document, "houdini"))


def test_loads_graph_rejects_bad_documents():
    with pytest.raises(ValueError):
        loads_graph("null")
    with pytest.raises(ValueError):
        loads_graph(json.dumps({"format": "other", "format_version": 1, "root": "A", "trees": []}))
    with pytest.raises(ValueError):
        loads_graph(json.dumps({"format": "nodebridge.graph", "format_version": 2, "root": "A", "trees": []}))
    with pytest.raises(ValueError):
        loads_graph(json.dumps({"format": "nodebridge.graph", "format_version": 1, "trees": []}))


def test_structural_errors_skip_generation(tmp_path):
    document = GraphDocument(root="missing", trees={}, source={})
    result = analyze(document, "houdini")
    assert "graph.missing_root" in _codes(result)
    generated = compile_document(document, "houdini")
    assert generated.code is None
    path = tmp_path / "missing.json"
    path.write_text("null", encoding="utf-8")
    assert main(["generate", str(path), "--target", "houdini"]) == 2
    assert main(["generate", str(tmp_path / "nope.json"), "--target", "houdini"]) == 2
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert main(["generate", str(broken), "--target", "houdini"]) == 2
    key = tmp_path / "key.json"
    key.write_text(json.dumps({"format": "nodebridge.graph", "format_version": 1, "root": "A", "trees": [{}]}), encoding="utf-8")
    assert main(["generate", str(key), "--target", "houdini"]) == 2


def test_cycle_makes_generate_exit_1(tmp_path, capsys):
    builder = TreeBuilder("Cycle")
    builder.interface("Socket_0", "Value", "INPUT", F, default=1.0).interface("Socket_1", "Value", "OUTPUT", F).group_io()
    builder.node("A", "ShaderNodeMath", inputs=[socket("Value", F, 0.0), socket("Value_001", F, 1.0)], outputs=[socket("Value", F, output=True)], operation="ADD")
    builder.node("B", "ShaderNodeMath", inputs=[socket("Value", F, 0.0), socket("Value_001", F, 1.0)], outputs=[socket("Value", F, output=True)], operation="ADD")
    builder.link("A", "Value", "B", "Value").link("B", "Value", "A", "Value").link("A", "Value", "Group Output", "Socket_1")
    path = tmp_path / "cycle.graph.json"
    path.write_text(dumps_graph(builder.document()), encoding="utf-8")
    out = tmp_path / "cycle.py"
    assert main(["generate", str(path), "--target", "houdini", "-o", str(out)]) == 1
    err = capsys.readouterr().err
    assert "Cycle between nodes" in err
    assert "nothing to generate" not in err
    assert not out.exists()
    assert compile_document(loads_graph(path.read_text(encoding="utf-8")), "houdini").code is None


def test_dangling_edge_prints_the_diagnostic(tmp_path, capsys):
    builder = geometry_passthrough("Dangle")
    builder.link("Group Input", "Socket_0", "Group Output", "Socket_1")
    builder.tree.edges.append(GraphEdge("Missing", "X", "Group Output", "Socket_1"))
    path = tmp_path / "dangle.graph.json"
    path.write_text(dumps_graph(builder.document()), encoding="utf-8")
    out = tmp_path / "dangle.py"
    assert main(["generate", str(path), "--target", "houdini", "-o", str(out)]) == 1
    err = capsys.readouterr().err
    assert "Link references a missing node (Missing -> Group Output)." in err
    assert "nothing to generate" not in err
    assert not out.exists()


def test_missing_selection_keeps_geometry():
    builder = geometry_passthrough("Keep")
    builder.node("Delete", "GeometryNodeDeleteGeometry", inputs=[socket("Geometry", G)], outputs=[socket("Geometry", G, output=True)], domain="POINT")
    builder.link("Group Input", "Socket_0", "Delete", "Geometry").link("Delete", "Geometry", "Group Output", "Socket_1")
    houdini = compile_document(builder.document(), "houdini")
    unreal = compile_document(builder.document(), "unreal")
    assert "removepoint" not in houdini.code.code
    assert "if (1)" not in houdini.code.code
    assert "delete.missing_selection" in _codes(houdini)
    assert "delete.missing_selection" in _codes(unreal)
    for result in (houdini, unreal):
        entry = next(item for item in result.report.entries if item.kind == "DELETE_GEOMETRY")
        assert entry.classification.confidence != Confidence.EXACT


def _delete_points(selection):
    builder = geometry_passthrough("Points")
    builder.node(
        "Scatter",
        "GeometryNodeDistributePointsOnFaces",
        inputs=[socket("Mesh", G), socket("Density", F, 4.0), socket("Seed", I, 1)],
        outputs=[socket("Points", DataType.POINTS, output=True)],
        distribute_method="RANDOM",
    )
    inputs = [socket("Geometry", G)]
    if selection is not None:
        inputs.append(socket("Selection", B, selection))
    builder.node("Delete", "GeometryNodeDeleteGeometry", inputs=inputs, outputs=[socket("Geometry", G, output=True)], domain="POINT")
    builder.link("Group Input", "Socket_0", "Scatter", "Mesh").link("Scatter", "Points", "Delete", "Geometry").link("Delete", "Geometry", "Group Output", "Socket_1")
    return compile_document(builder.document(), "unreal")


def test_constant_unreal_deletes_differ_by_an_empty_result():
    kept = _delete_points(False)
    removed = _delete_points(True)
    assert "PCGCreatePointsSettings" in removed.code.code
    assert "PCGCreatePointsSettings" not in kept.code.code
    _namespace, fake = _exec(removed.code.code, "unreal")
    edges = fake.STATE["edges"]
    assert any(edge[0] == "PCGCreatePointsSettings" for edge in edges)
    assert any(edge[2] == "_output" for edge in edges)
    _namespace, kept_fake = _exec(kept.code.code, "unreal")
    assert any(edge[2] == "_output" for edge in kept_fake.STATE["edges"])
    assert not any(edge[0] == "PCGCreatePointsSettings" for edge in kept_fake.STATE["edges"])


def test_scene_scale_and_non_finite_values():
    builder = geometry_passthrough("Scaled")
    builder.node(
        "Move",
        "GeometryNodeTransform",
        inputs=[socket("Geometry", G), socket("Translation", V, [1.0, 2.0, 3.0]), socket("Rotation", V, [0, 0, 0]), socket("Scale", V, [1, 1, 1])],
        outputs=[socket("Geometry", G, output=True)],
    )
    builder.link("Group Input", "Socket_0", "Move", "Geometry").link("Move", "Geometry", "Group Output", "Socket_1")
    houdini = compile_document(builder.document(unit_scale=0.01), "houdini")
    assert "(0.01, 0.03, -0.02)" in houdini.code.code
    points = geometry_passthrough("PointsScale")
    points.node(
        "Scatter",
        "GeometryNodeDistributePointsOnFaces",
        inputs=[socket("Mesh", G), socket("Density", F, 1.0)],
        outputs=[socket("Points", DataType.POINTS, output=True)],
        distribute_method="RANDOM",
    )
    points.node(
        "Move",
        "GeometryNodeSetPosition",
        inputs=[socket("Geometry", G), socket("Offset", V, [1.0, 2.0, 3.0])],
        outputs=[socket("Geometry", G, output=True)],
    )
    points.link("Group Input", "Socket_0", "Scatter", "Mesh").link("Scatter", "Points", "Move", "Geometry").link("Move", "Geometry", "Group Output", "Socket_1")
    unreal = compile_document(points.document(unit_scale=0.01), "unreal")
    assert "Vector(1.0, -2.0, 3.0)" in unreal.code.code
    assert "Vector(100" not in unreal.code.code
    dirty = geometry_passthrough("Dirty")
    dirty.node(
        "Move",
        "GeometryNodeTransform",
        inputs=[socket("Geometry", G), socket("Translation", V, [float("nan"), float("inf"), 2.0]), socket("Rotation", V, [0, 0, 0]), socket("Scale", V, [1, 1, 1])],
        outputs=[socket("Geometry", G, output=True)],
    )
    dirty.link("Group Input", "Socket_0", "Move", "Geometry").link("Move", "Geometry", "Group Output", "Socket_1")
    warned = compile_document(dirty.document(), "houdini")
    assert "houdini.non_finite" in _codes(warned)
    assert "(0.0, 2.0, 0.0)" in warned.code.code
    entry = next(item for item in warned.report.entries if item.kind == "TRANSFORM")
    assert entry.classification.confidence != Confidence.EXACT
    points = geometry_passthrough("DirtyPoints")
    points.node(
        "Scatter",
        "GeometryNodeDistributePointsOnFaces",
        inputs=[socket("Mesh", G), socket("Density", F, 1.0)],
        outputs=[socket("Points", DataType.POINTS, output=True)],
        distribute_method="RANDOM",
    )
    points.node(
        "Move",
        "GeometryNodeSetPosition",
        inputs=[socket("Geometry", G), socket("Offset", V, [float("nan"), float("inf"), 2.0])],
        outputs=[socket("Geometry", G, output=True)],
    )
    points.link("Group Input", "Socket_0", "Scatter", "Mesh").link("Scatter", "Points", "Move", "Geometry").link("Move", "Geometry", "Group Output", "Socket_1")
    unreal_warned = compile_document(points.document(), "unreal")
    assert "unreal.non_finite" in _codes(unreal_warned)
    move = next(item for item in unreal_warned.report.entries if item.kind == "SET_POSITION")
    assert move.classification.confidence != Confidence.EXACT


def test_non_ascii_fallback_names_the_original():
    builder = geometry_passthrough("Ascii")
    builder.interface("Socket_2", "密度", "INPUT", F, default=1.0)
    node = builder.node(
        "Move",
        "GeometryNodeTransform",
        inputs=[socket("Geometry", G), socket("Translation", V, [1, 0, 0]), socket("Rotation", V, [0, 0, 0]), socket("Scale", V, [1, 1, 1])],
        outputs=[socket("Geometry", G, output=True)],
    )
    node.label = "密度"
    builder.tree.nodes.pop("Group Input")
    builder.tree.nodes.pop("Group Output")
    builder.group_io()
    builder.link("Group Input", "Socket_0", "Move", "Geometry").link("Move", "Geometry", "Group Output", "Socket_1")
    result = compile_document(builder.document(), "houdini")
    messages = [item.message for item in result.diagnostics if item.code == "name.non_ascii"]
    assert any("密度" in message and "parameter" in message for message in messages)
    assert any("密度" in message and "node" in message for message in messages)
    asset = TreeBuilder("密度")
    asset.interface("Socket_0", "Geometry", "INPUT", G).interface("Socket_1", "Geometry", "OUTPUT", G).group_io()
    asset.link("Group Input", "Socket_0", "Group Output", "Socket_1")
    unreal = compile_document(asset.document(), "unreal")
    assert any(item.code == "name.non_ascii" and "密度" in item.message and "Asset" in item.message for item in unreal.diagnostics)


def test_sidebar_notes_include_dead_nodes_and_the_omitted_count():
    builder = geometry_passthrough("Dead")
    builder.node("Unused", "ShaderNodeMath", inputs=[socket("Value", F, 1.0), socket("Value_001", F, 2.0)], outputs=[socket("Value", F, output=True)], operation="ADD")
    builder.link("Group Input", "Socket_0", "Group Output", "Socket_1")
    result = analyze(builder.document(), "houdini")
    assert any(line.startswith("Note |") and "does not contribute" in line for line in result.report.warnings())
    report = TranslationReport("Geometry Nodes", "Many", "", "houdini", "Houdini", 0)
    from nodebridge.compiler.diagnostics import Diagnostic, Severity

    report.diagnostics = [Diagnostic(Severity.INFO, "graph.dead_node", f"dead {index}") for index in range(45)]
    lines = report.ui_warnings(40)
    assert lines[-1] == "5 notes omitted past 40"
    assert len(lines) == 41


def test_modifier_seed_is_read_from_blender_5_inputs():
    builder = geometry_passthrough("Seeded")
    builder.interface("Seed", "Seed", "INPUT", I, default=0)
    builder.tree.nodes.pop("Group Input")
    builder.tree.nodes.pop("Group Output")
    builder.group_io().link("Group Input", "Socket_0", "Group Output", "Socket_1")

    class Item:
        def __init__(self, value):
            self.value = value

    class Modifier:
        def __init__(self):
            self.properties = type("Props", (), {"inputs": {"Seed": Item(42)}})()

        def __getitem__(self, key):
            raise TypeError("5.x modifiers are not keyed by identifier")

    apply_modifier_values(builder.tree, Modifier())
    seed = next(item for item in builder.tree.inputs if item.identifier == "Seed")
    assert seed.value == 42
    houdini = compile_document(builder.document(), "houdini")
    unreal = compile_document(builder.document(), "unreal")
    assert "42" in houdini.code.code
    assert "SEED = 42" in unreal.code.code

    class Broken:
        def __getitem__(self, key):
            raise TypeError("not a modifier")

    with pytest.raises(TypeError):
        apply_modifier_values(builder.tree, Broken())


def test_unsupported_shader_passes_its_color_through():
    builder = TreeBuilder("Shade", TreeKind.SHADER)
    builder.node("RGB", "ShaderNodeRGB", outputs=[socket("Color", COLOR, [0.2, 0.4, 0.6, 1.0], output=True)])
    builder.node(
        "Side",
        "ShaderNodeSeparateColor",
        inputs=[socket("Color", COLOR, [1, 0, 0, 1])],
        outputs=[socket("Red", F, output=True), socket("Green", F, output=True), socket("Blue", F, output=True)],
    )
    builder.node(
        "Gamma",
        "ShaderNodeGamma",
        inputs=[socket("Color", COLOR), socket("Gamma", F)],
        outputs=[socket("Color", COLOR, output=True)],
    )
    builder.node(
        "Emit",
        "ShaderNodeEmission",
        inputs=[socket("Color", COLOR), socket("Strength", F, 1.0)],
        outputs=[socket("Emission", DataType.SHADER, output=True)],
    )
    builder.node("Out", "ShaderNodeOutputMaterial", inputs=[socket("Surface", DataType.SHADER)], outputs=[], is_active_output=True)
    builder.link("RGB", "Color", "Gamma", "Color").link("Side", "Red", "Gamma", "Gamma").link("Gamma", "Color", "Emit", "Color").link("Emit", "Emission", "Out", "Surface")
    result = compile_document(builder.document(display_name="Shade"), "houdini")
    assert "0.2" in result.code.code and "0.4" in result.code.code
    assert "constant is used instead" not in result.code.code
    assert not any(entry.name == "Side" for entry in result.report.entries)
    hue = TreeBuilder("Hue", TreeKind.SHADER)
    hue.node("RGB", "ShaderNodeRGB", outputs=[socket("Color", COLOR, [1, 0, 0, 1], output=True)])
    hue.node(
        "HSV",
        "ShaderNodeHueSaturation",
        inputs=[socket("Hue", F, 0.5), socket("Saturation", F, 1.0), socket("Value", F, 1.0), socket("Fac", F, 1.0), socket("Color", COLOR)],
        outputs=[socket("Color", COLOR, output=True)],
    )
    hue.node("Emit", "ShaderNodeEmission", inputs=[socket("Color", COLOR), socket("Strength", F, 1.0)], outputs=[socket("Emission", DataType.SHADER, output=True)])
    hue.node("Out", "ShaderNodeOutputMaterial", inputs=[socket("Surface", DataType.SHADER)], outputs=[], is_active_output=True)
    hue.link("RGB", "Color", "HSV", "Color").link("HSV", "Color", "Emit", "Color").link("Emit", "Emission", "Out", "Surface")
    houdini = compile_document(hue.document(display_name="Hue"), "houdini")
    unreal = compile_document(hue.document(display_name="Hue"), "unreal")
    assert "mtlxhsvadjust" in houdini.code.code
    assert "MaterialExpressionHueShift" in unreal.code.code
    entry = next(item for item in houdini.report.entries if item.kind == "COLOR_OPERATION")
    assert entry.classification.confidence == Confidence.EQUIVALENT


def test_compositor_mix_viewer_and_lift():
    mix = TreeBuilder("Mix", TreeKind.COMPOSITOR)
    mix.node("Image", "CompositorNodeImage", outputs=[socket("Image", COLOR, output=True)], image={"filepath": "a.exr"})
    mix.node(
        "Blend",
        "CompositorNodeMixRGB",
        inputs=[socket("Fac", F, 0.25), socket("Image", COLOR), socket("Image_001", COLOR, [1, 0, 0, 1])],
        outputs=[socket("Image", COLOR, output=True)],
        blend_type="SCREEN",
    )
    mix.node("Out", "CompositorNodeComposite", inputs=[socket("Image", COLOR)], outputs=[], is_active_output=True)
    mix.link("Image", "Image", "Blend", "Image").link("Blend", "Image", "Out", "Image")
    screen = compile_document(mix.document(), "houdini").code.code
    assert 'nb_create(net, "screen"' in screen
    assert 'nb_create(net, "over"' not in screen
    assert 'nb_create(net, "blend"' in screen
    unknown = TreeBuilder("Odd", TreeKind.COMPOSITOR)
    unknown.node("Image", "CompositorNodeImage", outputs=[socket("Image", COLOR, output=True)])
    unknown.node(
        "Odd",
        "CompositorNodeMixRGB",
        inputs=[socket("Fac", F, 1.0), socket("Image", COLOR), socket("Image_001", COLOR)],
        outputs=[socket("Image", COLOR, output=True)],
        blend_type="DODGE",
    )
    unknown.node("Out", "CompositorNodeComposite", inputs=[socket("Image", COLOR)], outputs=[], is_active_output=True)
    unknown.link("Image", "Image", "Odd", "Image").link("Odd", "Image", "Out", "Image")
    odd = compile_document(unknown.document(), "houdini").code.code
    assert 'nb_create(net, "over"' not in odd
    assert 'nb_create(net, "null"' in odd
    viewer = TreeBuilder("View", TreeKind.COMPOSITOR)
    viewer.node("Image", "CompositorNodeImage", outputs=[socket("Image", COLOR, output=True)])
    viewer.node("View", "CompositorNodeViewer", inputs=[socket("Image", COLOR)], outputs=[])
    viewer.link("Image", "Image", "View", "Image")
    viewed = compile_document(viewer.document(), "houdini")
    assert "COMPOSITE_OUTPUT" not in {op.kind for op in viewed.semantic.ops.values()}
    assert "setDisplayFlag" not in viewed.code.code
    grade = TreeBuilder("Grade", TreeKind.COMPOSITOR)
    grade.node(
        "Grade",
        "CompositorNodeColorBalance",
        inputs=[
            socket("Image", COLOR),
            socket("Base Lift", F, 0.0, name="Base Lift"),
            socket("Color Lift", COLOR, [1.2, 1.0, 0.8], name="Color Lift"),
            socket("Base Gamma", F, 1.0, name="Base Gamma"),
            socket("Color Gamma", COLOR, [1, 1, 1], name="Color Gamma"),
            socket("Base Gain", F, 1.0, name="Base Gain"),
            socket("Color Gain", COLOR, [1, 1, 1], name="Color Gain"),
        ],
        outputs=[socket("Image", COLOR, output=True)],
    )
    grade.node("Image", "CompositorNodeImage", outputs=[socket("Image", COLOR, output=True)])
    grade.node("Out", "CompositorNodeComposite", inputs=[socket("Image", COLOR)], outputs=[], is_active_output=True)
    grade.link("Image", "Image", "Grade", "Image").link("Grade", "Image", "Out", "Image")
    graded = compile_document(grade.document(), "unreal")
    assert "Vector4(0.2, 0.0, -0.2" in graded.code.code
    houdini_grade = compile_document(grade.document(), "houdini")
    assert '"lift", (1.2, 1.0, 0.8)' in houdini_grade.code.code


def test_houdini_lift_is_combined_not_the_unreal_offset():
    grade = TreeBuilder("Grade52", TreeKind.COMPOSITOR)
    grade.node(
        "Grade",
        "CompositorNodeColorBalance",
        inputs=[
            socket("Image", COLOR),
            socket("Base Lift", F, 0.0, name="Base Lift"),
            socket("Color Lift", COLOR, [0.98, 1.0, 1.04], name="Color Lift"),
            socket("Base Gamma", F, 1.0, name="Base Gamma"),
            socket("Color Gamma", COLOR, [1, 1, 1], name="Color Gamma"),
            socket("Base Gain", F, 1.0, name="Base Gain"),
            socket("Color Gain", COLOR, [1, 1, 1], name="Color Gain"),
        ],
        outputs=[socket("Image", COLOR, output=True)],
    )
    grade.node("Image", "CompositorNodeImage", outputs=[socket("Image", COLOR, output=True)])
    grade.node("Out", "CompositorNodeComposite", inputs=[socket("Image", COLOR)], outputs=[], is_active_output=True)
    grade.link("Image", "Image", "Grade", "Image").link("Grade", "Image", "Out", "Image")
    houdini = compile_document(grade.document(), "houdini")
    unreal = compile_document(grade.document(), "unreal")
    assert '"lift", (0.98, 1.0, 1.04)' in houdini.code.code
    assert '"lift", (-0.02, 0.0, 0.04)' not in houdini.code.code
    assert "Vector4(-0.02, 0.0, 0.04, 0.0)" in unreal.code.code
    holder = TreeBuilder("Hold", TreeKind.COMPOSITOR)
    holder.node("Image", "CompositorNodeImage", outputs=[socket("Image", COLOR, output=True)])
    holder.node("Mystery", "CompositorNodeCustom", inputs=[socket("Color", COLOR)], outputs=[socket("Image", COLOR, output=True)])
    holder.node("Out", "CompositorNodeComposite", inputs=[socket("Image", COLOR)], outputs=[], is_active_output=True)
    holder.link("Image", "Image", "Mystery", "Color").link("Mystery", "Image", "Out", "Image")
    held = compile_document(holder.document(), "houdini").code.code
    assert "setInput" in held


def test_several_colour_outputs_get_one_display_flag():
    builder = TreeBuilder("Passes", TreeKind.COMPOSITOR)
    builder.interface("Beauty", "Beauty", "OUTPUT", COLOR)
    builder.interface("Diffuse", "Diffuse", "OUTPUT", COLOR)
    builder.interface("Glossy", "Glossy", "OUTPUT", COLOR)
    builder.group_io()
    result = compile_document(builder.document(), "houdini")
    outputs = [op for op in result.semantic.ops.values() if op.kind == "COMPOSITE_OUTPUT"]
    assert [op.name for op in outputs] == ["Beauty", "Diffuse", "Glossy"]
    assert [op.name for op in outputs if op.params.get("display")] == ["Beauty"]
    assert result.code.code.count("setDisplayFlag(True)") == 1

    image = TreeBuilder("ImagePass", TreeKind.COMPOSITOR)
    image.interface("Beauty", "Beauty", "OUTPUT", COLOR)
    image.interface("Image", "Image", "OUTPUT", COLOR)
    image.group_io()
    preferred = compile_document(image.document(), "houdini")
    shown = [op.name for op in preferred.semantic.ops.values() if op.kind == "COMPOSITE_OUTPUT" and op.params.get("display")]
    assert shown == ["Image"]
    assert preferred.code.code.count("setDisplayFlag(True)") == 1


def test_pcg_missing_source_connects_the_input():
    builder = geometry_passthrough("CubeScatter")
    builder.node("Cube", "GeometryNodeMeshCube", inputs=[socket("Size", V, [1, 1, 1])], outputs=[socket("Mesh", G, output=True)])
    builder.node(
        "Scatter",
        "GeometryNodeDistributePointsOnFaces",
        inputs=[socket("Mesh", G), socket("Density", F, 2.0)],
        outputs=[socket("Points", DataType.POINTS, output=True)],
        distribute_method="RANDOM",
    )
    builder.link("Cube", "Mesh", "Scatter", "Mesh").link("Scatter", "Points", "Group Output", "Socket_1")
    result = compile_document(builder.document(), "unreal")
    assert "unreal.missing_source" in _codes(result)
    assert "input_node" in result.code.code and "nb_edge" in result.code.code


def test_inlined_groups_and_unused_inputs_are_honest():
    group = TreeBuilder("Slab", is_group=True)
    group.interface("Socket_0", "Geometry", "INPUT", G).interface("Socket_1", "Geometry", "OUTPUT", G).group_io()
    group.node(
        "Move",
        "GeometryNodeTransform",
        inputs=[socket("Geometry", G), socket("Translation", V, [0, 0, 1]), socket("Rotation", V, [0, 0, 0]), socket("Scale", V, [1, 1, 1])],
        outputs=[socket("Geometry", G, output=True)],
    )
    group.link("Group Input", "Socket_0", "Move", "Geometry").link("Move", "Geometry", "Group Output", "Socket_1")
    root = TreeBuilder("Root")
    root.interface("Socket_0", "Geometry", "INPUT", G)
    root.interface("Socket_extra", "Spare", "INPUT", G)
    root.interface("Socket_1", "Geometry", "OUTPUT", G)
    root.group_io()
    node = root.node("Use", "GeometryNodeGroup", inputs=[socket("Socket_0", G)], outputs=[socket("Socket_1", G, output=True)])
    node.group_tree = "Slab"
    root.link("Group Input", "Socket_0", "Use", "Socket_0").link("Use", "Socket_1", "Group Output", "Socket_1")
    result = compile_document(root.document(group.tree), "unreal")
    assert any(entry.name.endswith("(inlined)") for entry in result.report.entries)
    assert not any(entry.kind == "GEOMETRY_INPUT" and "Spare" in entry.name for entry in result.report.entries)
