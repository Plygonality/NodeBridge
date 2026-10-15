"""Source frontend abstraction.

A frontend turns a source application's node system into Graph IR
(``parse``) and lifts Graph IR into Semantic IR (``lift``). Blender is
the only implemented frontend; Houdini or Unreal frontends would subclass
:class:`SourceFrontend` and register their own lifters, which makes
NodeBridge bidirectional without changing the compiler or backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..compiler.diagnostics import DiagnosticBag
from ..ir.graph import GraphDocument
from ..ir.semantic import SemanticGraph


class SourceFrontend(ABC):
    id: str = ""
    display_name: str = ""
    coordinate_system: str = "blender"

    @abstractmethod
    def parse(self, source: Any, **options: Any) -> GraphDocument:
        """Read a live source object into Graph IR."""

    @abstractmethod
    def lift(self, document: GraphDocument, diagnostics: DiagnosticBag) -> SemanticGraph:
        """Translate Graph IR into Semantic IR."""


_FRONTENDS: dict[str, SourceFrontend] = {}


def register_frontend(frontend: SourceFrontend) -> SourceFrontend:
    _FRONTENDS[frontend.id] = frontend
    return frontend


def get_frontend(frontend_id: str) -> SourceFrontend:
    if frontend_id not in _FRONTENDS:
        from . import blender  # noqa: F401  (registers the Blender frontend)
    return _FRONTENDS[frontend_id]
