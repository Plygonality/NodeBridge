"""Graph validation tests."""

from __future__ import annotations

import pytest

from nodebridge.core.exceptions import ValidationError
from nodebridge.core.graph import IRGraph
from nodebridge.core.link import IRConnection
from nodebridge.core.node import IRNode
from nodebridge.core.socket import IRSocket
from nodebridge.core.types import DataType
from nodebridge.ir.validation import validate_graph
from tests.helpers import make_transform_graph


def test_valid_transform_graph_has_no_errors() -> None:
    result = validate_graph(make_transform_graph().graph)
    assert result.ok
    assert result.errors() == []


def test_missing_endpoint_is_an_error() -> None:
    graph = make_transform_graph().graph
    graph.add_connection(
        IRConnection(
            id="link_missing",
            source_node="node_missing",
            source_socket="x",
            target_node="node_xform",
            target_socket="xf_geo",
        )
    )
    result = validate_graph(graph)
    assert not result.ok
    assert any(item.code == "NB-E002" for item in result.errors())


def test_socket_direction_mismatch() -> None:
    graph = IRGraph(id="graph_dir", name="dir")
    a = IRNode(id="node_a", operation="math.add")
    b = IRNode(id="node_b", operation="math.add")
    a.add_socket(IRSocket.input("a_in", "a", DataType.FLOAT))
    b.add_socket(IRSocket.input("b_in", "b", DataType.FLOAT))
    graph.add_node(a)
    graph.add_node(b)
    graph.add_connection(
        IRConnection(
            id="bad",
            source_node="node_a",
            source_socket="a_in",
            target_node="node_b",
            target_socket="b_in",
        )
    )
    result = validate_graph(graph)
    assert any(item.code == "NB-E003" for item in result.errors())


def test_unknown_operation_is_a_warning() -> None:
    graph = IRGraph(id="graph_unk", name="unk")
    graph.add_node(IRNode(id="node_x", operation="geometry.foobar"))
    result = validate_graph(graph)
    assert result.ok
    assert any(item.code == "NB-W002" for item in result.diagnostics)


def test_type_mismatch_is_a_warning() -> None:
    graph = IRGraph(id="graph_types", name="types")
    a = IRNode(id="node_a", operation="math.add")
    b = IRNode(id="node_b", operation="geometry.join")
    a.add_socket(IRSocket.output("a_out", "value", DataType.FLOAT))
    b.add_socket(IRSocket.input("b_in", "geometry", DataType.GEOMETRY))
    graph.add_node(a)
    graph.add_node(b)
    graph.add_connection(
        IRConnection(
            id="mismatch",
            source_node="node_a",
            source_socket="a_out",
            target_node="node_b",
            target_socket="b_in",
        )
    )
    result = validate_graph(graph)
    assert result.ok
    assert any(item.code == "NB-W001" for item in result.diagnostics)


def test_missing_nested_graph_is_an_error() -> None:
    graph = IRGraph(id="graph_outer", name="outer")
    graph.add_node(
        IRNode(id="node_g", operation="graph.group", nested_graph_id="missing")
    )
    result = validate_graph(graph, raise_on_error=False)
    assert any(item.code == "NB-E010" for item in result.errors())
    with pytest.raises(ValidationError):
        validate_graph(graph, raise_on_error=True)


def test_nested_graph_cycle_is_an_error() -> None:
    outer = IRGraph(id="graph_a", name="a")
    inner = IRGraph(id="graph_a", name="loop")
    outer.add_graph(inner)
    result = validate_graph(outer)
    assert any(item.code == "NB-E006" for item in result.errors())


def test_cycle_in_data_flow_is_a_warning() -> None:
    graph = IRGraph(id="graph_cyc", name="cyc")
    a = IRNode(id="node_a", operation="math.add")
    b = IRNode(id="node_b", operation="math.add")
    a.add_socket(IRSocket.output("ao", "value", DataType.FLOAT))
    a.add_socket(IRSocket.input("ai", "value", DataType.FLOAT))
    b.add_socket(IRSocket.output("bo", "value", DataType.FLOAT))
    b.add_socket(IRSocket.input("bi", "value", DataType.FLOAT))
    graph.add_node(a)
    graph.add_node(b)
    graph.add_connection(
        IRConnection("c1", "node_a", "ao", "node_b", "bi")
    )
    graph.add_connection(
        IRConnection("c2", "node_b", "bo", "node_a", "ai")
    )
    result = validate_graph(graph)
    assert result.ok
    assert any(item.code == "NB-W003" for item in result.diagnostics)
