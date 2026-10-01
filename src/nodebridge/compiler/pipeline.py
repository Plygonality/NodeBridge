"""The NodeBridge compiler pipeline.

::

    Blender node tree --parse--> Graph IR --validate/normalize--> lift --> Semantic IR
        --> backend.prepare (subgraph policy) --> rewrite rules --> dead-op elimination
        --> backend.lower --> parameter role inference --> classification (capabilities)
        --> backend.generate --> script validation --> generated code + report
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ..backend.base import GeneratedCode
from ..backend.registry import get_backend
from ..common.units import ValueRole
from ..frontend.base import get_frontend
from ..ir.graph import GraphDocument, TreeKind
from ..ir.operations import get_operation
from ..ir.semantic import Param, SemanticGraph, SemanticOp
from ..ir.validation import validate_document, validate_semantic
from ..translation.confidence import Classification, Strictness
from ..translation.fallback import TranslationFallbackProvider
from .diagnostics import DiagnosticBag, Severity
from .report import ReportEntry, TranslationReport
from .rewrite import RewriteEngine, eliminate_dead_operations


@dataclass
class CompileOptions:
    strictness: Strictness = Strictness.ALLOW_APPROXIMATE
    include_comments: bool = True
    preserve_names: bool = True
    organize_graph: bool = True
    embed_metadata: bool = True
    deterministic_random: bool = True
    debug: bool = False
    include_materials: bool = True


@dataclass
class CompilationResult:
    document: GraphDocument
    target: str
    options: CompileOptions
    semantic: SemanticGraph
    context: str
    report: TranslationReport
    diagnostics: DiagnosticBag
    classifications: dict[tuple[str, str], Classification] = field(default_factory=dict)
    blocked: set[tuple[str, str]] = field(default_factory=set)
    code: GeneratedCode | None = None
    materials: dict[str, "CompilationResult"] = field(default_factory=dict)

    def classification(self, graph: SemanticGraph, op: SemanticOp) -> Classification:
        return self.classifications[(graph.name, op.id)]

    def is_blocked(self, graph: SemanticGraph, op: SemanticOp) -> bool:
        return (graph.name, op.id) in self.blocked

    @property
    def ok(self) -> bool:
        return not self.diagnostics.errors


PASSTHROUGH_ROLES = {"ADD", "SUBTRACT", "MINIMUM", "MAXIMUM", "MULTIPLY", "DIVIDE", "SNAP", "ABSOLUTE"}


def infer_parameter_roles(graph: SemanticGraph) -> None:
    """Give unit-less parameters the role of the ports they feed (e.g. LENGTH)."""
    for parameter in graph.parameters:
        if parameter.role not in (ValueRole.SCALAR, ValueRole.DIRECTION):
            continue
        role = _consumer_role(graph, Param(parameter.key), depth=0)
        if role is not None:
            parameter.role = role
    for sub in graph.subgraphs.values():
        infer_parameter_roles(sub)


def _consumer_role(graph: SemanticGraph, value, depth: int) -> ValueRole | None:
    if depth > 3:
        return None
    for op in graph.ops.values():
        for name, item in op.inputs.items():
            if item != value:
                continue
            spec = get_operation(op.kind)
            port = spec.input(name) if spec else None
            if op.kind == "MATH" and op.params.get("operation") in PASSTHROUGH_ROLES:
                from ..ir.semantic import Link

                inner = _consumer_role(graph, Link(op.id, "value"), depth + 1)
                if inner is not None:
                    return inner
            if port is not None and port.role not in (ValueRole.SCALAR, ValueRole.FACTOR, ValueRole.INTEGER, ValueRole.BOOLEAN):
                return port.role
    return None


def analyze(
    document: GraphDocument,
    target: str,
    options: CompileOptions | None = None,
    *,
    frontend: str = "blender",
    fallback: TranslationFallbackProvider | None = None,
) -> CompilationResult:
    options = options or CompileOptions()
    diagnostics = DiagnosticBag()
    diagnostics.extend(validate_document(document))
    backend = get_backend(target)
    semantic = get_frontend(frontend).lift(document, diagnostics)
    diagnostics.extend(validate_semantic(semantic))
    backend.validate(semantic, diagnostics)
    semantic = backend.prepare(semantic, diagnostics)
    RewriteEngine().run(semantic, diagnostics)
    eliminate_dead_operations(semantic, diagnostics)
    semantic = backend.lower(semantic, diagnostics)
    infer_parameter_roles(semantic)
    for item in validate_semantic(semantic):
        if item.severity == Severity.ERROR:
            item.code = "compiler." + item.code
            diagnostics.append(item)
    context = backend.context_for(semantic.kind) or ""
    result = CompilationResult(
        document=document,
        target=target,
        options=options,
        semantic=semantic,
        context=context,
        report=None,  # type: ignore[arg-type]
        diagnostics=diagnostics,
    )
    entries: list[ReportEntry] = []
    for graph, op in _ordered_walk(semantic):
        classification = backend.classify(op, graph, context)
        key = (graph.name, op.id)
        result.classifications[key] = classification
        blocked = not classification.confidence.allowed_by(options.strictness) and classification.confidence.rank < 3
        if blocked:
            result.blocked.add(key)
        if _reportable(op):
            suggestion = ""
            if fallback is not None and classification.confidence.rank == 3:
                found = fallback.suggest(op, graph, target)
                suggestion = found.summary if found else ""
            entries.append(ReportEntry(graph.name, op.id, op.kind, op.display_name, op.source.types, classification, blocked, suggestion))
    source = document.source
    result.report = TranslationReport(
        source_kind=semantic.kind.label,
        source_name=source.get("display_name") or document.root,
        source_application=source.get("application", ""),
        target=target,
        target_label=f"{backend.display_name} ({backend.context_label(context)})",
        node_count=document.node_count(),
        entries=entries,
        diagnostics=list(diagnostics),
        strictness=options.strictness.value,
    )
    if options.include_materials and semantic.kind == TreeKind.GEOMETRY and backend.context_for(TreeKind.SHADER):
        for name, tree_name in (document.source.get("materials") or {}).items():
            if tree_name not in document.trees:
                continue
            sub_document = material_document(document, tree_name, name)
            sub = analyze(sub_document, target, replace(options, include_materials=False), frontend=frontend, fallback=fallback)
            result.materials[name] = sub
            result.report.entries.extend(sub.report.entries)
            result.report.diagnostics.extend(d for d in sub.diagnostics if d.severity != Severity.INFO)
    return result


def material_document(document: GraphDocument, tree_name: str, material: str) -> GraphDocument:
    trees = {name: tree for name, tree in document.trees.items() if tree.kind == TreeKind.SHADER and (name == tree_name or tree.is_group)}
    source = {k: v for k, v in document.source.items() if k in ("application", "unit_scale", "fps")}
    source.update(display_name=material, material=material)
    return GraphDocument(root=tree_name, trees=trees, source=source)


def _ordered_walk(graph: SemanticGraph):
    for op in graph.topological_order():
        yield graph, op
    for sub in graph.subgraphs.values():
        yield from _ordered_walk(sub)


def _reportable(op: SemanticOp) -> bool:
    return not op.name.endswith("(implicit)")


def generate(result: CompilationResult) -> CompilationResult:
    backend = get_backend(result.target)
    if backend.context_for(result.semantic.kind) is None:
        return result
    result.code = backend.generate(result)
    for problem in backend.validate_script(result.code.code):
        result.diagnostics.append(problem)
        result.report.diagnostics.append(problem)
    return result


def compile_document(document: GraphDocument, target: str, options: CompileOptions | None = None, **kwargs) -> CompilationResult:
    return generate(analyze(document, target, options, **kwargs))
