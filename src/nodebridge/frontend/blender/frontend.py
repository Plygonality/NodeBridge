"""The Blender :class:`SourceFrontend`."""

from __future__ import annotations

from typing import Any

from ...compiler.diagnostics import DiagnosticBag
from ...ir.graph import GraphDocument
from ...ir.semantic import SemanticGraph
from ..base import SourceFrontend, register_frontend
from .lifting import BlenderLifter
from .parser import parse_document


class BlenderFrontend(SourceFrontend):
    id = "blender"
    display_name = "Blender"
    coordinate_system = "blender"

    def parse(self, source: Any, **options: Any) -> GraphDocument:
        return parse_document(source, **options)

    def lift(self, document: GraphDocument, diagnostics: DiagnosticBag) -> SemanticGraph:
        return BlenderLifter(document, diagnostics).lift()


register_frontend(BlenderFrontend())
