"""Graph IR, serialization, validation, dependency analysis and normalization."""

from helpers import F, G, geometry_passthrough, load_example, socket

from nodebridge.compiler.analyzer import analyze_tree, branch_points, extract_subgraph, find_cycles, topological_sort
from nodebridge.compiler.diagnostics import DiagnosticBag
from nodebridge.compiler.normalize import normalize_tree
from nodebridge.ir.graph import GraphEdge
from nodebridge.ir.serialization import dumps_graph, dumps_semantic, loads_graph, loads_semantic
from nodebridge.ir.validation import validate_document, validate_semantic


def test_example_fixtures_roundtrip_through_json():
    for name in ("scatter", "building", "shader", "compositor"):
        document = load_example(name)
        again = loads_graph(dumps_graph(document))
        assert dumps_graph(again) == dumps_graph(document)
        assert validate_document(document) == []


def test_fixture_contents_come_from_real_blender():
    document = load_example("building")
    assert document.source["application"].startswith("Blender 4.")
    assert set(document.trees) == {"BuildingGenerator", "FloorSlab"}
    slab = document.trees["FloorSlab"]
    assert slab.is_group and [s.name for s in slab.inputs] == ["Width", "Depth", "Thickness"]
    root = document.root_tree
    assert root.nodes["Floor Slab"].group_tree == "FloorSlab"
    width = next(s for s in root.inputs if s.name == "Width")
    assert width.subtype == "DISTANCE" and width.current == 10.0


def test_validation_reports_dangling_and_incompatible_links():
    builder = geometry_passthrough()
    builder.node("Value", "ShaderNodeValue", outputs=[socket("Value", F, 1.0, output=True)])
    builder.link("Value", "Value", "Group Output", "Socket_1")
    builder.tree.edges.append(GraphEdge("Missing", "X", "Group Output", "Socket_1"))
    codes = {d.code for d in validate_document(builder.document())}
    assert {"graph.incompatible_link", "graph.dangling_edge"} <= codes


def test_topological_sort_is_stable_and_detects_cycles():
    order, cyclic = topological_sort("abcd", [("a", "b"), ("b", "c"), ("a", "d")])
    assert order == ["a", "b", "d", "c"] or order == ["a", "b", "c", "d"]
    assert not cyclic
    order, cyclic = topological_sort("abc", [("a", "b"), ("b", "c"), ("c", "b")])
    assert order == ["a"] and cyclic == {"b", "c"}
    assert find_cycles("abc", [("a", "b"), ("b", "c"), ("c", "b")]) == [["b", "c"]]


def test_tree_analysis_uses_links_not_positions():
    document = load_example("scatter")
    tree = document.root_tree
    for node in tree.nodes.values():
        node.location = (0.0, 0.0)
    analysis = analyze_tree(tree)
    position = {node: index for index, node in enumerate(analysis.order)}
    for edge in tree.edges:
        assert position[edge.from_node] < position[edge.to_node]
    assert analysis.output_nodes == ["Group Output"]
    assert "Group Input" in analysis.branches


def test_dead_nodes_reroutes_and_muted_nodes_are_normalized():
    builder = geometry_passthrough()
    builder.node("Reroute", "NodeReroute", inputs=[socket("Input", G)], outputs=[socket("Output", G, output=True)])
    builder.node("Muted", "GeometryNodeTransform", inputs=[socket("Geometry", G)], outputs=[socket("Geometry", G, output=True)])
    builder.tree.nodes["Muted"].muted = True
    builder.tree.nodes["Muted"].internal_links = [("Geometry", "Geometry")]
    builder.node("Orphan", "GeometryNodeMeshCube", outputs=[socket("Mesh", G, output=True)])
    builder.link("Group Input", "Socket_0", "Reroute", "Input").link("Reroute", "Output", "Muted", "Geometry").link("Muted", "Geometry", "Group Output", "Socket_1")
    bag = DiagnosticBag()
    tree = normalize_tree(builder.tree, bag)
    assert set(tree.nodes) == {"Group Input", "Group Output"}
    assert [(e.from_node, e.to_node) for e in tree.edges] == [("Group Input", "Group Output")]
    assert {d.code for d in bag} >= {"graph.dead_node", "graph.muted_node"}


def test_branch_detection_and_subgraph_extraction():
    assert branch_points([("a", "b"), ("a", "c"), ("b", "c")]) == {"a": ["b", "c"]}
    tree = load_example("scatter").root_tree
    sub = extract_subgraph(tree, ["Place Rocks"])
    assert "Join Geometry" not in sub.nodes and "Scatter Rocks" in sub.nodes and "Rock Shape" in sub.nodes


def test_semantic_ir_serialization_roundtrip():
    from helpers import compile_example

    result = compile_example("building", "houdini")
    text = dumps_semantic(result.semantic)
    again = loads_semantic(text)
    assert dumps_semantic(again) == text
    assert validate_semantic(again) == []
