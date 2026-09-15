"""IR document schema: the versioned envelope around a graph."""

from __future__ import annotations

from dataclasses import dataclass, field

from nodebridge.core.graph import IRGraph
from nodebridge.core.metadata import Provenance
from nodebridge.ir.versioning import IR_VERSION, PACKAGE_VERSION


@dataclass
class IRDocument:
    """Versioned interchange document wrapping a single root graph."""

    graph: IRGraph
    source: Provenance = field(default_factory=Provenance)
    nodebridge_version: str = PACKAGE_VERSION
    ir_version: str = IR_VERSION

    def __post_init__(self) -> None:
        if not self.nodebridge_version:
            raise ValueError("nodebridge_version must be non-empty")
        if not self.ir_version:
            raise ValueError("ir_version must be non-empty")
        if not self.source.application and self.graph.provenance.application:
            self.source = self.graph.provenance
