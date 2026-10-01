"""Compiler planning, lowering, and fidelity tests."""

from __future__ import annotations

from nodebridge.compiler.analysis import can_implement
from nodebridge.compiler.normalization import normalize_graph
from nodebridge.compiler.pipeline import compile_graph
from nodebridge.compiler.planning import plan_translation
from nodebridge.core.diagnostics import TranslationStatus
from nodebridge.core.graph import GraphBuilder, GraphSystem, IRGraph
from nodebridge.core.link import IRConnection
from nodebridge.core.node import IRNode
from nodebridge.core.socket import IRSocket
from nodebridge.core.types import DataType
from tests.helpers import make_scatter_ir_graph, make_transform_graph


def test_plan_is_deterministic() -> None:
    graph = make_transform_graph().graph
    first = plan_translation(graph, "houdini").as_dict()
    second = plan_translation(graph, "houdini").as_dict()
    assert first == second


def test_plan_classifies_exact_and_custom_code() -> None:
    graph = make_transform_graph().graph
    plan = plan_translation(graph, "houdini")
    by_op = {item.operation: item for item in plan.operations}
    assert by_op["geometry.transform"].fidelity is TranslationStatus.EXACT
    assert by_op["vector.add"].fidelity is TranslationStatus.CUSTOM_CODE
    assert can_implement("houdini", "geometry.transform")
    assert can_implement("houdini", "shader.principled_surface")
    assert not can_implement("houdini", "simulation.zone")


def test_one_to_many_lowering() -> None:
    builder = GraphBuilder(name="realize", system=GraphSystem.GEOMETRY)
    node = builder.node("geometry.realize_instances")
    builder.input(node, "geometry", DataType.GEOMETRY)
    builder.output(node, "geometry", DataType.GEOMETRY)
    result = compile_graph(builder.graph, "houdini")
    types = [item.type for item in result.native_graph.nodes]
    assert types == ["unpack", "convert"]
    assert result.report.outcomes[0].status is TranslationStatus.LOWERED
    assert result.native_graph.links


def test_unsupported_operation_is_visible() -> None:
    graph = IRGraph(id="graph_x", name="x")
    graph.add_node(IRNode(id="node_x", operation="simulation.zone"))
    result = compile_graph(graph, "houdini")
    assert result.report.outcomes[0].status is TranslationStatus.UNSUPPORTED
    assert result.native_graph.nodes[0].type == "nodebridge.unsupported"
    assert result.report.errors()


def test_custom_code_emits_vex() -> None:
    builder = GraphBuilder(name="math", system=GraphSystem.GEOMETRY)
    node = builder.node("math.add")
    builder.input(node, "a", DataType.FLOAT, default=1.0)
    builder.input(node, "b", DataType.FLOAT, default=2.0)
    builder.output(node, "value", DataType.FLOAT)
    result = compile_graph(builder.graph, "houdini", generate=True)
    assert result.report.outcomes[0].status is TranslationStatus.CUSTOM_CODE
    assert any("f@value =" in item.source and "+" in item.source for item in result.report.generated_code)
    assert "attribwrangle" in {item.type for item in result.native_graph.nodes}


def test_approximate_unreal_instancing() -> None:
    graph = make_scatter_ir_graph().graph
    result = compile_graph(graph, "unreal")
    statuses = {item.operation: item.status for item in result.report.outcomes}
    assert statuses["geometry.instance"] is TranslationStatus.APPROXIMATE
    assert statuses["points.distribute"] is TranslationStatus.EXACT


def test_clamp_fusion_is_many_to_one() -> None:
    graph = IRGraph(id="graph_clamp", name="clamp")
    maximum = IRNode(id="node_max", operation="math.max")
    maximum.add_socket(IRSocket.input("max_a", "a", DataType.FLOAT, default=0.2))
    maximum.add_socket(IRSocket.input("max_b", "b", DataType.FLOAT, default=0.0))
    maximum.add_socket(IRSocket.output("max_out", "value", DataType.FLOAT))
    minimum = IRNode(id="node_min", operation="math.min")
    minimum.add_socket(IRSocket.input("min_a", "a", DataType.FLOAT))
    minimum.add_socket(IRSocket.input("min_b", "b", DataType.FLOAT, default=1.0))
    minimum.add_socket(IRSocket.output("min_out", "value", DataType.FLOAT))
    graph.add_node(maximum)
    graph.add_node(minimum)
    graph.add_connection(
        IRConnection("c1", "node_max", "max_out", "node_min", "min_a")
    )
    normalized = normalize_graph(graph)
    ops = [node.operation for node in normalized.nodes.values()]
    assert ops == ["math.clamp"]


def test_constant_fold_vector_add() -> None:
    graph = make_transform_graph().graph
    normalized = normalize_graph(graph)
    assert "node_offset" not in normalized.nodes
    xform = normalized.get_node("node_xform")
    translation = xform.socket_by_name("translation")
    assert translation.default == [0.0, 0.0, 1.0]
