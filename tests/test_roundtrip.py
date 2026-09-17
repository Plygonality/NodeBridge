"""Semantic round-trip tests. Compare IR operations, not native topology."""

from __future__ import annotations

from nodebridge.compiler.pipeline import compile_graph, compile_native
from nodebridge.hosts.blender import BlenderFrontend
from nodebridge.hosts.houdini import HoudiniFrontend
from tests.helpers import (
    make_blender_scatter_native,
    make_houdini_scatter_native,
    make_scatter_ir_graph,
)

SCATTER_OPS = {
    "graph.input",
    "graph.output",
    "points.distribute",
    "geometry.instance",
    "geometry.realize_instances",
}


def _ops(graph) -> set[str]:
    return {node.operation for node in graph.nodes.values()}


def test_blender_native_to_ir_to_blender() -> None:
    document = BlenderFrontend().extract(make_blender_scatter_native())
    result = compile_graph(document, "blender")
    types = {node.type for node in result.native_graph.nodes}
    assert "GeometryNodeDistributePointsOnFaces" in types
    assert "GeometryNodeInstanceOnPoints" in types
    reextract = BlenderFrontend().extract(result.native_graph)
    assert SCATTER_OPS <= _ops(reextract.graph)


def test_houdini_native_to_ir_to_houdini() -> None:
    document = HoudiniFrontend().extract(make_houdini_scatter_native())
    result = compile_graph(document, "houdini")
    types = {node.type for node in result.native_graph.nodes}
    assert "scatter" in types
    assert "copytopoints" in types
    reextract = HoudiniFrontend().extract(result.native_graph)
    assert "points.distribute" in _ops(reextract.graph)
    assert "geometry.instance" in _ops(reextract.graph)


def test_blender_to_houdini_to_ir() -> None:
    result = compile_native(make_blender_scatter_native(), "houdini")
    assert "scatter" in {node.type for node in result.native_graph.nodes}
    assert "copytopoints" in {node.type for node in result.native_graph.nodes}
    recovered = HoudiniFrontend().extract(result.native_graph)
    assert SCATTER_OPS <= _ops(recovered.graph) or (
        {"points.distribute", "geometry.instance"} <= _ops(recovered.graph)
    )


def test_houdini_to_blender() -> None:
    result = compile_native(make_houdini_scatter_native(), "blender")
    types = {node.type for node in result.native_graph.nodes}
    assert "GeometryNodeDistributePointsOnFaces" in types
    assert "GeometryNodeInstanceOnPoints" in types
    recovered = BlenderFrontend().extract(result.native_graph)
    assert "points.distribute" in _ops(recovered.graph)
    assert "geometry.instance" in _ops(recovered.graph)


def test_scatter_ir_compiles_to_all_hosts() -> None:
    graph = make_scatter_ir_graph().graph
    for target in ("blender", "houdini", "unreal"):
        result = compile_graph(graph, target)
        assert result.native_graph.nodes
        assert result.report.nodes_analysed >= 6
