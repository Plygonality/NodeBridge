"""Translation registry and compatibility-analysis tests."""

from __future__ import annotations

import pytest

from nodebridge.backends.base import GraphFragment, TargetNodeSpec
from nodebridge.core.diagnostics import TranslationStatus
from nodebridge.core.exceptions import TranslationError
from nodebridge.core.node import IRNode
from nodebridge.translators.compatibility import analyse_compatibility
from nodebridge.translators.registry import (
    TranslationRegistry,
    register_translation,
    translate_node,
)
from tests.helpers import make_transform_graph


def test_register_translation_returns_fragment() -> None:
    registry = TranslationRegistry()

    @register_translation(
        source="geometry.transform",
        target="houdini",
        registry=registry,
    )
    def translate_transform(node: IRNode) -> GraphFragment:
        return GraphFragment(
            nodes=[TargetNodeSpec(id=f"{node.id}_xform", kind="sop.xform")],
            status=TranslationStatus.EXACT,
        )

    node = IRNode(id="node_0024", operation="geometry.transform")
    fragment = translate_node(node, "houdini", registry=registry)
    assert fragment.status is TranslationStatus.EXACT
    assert fragment.nodes[0].kind == "sop.xform"
    assert registry.targets_for("geometry.transform") == ["houdini"]


def test_missing_translation_raises() -> None:
    registry = TranslationRegistry()
    with pytest.raises(TranslationError):
        translate_node(IRNode(id="n", operation="math.add"), "houdini", registry=registry)


def test_compatibility_marks_unregistered_as_unsupported() -> None:
    graph = make_transform_graph().graph
    report = analyse_compatibility(graph, "houdini")
    assert report.nodes_analysed == 4
    assert report.counts()[TranslationStatus.UNSUPPORTED] == 4
    text = report.format_text()
    assert "Unsupported" in text
    assert "GeometryNodeTransform" in text
    operations = {outcome.operation for outcome in report.outcomes}
    assert "geometry.transform" in operations


def test_compatibility_uses_registered_status() -> None:
    registry = TranslationRegistry()

    @register_translation(
        source="geometry.transform",
        target="houdini",
        status=TranslationStatus.EXACT,
        registry=registry,
    )
    def _xform(node: IRNode) -> GraphFragment:
        return GraphFragment(status=TranslationStatus.EXACT)

    @register_translation(
        source="vector.add",
        target="houdini",
        status=TranslationStatus.EQUIVALENT,
        kind="compound",
        registry=registry,
    )
    def _add(node: IRNode) -> GraphFragment:
        return GraphFragment(status=TranslationStatus.EQUIVALENT)

    report = analyse_compatibility(
        make_transform_graph().graph, "houdini", translations=registry
    )
    statuses = {outcome.operation: outcome.status for outcome in report.outcomes}
    assert statuses["geometry.transform"] is TranslationStatus.EXACT
    assert statuses["vector.add"] is TranslationStatus.EQUIVALENT
    assert statuses["graph.input"] is TranslationStatus.UNSUPPORTED
