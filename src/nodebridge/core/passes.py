"""Rewrite-pass protocol.

Passes transform an IR graph into another IR graph. Milestone 1 only
defines the pipeline; concrete optimizations land in later milestones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from nodebridge.core.graph import IRGraph


class RewritePass(Protocol):
    """A named IR transformation."""

    name: str

    def apply(self, graph: IRGraph) -> IRGraph:
        """Return a (possibly new) graph derived from *graph*."""
        ...


@dataclass
class IdentityPass:
    """No-op pass. Useful as a pipeline placeholder and test double."""

    name: str = "identity"

    def apply(self, graph: IRGraph) -> IRGraph:
        return graph


@dataclass
class PassPipeline:
    """Ordered sequence of rewrite passes.

    Future work can insert constant folding, dead-node elimination, type
    normalization, implicit conversion insertion, operation fusion,
    unsupported-operation lowering, and target-specific optimization
    without changing backend or adapter APIs.
    """

    passes: list[RewritePass] = field(default_factory=list)

    def add(self, rewrite_pass: RewritePass) -> None:
        self.passes.append(rewrite_pass)

    def run(self, graph: IRGraph) -> IRGraph:
        """Apply each pass in order and return the final graph."""
        current = graph
        for rewrite_pass in self.passes:
            current = rewrite_pass.apply(current)
        return current
