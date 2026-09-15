"""Generic provenance and presentation metadata.

Source-application identifiers live here so the IR can be traced back to
the originating graph. UI fields are never used to decide translation
semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Provenance:
    """Where an IR object came from, independent of any one application."""

    application: str = ""
    application_version: str = ""
    graph_system: str = ""
    original_type: str = ""
    original_name: str = ""
    original_label: str = ""
    original_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class UIHints:
    """Non-semantic layout information preserved for reconstruction and debug."""

    position: tuple[float, float] | None = None
    width: float | None = None
    label: str = ""
    muted: bool = False
    frame_id: str | None = None
    collapsed: bool = False
    color: tuple[float, float, float] | None = None


@dataclass
class SourceMapping:
    """Traceability between a source node, an IR node, and generated targets.

    Target IDs are empty until a backend produces a graph fragment.
    """

    source_node_id: str = ""
    ir_node_id: str = ""
    target_nodes: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Metadata:
    """Bundle of provenance, UI hints, and free-form extra data."""

    provenance: Provenance = field(default_factory=Provenance)
    ui: UIHints = field(default_factory=UIHints)
    mapping: SourceMapping = field(default_factory=SourceMapping)
    extra: dict[str, Any] = field(default_factory=dict)
