"""Graph rewrite framework for the Semantic IR.

A :class:`RewriteRule` pairs a :class:`Pattern` (or a custom matcher)
with an ``apply`` function. Rules are registered with
:func:`rewrite_rule` and run to a fixpoint by :class:`RewriteEngine`.
Rules recognize multi-node idioms (Distribute -> Instance -> Rotate
Instances becomes Scatter -> RandomTransform -> Instance), fold
constants, and simplify structure. They are target-independent; backend
lowering happens later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..ir.graph import TreeKind
from ..ir.semantic import Link, SemanticGraph, SemanticOp
from .diagnostics import DiagnosticBag


@dataclass
class Pattern:
    """Structural pattern over operations.

    ``inputs`` maps input names to sub-patterns (matched against the
    linked upstream operation). ``where`` is an extra predicate. Non-root
    operations must be used exactly once when ``single_use`` is set, so a
    fusion never duplicates work that other consumers rely on.
    """

    kind: str | tuple[str, ...] | None = None
    bind: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, "Pattern"] = field(default_factory=dict)
    where: Callable[[SemanticGraph, SemanticOp], bool] | None = None
    single_use: bool = True
    optional: bool = False


@dataclass
class Match:
    root: SemanticOp
    bindings: dict[str, SemanticOp]

    def __getitem__(self, key: str) -> SemanticOp:
        return self.bindings[key]

    def get(self, key: str) -> SemanticOp | None:
        return self.bindings.get(key)


def match(pattern: Pattern, graph: SemanticGraph, op: SemanticOp, *, root: bool = True) -> Match | None:
    bindings: dict[str, SemanticOp] = {}
    if not _match(pattern, graph, op, bindings, root):
        return None
    return Match(op, bindings)


def _match(pattern: Pattern, graph: SemanticGraph, op: SemanticOp, bindings: dict, root: bool) -> bool:
    kinds = (pattern.kind,) if isinstance(pattern.kind, str) else pattern.kind
    if kinds and op.kind not in kinds:
        return False
    for key, expected in pattern.params.items():
        actual = op.params.get(key)
        if callable(expected):
            if not expected(actual):
                return False
        elif actual != expected:
            return False
    if not root and pattern.single_use and graph.use_count(op.id) != 1:
        return False
    if pattern.where is not None and not pattern.where(graph, op):
        return False
    for input_name, sub in pattern.inputs.items():
        value = op.inputs.get(input_name)
        upstream = graph.resolve(value) if isinstance(value, Link) else None
        if upstream is None:
            if sub.optional:
                continue
            return False
        if not _match(sub, graph, upstream, bindings, False):
            if sub.optional:
                continue
            return False
    if pattern.bind:
        bindings[pattern.bind] = op
    return True


@dataclass
class RewriteRule:
    name: str
    description: str
    apply: Callable[[SemanticGraph, Match], bool]
    pattern: Pattern | None = None
    matcher: Callable[[SemanticGraph, SemanticOp], Match | None] | None = None
    kinds: tuple[TreeKind, ...] = (TreeKind.GEOMETRY, TreeKind.SHADER, TreeKind.COMPOSITOR)
    priority: int = 100

    def find(self, graph: SemanticGraph, op: SemanticOp) -> Match | None:
        if self.matcher is not None:
            return self.matcher(graph, op)
        if self.pattern is not None:
            return match(self.pattern, graph, op)
        return None


_RULES: list[RewriteRule] = []


def rewrite_rule(name: str, description: str, *, pattern: Pattern | None = None, kinds=None, priority: int = 100, matcher=None):
    """Register ``fn(graph, match) -> bool`` as a rewrite rule."""

    def decorator(fn: Callable[[SemanticGraph, Match], bool]):
        rule = RewriteRule(name, description, fn, pattern, matcher, tuple(kinds) if kinds else RewriteRule.kinds, priority)
        _RULES.append(rule)
        _RULES.sort(key=lambda r: r.priority)
        return fn

    return decorator


def registered_rules() -> list[RewriteRule]:
    from . import rules  # noqa: F401  (registers the built-in rules)

    return list(_RULES)


class RewriteEngine:
    def __init__(self, rules: list[RewriteRule] | None = None, *, max_iterations: int = 50) -> None:
        self.rules = rules if rules is not None else registered_rules()
        self.max_iterations = max_iterations
        self.applied: list[tuple[str, str]] = []

    def run(self, graph: SemanticGraph, diagnostics: DiagnosticBag) -> SemanticGraph:
        for sub in graph.subgraphs.values():
            self.run(sub, diagnostics)
        rules = [r for r in self.rules if graph.kind in r.kinds]
        for _ in range(self.max_iterations):
            changed = False
            for op in list(graph.topological_order()):
                if op.id not in graph.ops:
                    continue
                for rule in rules:
                    found = rule.find(graph, op)
                    if found is not None and rule.apply(graph, found):
                        self.applied.append((rule.name, op.id))
                        diagnostics.info("rewrite.applied", f"{rule.description} ({op.display_name})", tree=graph.name, op=op.id)
                        changed = True
                        break
                if changed:
                    break
            if not changed:
                break
        return graph


def remove_unused(graph: SemanticGraph, op_ids) -> None:
    """Remove operations that no longer have consumers (cascading upstream)."""
    pending = list(op_ids)
    while pending:
        op_id = pending.pop()
        if op_id in graph.ops and graph.use_count(op_id) == 0 and graph.ops[op_id].kind not in SINK_KINDS:
            deps = graph.dependencies(op_id)
            graph.remove(op_id)
            pending.extend(deps)


SINK_KINDS = {"GEOMETRY_OUTPUT", "MATERIAL_OUTPUT", "COMPOSITE_OUTPUT"}


def eliminate_dead_operations(graph: SemanticGraph, diagnostics: DiagnosticBag | None = None) -> list[str]:
    """Drop operations that cannot affect any output or sink."""
    roots = [o.value for o in graph.outputs]
    sinks = [op.id for op in graph.ops.values() if op.kind in SINK_KINDS]
    live = graph.upstream(roots) | set(sinks)
    for sink in sinks:
        live |= graph.upstream(graph.ops[sink].inputs.values())
    removed = [op_id for op_id in graph.ops if op_id not in live]
    for op_id in removed:
        op = graph.ops.pop(op_id)
        if diagnostics is not None and not op.name.endswith("(implicit)"):
            diagnostics.info("semantic.dead", f"{op.display_name} no longer contributes to the output after rewriting.", tree=graph.name, op=op_id)
    for sub in graph.subgraphs.values():
        eliminate_dead_operations(sub, diagnostics)
    return removed
