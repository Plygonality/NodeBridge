"""Rewrite-pass pipeline tests."""

from __future__ import annotations

from nodebridge.core.graph import IRGraph
from nodebridge.core.node import IRNode
from nodebridge.core.passes import IdentityPass, PassPipeline


class RenamePass:
    name = "rename"

    def apply(self, graph: IRGraph) -> IRGraph:
        clone = IRGraph(id=graph.id, name=graph.name + "_rewritten", system=graph.system)
        for node in graph.nodes.values():
            clone.add_node(node)
        return clone


def test_pipeline_runs_in_order() -> None:
    graph = IRGraph(id="g", name="raw")
    graph.add_node(IRNode(id="n1", operation="math.add"))
    pipeline = PassPipeline([IdentityPass(), RenamePass()])
    result = pipeline.run(graph)
    assert result.name == "raw_rewritten"
    assert "n1" in result.nodes


def test_empty_pipeline_is_identity() -> None:
    graph = IRGraph(id="g", name="raw")
    assert PassPipeline().run(graph) is graph
