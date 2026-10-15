"""SOP construction model used by Houdini translators.

Translators append nodes. The script renderer turns those nodes into
``hou`` Python. Nothing in this module imports ``hou``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nodebridge.common.names import sanitize_identifier
from nodebridge.compiler.evaluate import Expr, as_constant, trace_input
from nodebridge.ir.semantic import Operation, SemanticGraph
from nodebridge.translation.confidence import Classification, Confidence
from nodebridge.translation.registry import Translator


@dataclass
class SopNode:
    var: str
    node_type: str
    name: str
    op_id: str
    inputs: list[str | None] = field(default_factory=list)
    parms: list[tuple[str, object]] = field(default_factory=list)
    parm_tuples: list[tuple[str, tuple]] = field(default_factory=list)
    expressions: list[tuple[str, str]] = field(default_factory=list)
    snippet: str | None = None
    comment: str | None = None
    display: bool = False
    render: bool = False


@dataclass
class SpareParm:
    kind: str
    name: str
    label: str
    default: object


@dataclass
class SubnetNode:
    var: str
    name: str
    op_id: str
    inputs: list[str | None]
    inner_lines: list[str]
    comment: str | None = None


class HoudiniBuild:
    """Accumulates a SOP network for one semantic graph."""

    def __init__(self, graph: SemanticGraph, options, *, container: str = "container", inside_subnet: bool = False) -> None:
        self.graph = graph
        self.options = options
        self.target = "houdini"
        self.container = container
        self.inside_subnet = inside_subnet
        self.nodes: list[SopNode | SubnetNode] = []
        self.notes: list[str] = []
        self.spares: list[SpareParm] = []
        self.classifications: dict[str, Classification] = {}
        self.output_of: dict[tuple[str, str], str] = {}
        self.prelude: list[str] = []
        self._index = 0

    def var(self, hint: str) -> str:
        self._index += 1
        return f"{sanitize_identifier(hint, fallback='node')}_{self._index}"

    def node_name(self, operation: Operation) -> str:
        if self.options.preserve_names:
            return sanitize_identifier(operation.name or operation.kind.value)
        return sanitize_identifier(operation.kind.value)

    def classify(self, operation: Operation, spec: Translator, **overrides) -> Classification:
        classification = spec.classification()
        if "confidence" in overrides and overrides["confidence"] is not None:
            classification.confidence = overrides["confidence"]
        if overrides.get("explanation"):
            classification.explanation = overrides["explanation"]
        if overrides.get("implementation"):
            classification.implementation = overrides["implementation"]
        if overrides.get("limitations") is not None:
            classification.limitations = tuple(overrides["limitations"])
        if overrides.get("fallback") is not None:
            classification.fallback = overrides["fallback"]
        if classification.confidence is not Confidence.UNSUPPORTED and not self.options.strictness.allows(classification.confidence):
            classification.emitted = False
            classification.fallback = (
                f"Passthrough only. Translation strictness is {self.options.strictness.value}."
            )
        self.classifications[operation.id] = classification
        return classification

    def marker(self, operation: Operation) -> str:
        classification = self.classifications[operation.id]
        source = ", ".join(operation.source.node_types) or "semantic"
        lines = [
            f"# operation: {operation.id} kind={operation.kind.value} confidence={classification.confidence.value}",
            f"# source: {source}",
            f"# {classification.explanation}",
        ]
        if self.options.debug_output:
            lines.append(f"# parameters: {operation.parameters!r}")
        return "\n".join(lines)

    def note(self, operation: Operation) -> None:
        self.notes.append(self.marker(operation))

    def emit_unsupported(self, operation: Operation, reason: str) -> None:
        self.passthrough(operation, reason)

    def passthrough(self, operation: Operation, reason: str) -> None:
        source = self.first_geometry(operation)
        var = self.var(operation.name or "unsupported")
        node = SopNode(
            var=var,
            node_type="null",
            name=self.node_name(operation),
            op_id=operation.id,
            inputs=[source] if source else [],
            comment=reason,
        )
        self.add(node)

    def add(self, node: SopNode | SubnetNode, port: str = "*") -> None:
        self.nodes.append(node)
        self.output_of[(node.op_id, port)] = node.var
        self.output_of[(node.op_id, "*")] = node.var

    def bind(self, operation_id: str, var: str, port: str = "*") -> None:
        self.output_of[(operation_id, port)] = var
        self.output_of.setdefault((operation_id, "*"), var)

    def first_geometry(self, operation: Operation) -> str | None:
        for edge in self.graph.incoming(operation.id):
            found = self._geometry_from_edge(edge.from_operation, edge.from_port)
            if found:
                return found
        return None

    def geometry(self, operation: Operation, port: str) -> str | None:
        edge = self.graph.edge_to(operation.id, port)
        if edge is None:
            return None
        return self._geometry_from_edge(edge.from_operation, edge.from_port)

    def _geometry_from_edge(self, operation_id: str, port: str) -> str | None:
        source = self.graph.try_get(operation_id)
        if source is None:
            return None
        socket = source.outputs.get(port)
        if socket is not None and socket.role != "geometry":
            return None
        return self.output_of.get((operation_id, port)) or self.output_of.get((operation_id, "*"))

    def value(self, operation: Operation, port: str, default=None):
        """Return ``(mode, payload)`` where mode is const, exposed, or expr."""

        expr = trace_input(self.graph, operation, port)
        if expr.op == "exposed":
            return ("exposed", expr)
        if expr.op == "const":
            return ("const", expr.args[0] if expr.args[0] is not None else default)
        constant = as_constant(expr)
        if constant is not None and not _contains(expr, {"attr", "random", "noise", "voronoi", "exposed", "spatial_noise_mask", "opaque"}):
            return ("const", constant)
        return ("expr", expr)


def _contains(expr: Expr, ops: set[str]) -> bool:
    if expr.op in ops:
        return True
    return any(isinstance(arg, Expr) and _contains(arg, ops) for arg in expr.args)
