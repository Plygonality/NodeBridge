"""Analyze and generate without importing bpy.

The Blender operators call this module. Tests call it with duck-typed
node trees.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nodebridge.compiler.dependencies import DependencyReport, analyze_dependencies
from nodebridge.compiler.pipeline import CompilationResult, compile_graph
from nodebridge.frontend.blender.parser import parse_node_tree
from nodebridge.ir.graph_ir import NodeTree
from nodebridge.ir.schema import IRDocument
from nodebridge.translation.report import confidence_counts, format_translation_report


@dataclass
class TranslateOptions:
    """Options exposed by the N-panel."""

    target: str = "houdini"
    strictness: str = "allow_approximate"
    include_comments: bool = True
    preserve_names: bool = True
    organized_graph: bool = True
    embed_metadata: bool = True
    deterministic_random: bool = True
    debug_output: bool = False

    def as_metadata(self) -> dict[str, object]:
        return {
            "strictness": self.strictness,
            "include_comments": self.include_comments,
            "preserve_names": self.preserve_names,
            "organized_graph": self.organized_graph,
            "embed_metadata": self.embed_metadata,
            "deterministic_random": self.deterministic_random,
            "debug_output": self.debug_output,
        }


@dataclass
class SessionResult:
    """One analyze or generate pass."""

    source_name: str
    source_system: str
    target: str
    node_count: int
    operation_count: int
    counts: dict[str, int]
    warnings: list[str] = field(default_factory=list)
    report: str = ""
    code: str = ""
    tree: NodeTree | None = None
    document: IRDocument | None = None
    dependencies: DependencyReport | None = None
    compilation: CompilationResult | None = None


def analyze_source(source: object, *, system: str | None, options: TranslateOptions) -> SessionResult:
    """Parse, order, semanticize, and classify. Does not need the code text."""
    tree = parse_node_tree(source, system=system)
    return _compile(tree, options, generate=False)


def generate_source(source: object, *, system: str | None, options: TranslateOptions) -> SessionResult:
    """Analyze and emit target code."""
    tree = parse_node_tree(source, system=system)
    return _compile(tree, options, generate=True)


def generate_from_document(document: IRDocument, options: TranslateOptions, *, node_count: int | None = None) -> SessionResult:
    """Generate from semantic IR that was already analyzed."""
    document.graph.metadata.extra["nodebridge_options"] = options.as_metadata()
    compiled = compile_graph(document, _target_id(options.target), generate=True)
    counts = confidence_counts(compiled.report)
    warnings = _warnings(compiled)
    report = format_translation_report(
        compiled.report,
        source_nodes=node_count if node_count is not None else len(document.graph.nodes),
        source_name=document.graph.name,
    )
    if options.debug_output:
        report += "\nDebug: semantic operations\n"
        for node in document.graph.nodes.values():
            report += f"    {node.id} {node.operation}\n"
    return SessionResult(
        source_name=document.graph.name,
        source_system=document.graph.system.value,
        target=options.target,
        node_count=node_count if node_count is not None else len(document.graph.nodes),
        operation_count=len(compiled.report.outcomes),
        counts=counts,
        warnings=warnings,
        report=report,
        code=compiled.generated_code,
        document=document,
        compilation=compiled,
    )


def _compile(tree: NodeTree, options: TranslateOptions, *, generate: bool) -> SessionResult:
    from nodebridge.compiler.semanticize import semanticize

    dependencies = analyze_dependencies(tree)
    document = semanticize(tree)
    document.graph.metadata.extra["nodebridge_options"] = options.as_metadata()
    if dependencies.cycles:
        document.graph.metadata.extra["cycles"] = dependencies.cycles
    compiled = compile_graph(document, _target_id(options.target), generate=generate)
    counts = confidence_counts(compiled.report)
    warnings = _warnings(compiled)
    if dependencies.cycles:
        warnings.append(f"Cycle detected involving {dependencies.cycles[0][0]}")
    if dependencies.dead_nodes:
        warnings.append(f"Dead nodes: {', '.join(dependencies.dead_nodes)}")
    report = format_translation_report(
        compiled.report,
        source_nodes=len(tree.nodes),
        source_name=f"{tree.system} / {tree.name}",
    )
    if options.debug_output:
        report += "\nDebug: graph order\n"
        report += "    " + ", ".join(dependencies.order) + "\n"
    return SessionResult(
        source_name=tree.name,
        source_system=tree.system,
        target=options.target,
        node_count=len(tree.nodes),
        operation_count=len(compiled.report.outcomes),
        counts=counts,
        warnings=warnings,
        report=report,
        code=compiled.generated_code,
        tree=tree,
        document=document,
        dependencies=dependencies,
        compilation=compiled,
    )


def _warnings(compiled: CompilationResult) -> list[str]:
    warnings: list[str] = []
    for outcome in compiled.report.outcomes:
        if outcome.status.value != "exact" or outcome.operation in {
            "points.distribute",
            "random.float",
            "random.vector",
            "random.integer",
            "procedural.noise",
            "procedural.voronoi",
        }:
            label = outcome.source_type or outcome.operation
            warnings.append(f"{label}: {outcome.note or outcome.status.value}")
    return warnings


def _target_id(target: str) -> str:
    key = target.strip().lower()
    if key in {"unreal", "unreal engine 5", "ue5", "unreal_engine_5"}:
        return "unreal"
    return "houdini"
