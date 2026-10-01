"""Subgraph (node group) handling.

Groups are kept as ``SUBGRAPH`` operations whenever the target can
express a reusable unit (Houdini subnets). A backend may ask for a group
to be inlined when the target cannot represent its interface, for
example when a Geometry Nodes group passes *fields* across its boundary.
"""

from __future__ import annotations

import copy
from typing import Callable

from ..ir.semantic import Const, GraphOutput, InputValue, Link, Param, SemanticGraph, SemanticOp
from ..ir.types import GEOMETRY_TYPES, DataType
from .diagnostics import DiagnosticBag


def has_field_interface(graph: SemanticGraph, op: SemanticOp) -> bool:
    if any(ref.field for ref in op.outputs.values()):
        return True
    for value in op.inputs.values():
        upstream = graph.resolve(value)
        if upstream is not None and isinstance(value, Link) and upstream.outputs.get(value.output) is not None and upstream.outputs[value.output].field:
            return True
    return False


def inline_subgraph(graph: SemanticGraph, op_id: str) -> None:
    op = graph.ops[op_id]
    sub = graph.subgraphs[op.params["graph"]]
    prefix = f"{op_id}__"
    by_identifier = {p.key: p.identifier for p in sub.parameters}

    def remap(value: InputValue) -> InputValue:
        if isinstance(value, tuple):
            return tuple(remap(item) for item in value)
        if isinstance(value, Param):
            identifier = by_identifier.get(value.name, value.name)
            if identifier in op.inputs:
                return op.inputs[identifier]
            parameter = sub.parameter(value.name)
            return Const(parameter.current if parameter else None, parameter.data_type if parameter else DataType.ANY)
        if isinstance(value, Link):
            inner = sub.ops.get(value.op)
            if inner is not None and inner.kind == "GEOMETRY_INPUT":
                return op.inputs.get(inner.params.get("identifier", ""), Const(None, DataType.GEOMETRY))
            return Link(prefix + value.op, value.output)
        return value

    for inner in sub.ops.values():
        if inner.kind == "GEOMETRY_INPUT":
            continue
        clone = copy.deepcopy(inner)
        clone.id = prefix + inner.id
        clone.inputs = {k: remap(v) for k, v in inner.inputs.items()}
        clone.annotations["inlined_from"] = sub.name
        if not clone.name or clone.name.endswith("(implicit)"):
            clone.name = inner.name
        graph.add(clone)
    outputs: dict[str, InputValue] = {out.name: remap(out.value) for out in sub.outputs}
    for name, value in outputs.items():
        graph.replace_uses(Link(op_id, name), value)
    for name, nested in sub.subgraphs.items():
        graph.subgraphs.setdefault(name, nested)
    graph.remove(op_id)
    if not any(o.kind == "SUBGRAPH" and o.params.get("graph") == sub.name for o in graph.ops.values()):
        graph.subgraphs.pop(sub.name, None)


def inline_where(graph: SemanticGraph, predicate: Callable[[SemanticGraph, SemanticOp], bool], diagnostics: DiagnosticBag | None = None, reason: str = "") -> int:
    """Inline every SUBGRAPH op matching ``predicate`` (recursively)."""
    count = 0
    while True:
        target = next((op for op in graph.ops.values() if op.kind == "SUBGRAPH" and predicate(graph, op)), None)
        if target is None:
            break
        if diagnostics is not None:
            diagnostics.info("subgraph.inlined", f"Node group {target.params['graph']!r} ({target.display_name}) was inlined{': ' + reason if reason else ''}.", tree=graph.name, op=target.id)
        inline_subgraph(graph, target.id)
        count += 1
    for sub in graph.subgraphs.values():
        count += inline_where(sub, predicate, diagnostics, reason)
    return count


def geometry_inputs(sub: SemanticGraph) -> list[SemanticOp]:
    return [op for op in sub.ops.values() if op.kind == "GEOMETRY_INPUT"]


def geometry_outputs(sub: SemanticGraph) -> list[GraphOutput]:
    return [out for out in sub.outputs if out.data_type in GEOMETRY_TYPES]
