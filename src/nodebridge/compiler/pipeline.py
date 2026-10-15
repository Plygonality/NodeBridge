"""Compile a Blender node tree into a target script and a report.

    Blender node tree
        -> parser
        -> graph IR
        -> dependency analysis
        -> semantic IR
        -> normalization
        -> capability classification inside the backend
        -> generated code
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nodebridge.backend.houdini.backend import HoudiniBackend
from nodebridge.backend.unreal.backend import UnrealBackend
from nodebridge.compiler.analyzer import GraphAnalysis, analyze
from nodebridge.compiler.diagnostics import Diagnostic, Report, build_report
from nodebridge.compiler.normalize import normalize
from nodebridge.compiler.options import CompileOptions
from nodebridge.compiler.validate import validate_script, validate_semantic
from nodebridge.frontend.blender.frontend import BlenderFrontend
from nodebridge.ir.graph import GraphSystem, NodeTree
from nodebridge.ir.semantic import SemanticGraph
from nodebridge.translation.confidence import TranslationRecord

_BACKENDS = {
    "houdini": HoudiniBackend,
    "unreal": UnrealBackend,
    "unreal_engine_5": UnrealBackend,
}


@dataclass
class CompileResult:
    """Everything the UI and the CLI show after Generate."""

    tree: NodeTree
    analysis: GraphAnalysis
    semantic: SemanticGraph
    code: str
    records: list[TranslationRecord]
    report: Report
    target: str
    options: CompileOptions
    issues: list[str] = field(default_factory=list)

    @property
    def diagnostics(self) -> list[Diagnostic]:
        return self.report.diagnostics


def compile_source(source: Any, target: str, options: CompileOptions | None = None, *, system: GraphSystem | None = None) -> CompileResult:
    """Parse a duck-typed or live Blender node tree and compile it."""

    tree = BlenderFrontend().parse(source, system=system)
    return compile_tree(tree, target, options)


def compile_tree(tree: NodeTree, target: str, options: CompileOptions | None = None) -> CompileResult:
    """Compile graph IR that has already been parsed."""

    selected = _normalize_target(target)
    active = options or CompileOptions()
    analysis = analyze(tree)
    semantic = BlenderFrontend().lower(tree)
    semantic = normalize(semantic, active)
    issues = validate_semantic(semantic)
    backend = _BACKENDS[selected]()
    code, records = backend.generate(semantic, active)
    script_issues = validate_script(code, records, selected)
    issues.extend(script_issues)
    report = build_report(tree, analysis, semantic, records, target=selected, script_issues=script_issues)
    return CompileResult(
        tree=tree,
        analysis=analysis,
        semantic=semantic,
        code=code,
        records=records,
        report=report,
        target=selected,
        options=active,
        issues=issues,
    )


def _normalize_target(target: str) -> str:
    key = (target or "").strip().lower().replace(" ", "_")
    if key in {"unreal_engine_5", "ue5", "unreal"}:
        return "unreal"
    if key in {"houdini", "houdini_python"}:
        return "houdini"
    known = ", ".join(sorted({"houdini", "unreal"}))
    raise ValueError(f"Unknown target {target!r}. Known targets: {known}.")
