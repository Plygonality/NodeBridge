"""Semantic translation entry points.

``translate_graph`` now compiles through the host-plugin pipeline instead
of raising a Milestone 1 stub error.
"""

from __future__ import annotations

from nodebridge.compiler.pipeline import CompilationResult, compile_graph
from nodebridge.core.graph import IRGraph
from nodebridge.core.passes import PassPipeline
from nodebridge.translators.registry import TranslationRegistry


def translate_graph(
    graph: IRGraph,
    target: str,
    *,
    registry: TranslationRegistry | None = None,
    pipeline: PassPipeline | None = None,
    generate: bool = False,
) -> CompilationResult:
    """Translate *graph* toward *target* using the semantic compiler.

    *registry* and *pipeline* are retained for call-site compatibility.
    Host mappings come from the host plugin, not from a pairwise table.
    """
    _ = (registry, pipeline)
    return compile_graph(graph, target, generate=generate)
