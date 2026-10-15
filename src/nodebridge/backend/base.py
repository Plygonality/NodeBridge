"""Target backend abstraction.

A backend owns everything target-specific: which semantic kinds it can
translate (through the translator registry), how confident each
translation is, target-specific lowering, and code generation. Adding a
new DCC means adding a backend package that registers translators and
subclasses :class:`TargetBackend`; the compiler does not change.
"""

from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..compiler.diagnostics import Diagnostic, DiagnosticBag, Severity
from ..ir.graph import TreeKind
from ..ir.semantic import SemanticGraph, SemanticOp
from ..translation.confidence import UNSUPPORTED_DEFAULT, Classification
from ..translation.registry import REGISTRY, Translator

if TYPE_CHECKING:
    from ..compiler.pipeline import CompilationResult


@dataclass
class GeneratedCode:
    target: str
    language: str
    filename: str
    code: str
    run_instructions: str = ""
    warnings: list[str] = field(default_factory=list)


class TargetBackend(ABC):
    id: str = ""
    display_name: str = ""
    language: str = "python"
    language_label: str = "Python"
    coordinate_system: str = ""
    required_imports: tuple[str, ...] = ()
    contexts: dict[TreeKind, str] = {}

    # -- capability ------------------------------------------------------
    def context_for(self, kind: TreeKind) -> str | None:
        return self.contexts.get(kind)

    def translator(self, op: SemanticOp, context: str) -> Translator | None:
        return REGISTRY.get(self.id, context, op.kind)

    def supports(self, op: SemanticOp, context: str) -> bool:
        return self.translator(op, context) is not None

    def classify(self, op: SemanticOp, graph: SemanticGraph, context: str) -> Classification:
        item = self.translator(op, context)
        if item is None:
            if op.kind == "UNSUPPORTED_OPERATION":
                reason = op.params.get("reason", "")
                return Classification(UNSUPPORTED_DEFAULT.confidence, reason or UNSUPPORTED_DEFAULT.explanation, "placeholder", [], UNSUPPORTED_DEFAULT.fallback)
            return UNSUPPORTED_DEFAULT
        return item.classify(op, graph)

    context_labels: dict[str, str] = {}

    def context_label(self, context: str) -> str:
        return self.context_labels.get(context, context or "no backend")

    # -- pipeline hooks -----------------------------------------------------
    def prepare(self, graph: SemanticGraph, diagnostics: DiagnosticBag) -> SemanticGraph:
        """Before rewriting: decide which node groups stay reusable (default: keep all)."""
        return graph

    def lower(self, graph: SemanticGraph, diagnostics: DiagnosticBag) -> SemanticGraph:
        """After rewriting: target-specific lowering before classification (default: none)."""
        return graph

    def validate(self, graph: SemanticGraph, diagnostics: DiagnosticBag) -> None:
        if self.context_for(graph.kind) is None:
            diagnostics.error("backend.unsupported_tree", f"{self.display_name} has no backend for {graph.kind.label} trees.", target=self.id)

    @abstractmethod
    def generate(self, result: "CompilationResult") -> GeneratedCode:
        """Generate executable code for a compiled graph."""

    def generate_header(self, result: "CompilationResult") -> str:
        return ""

    def generate_footer(self, result: "CompilationResult") -> str:
        return ""

    # -- post-generation validation ----------------------------------------
    def validate_script(self, code: str) -> list[Diagnostic]:
        problems: list[Diagnostic] = []
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            return [Diagnostic(Severity.ERROR, "script.syntax", f"Generated script has a syntax error at line {exc.lineno}: {exc.msg}", target=self.id)]
        imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
        for module in self.required_imports:
            if module not in imported:
                problems.append(Diagnostic(Severity.ERROR, "script.import", f"Generated script does not import {module!r}.", target=self.id))
        if "\t" in code:
            problems.append(Diagnostic(Severity.WARNING, "script.tabs", "Generated script contains tab characters.", target=self.id))
        defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        if "build" not in defined:
            problems.append(Diagnostic(Severity.ERROR, "script.structure", "Generated script has no build() entry point.", target=self.id))
        return problems
