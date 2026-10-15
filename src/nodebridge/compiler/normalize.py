"""Normalization: Blender-shaped semantic graphs become fewer, clearer operations.

Rewrite rules live in :mod:`nodebridge.compiler.rewrite`. This module is the
pipeline stage that decides whether to run them.
"""

from __future__ import annotations

from nodebridge.compiler.options import CompileOptions
from nodebridge.compiler.rewrite import apply_rewrites
from nodebridge.ir.semantic import SemanticGraph


def normalize(graph: SemanticGraph, options: CompileOptions) -> SemanticGraph:
    """Apply graph rewrite rules when pattern fusion is enabled."""

    if not options.fuse_patterns:
        graph.metadata["rewrites"] = []
        return graph
    return apply_rewrites(graph)
