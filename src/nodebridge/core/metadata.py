"""Generic provenance and presentation metadata.

Source-application identifiers live here so the IR can be traced back to
the originating graph. UI fields are never used to decide translation
semantics. Provenance must never be used to fake equivalent behavior.
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
    extracted_at: str = ""
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
class TranslationEvent:
    """One recorded translation step for round-trip diagnostics.

    Stored on :class:`Metadata` when non-empty. Never used to invent
    semantics that were not actually preserved.
    """

    stage: str
    host: str = ""
    fidelity: str = ""
    note: str = ""
    native_type: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"stage": self.stage}
        if self.host:
            payload["host"] = self.host
        if self.fidelity:
            payload["fidelity"] = self.fidelity
        if self.note:
            payload["note"] = self.note
        if self.native_type:
            payload["native_type"] = self.native_type
        if self.extra:
            payload["extra"] = dict(self.extra)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TranslationEvent:
        return cls(
            stage=str(data.get("stage") or ""),
            host=str(data.get("host") or ""),
            fidelity=str(data.get("fidelity") or ""),
            note=str(data.get("note") or ""),
            native_type=str(data.get("native_type") or ""),
            extra=dict(data.get("extra") or {}),
        )


@dataclass
class Metadata:
    """Bundle of provenance, UI hints, and free-form extra data."""

    provenance: Provenance = field(default_factory=Provenance)
    ui: UIHints = field(default_factory=UIHints)
    mapping: SourceMapping = field(default_factory=SourceMapping)
    extra: dict[str, Any] = field(default_factory=dict)
    history: list[TranslationEvent] = field(default_factory=list)
