"""IR data-model tests."""

from __future__ import annotations

import pytest

from nodebridge.core.graph import GraphBuilder, GraphSystem, IRGraph
from nodebridge.core.link import IRConnection
from nodebridge.core.node import IRNode
from nodebridge.core.socket import FieldKind, IRSocket, SocketDirection
from nodebridge.core.types import (
    DataType,
    TypeCompatibility,
    TypeRef,
    TypeRegistry,
    compare_types,
)
from tests.helpers import make_math_add_graph, make_transform_graph


def test_type_ref_builtin_and_custom() -> None:
    assert TypeRef.of(DataType.FLOAT).is_builtin
    assert TypeRef.of("vector3").builtin is DataType.VECTOR3
    custom = TypeRef.of("usd.token")
    assert custom.name == "usd.token"
    assert not custom.is_builtin
    assert custom.is_unknown


def test_type_registry_rejects_builtin_collision() -> None:
    registry = TypeRegistry()
    registry.register("custom.quaternion", description="Unit quaternion")
    assert registry.is_registered("custom.quaternion")
    with pytest.raises(Exception):
        registry.register("float")


def test_type_compatibility_geometry_and_numeric() -> None:
    assert (
        compare_types(TypeRef.of(DataType.FLOAT), TypeRef.of(DataType.FLOAT))
        is TypeCompatibility.IDENTICAL
    )
    assert (
        compare_types(TypeRef.of(DataType.MESH), TypeRef.of(DataType.GEOMETRY))
        is TypeCompatibility.EQUIVALENT
    )
    assert (
        compare_types(TypeRef.of(DataType.FLOAT), TypeRef.of(DataType.INTEGER))
        is TypeCompatibility.CONVERTIBLE
    )
    assert (
        compare_types(TypeRef.of(DataType.SHADER), TypeRef.of(DataType.GEOMETRY))
        is TypeCompatibility.INCOMPATIBLE
    )


def test_math_add_graph_structure() -> None:
    graph = make_math_add_graph().graph
    assert graph.name == "math_add"
    node = graph.get_node("node_add")
    assert node.operation == "math.add"
    assert set(node.inputs) == {"sock_a", "sock_b"}
    assert node.outputs["sock_out"].data_type.builtin is DataType.FLOAT
    assert node.parameters["operation"].value == "ADD"
    assert node.metadata.ui.position == (120.0, 40.0)


def test_transform_graph_connections_and_topology() -> None:
    graph = make_transform_graph().graph
    assert len(graph.nodes) == 4
    assert len(graph.connections) == 3
    order = graph.topological_order()
    assert order.index("node_in") < order.index("node_xform")
    assert order.index("node_offset") < order.index("node_xform")
    assert order.index("node_xform") < order.index("node_out")
    incoming = graph.incoming("node_xform", "xf_geo")
    assert incoming[0].source_node == "node_in"


def test_nested_graph_registration() -> None:
    builder = GraphBuilder(name="outer", system=GraphSystem.GEOMETRY)
    inner = IRGraph(id="graph_inner", name="group")
    builder.graph.add_graph(inner)
    call = builder.node("graph.group", nested_graph_id="graph_inner")
    assert call.nested_graph_id == "graph_inner"
    assert [item.id for item in builder.graph.all_graphs()] == [
        builder.graph.id,
        "graph_inner",
    ]


def test_cycle_raises_in_topological_order() -> None:
    graph = IRGraph(id="graph_cycle", name="cycle")
    a = IRNode(id="node_a", operation="math.add")
    b = IRNode(id="node_b", operation="math.add")
    a.add_socket(IRSocket.output("a_out", "value", DataType.FLOAT))
    a.add_socket(IRSocket.input("a_in", "value", DataType.FLOAT))
    b.add_socket(IRSocket.output("b_out", "value", DataType.FLOAT))
    b.add_socket(IRSocket.input("b_in", "value", DataType.FLOAT))
    graph.add_node(a)
    graph.add_node(b)
    graph.add_connection(
        IRConnection(
            id="c1",
            source_node="node_a",
            source_socket="a_out",
            target_node="node_b",
            target_socket="b_in",
        )
    )
    graph.add_connection(
        IRConnection(
            id="c2",
            source_node="node_b",
            source_socket="b_out",
            target_node="node_a",
            target_socket="a_in",
        )
    )
    with pytest.raises(ValueError, match="cycle"):
        graph.topological_order()


def test_socket_lookup_by_name() -> None:
    node = IRNode(id="node_x", operation="vector.normalize")
    node.add_socket(IRSocket.input("s1", "vector", DataType.VECTOR3))
    node.add_socket(IRSocket.output("s2", "vector", DataType.VECTOR3))
    found = node.socket_by_name("vector", SocketDirection.OUTPUT)
    assert found.id == "s2"
    assert found.field_kind is FieldKind.VALUE


def test_duplicate_node_id_rejected() -> None:
    graph = IRGraph(id="graph_dup", name="dup")
    graph.add_node(IRNode(id="node_a", operation="math.add"))
    with pytest.raises(ValueError):
        graph.add_node(IRNode(id="node_a", operation="math.subtract"))
