"""Semantic translation entry points.

Milestone 1 defines the pipeline shape. Concrete lowering lives in later
milestones so adapters and backends stay decoupled.
"""

from __future__ import annotations

from nodebridge.core.exceptions import TranslationError
from nodebridge.core.graph import IRGraph
from nodebridge.core.passes import PassPipeline
from nodebridge.translators.registry import TranslationRegistry


def translate_graph(
    graph: IRGraph,
    target: str,
    *,
    registry: TranslationRegistry | None = None,
    pipeline: PassPipeline | None = None,
) -> None:
    """Translate *graph* toward *target*.

    Intended flow::

        raw IR → optional rewrite pipeline → per-node registry dispatch
        → backend graph fragments → generated host script
    """
    _ = (graph, target, registry, pipeline)
    raise TranslationError(
        "Semantic translation is not implemented in Milestone 1. "
        "Use inspect/validate on a serialized IR document."
    )
