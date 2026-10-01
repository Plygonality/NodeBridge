"""Structural validation of Graph IR and Semantic IR."""

from __future__ import annotations

from ..compiler.diagnostics import Diagnostic, Severity
from .graph import GraphDocument, NodeTree
from .operations import get_operation
from .semantic import Const, Link, Param, SemanticGraph, iter_links
from .types import Conversion, DataType, conversion


def validate_tree(tree: NodeTree) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for edge in tree.edges:
        source = tree.nodes.get(edge.from_node)
        target = tree.nodes.get(edge.to_node)
        if source is None or target is None:
            diagnostics.append(Diagnostic(Severity.ERROR, "graph.dangling_edge", f"Link references a missing node ({edge.from_node} -> {edge.to_node}).", tree=tree.name))
            continue
        out_socket = source.output(edge.from_socket)
        in_socket = target.input(edge.to_socket)
        if out_socket is None or in_socket is None:
            diagnostics.append(
                Diagnostic(Severity.ERROR, "graph.missing_socket", f"Link {source.display_name}.{edge.from_socket} -> {target.display_name}.{edge.to_socket} references a missing socket.", tree=tree.name, nodes=[source.id, target.id])
            )
            continue
        if not edge.valid:
            diagnostics.append(Diagnostic(Severity.WARNING, "graph.invalid_link", f"Blender marks the link into {target.display_name}.{in_socket.name} as invalid; it is ignored.", tree=tree.name, nodes=[target.id]))
            continue
        if conversion(out_socket.data_type, in_socket.data_type) == Conversion.INVALID:
            diagnostics.append(
                Diagnostic(
                    Severity.ERROR,
                    "graph.incompatible_link",
                    f"Cannot connect {out_socket.data_type.value} ({source.display_name}.{out_socket.name}) to {in_socket.data_type.value} ({target.display_name}.{in_socket.name}).",
                    tree=tree.name,
                    nodes=[source.id, target.id],
                )
            )
    return diagnostics


def validate_document(document: GraphDocument) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if document.root not in document.trees:
        return [Diagnostic(Severity.ERROR, "graph.missing_root", f"Root tree {document.root!r} is missing.")]
    for tree in document.trees.values():
        diagnostics.extend(validate_tree(tree))
        for node in tree.nodes.values():
            if node.group_tree and node.group_tree not in document.trees:
                diagnostics.append(Diagnostic(Severity.ERROR, "graph.missing_group", f"Group node {node.display_name} references missing tree {node.group_tree!r}.", tree=tree.name, nodes=[node.id]))
    return diagnostics


def validate_semantic(graph: SemanticGraph) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    params = {p.key for p in graph.parameters}
    for op in graph.ops.values():
        spec = get_operation(op.kind)
        if spec is None:
            diagnostics.append(Diagnostic(Severity.ERROR, "semantic.unknown_kind", f"Operation {op.id} has unregistered kind {op.kind!r}.", op=op.id))
            continue
        if not spec.dynamic:
            for name in op.inputs:
                if spec.input(name) is None:
                    diagnostics.append(Diagnostic(Severity.ERROR, "semantic.unknown_input", f"{op.kind} has no input {name!r}.", op=op.id))
            for name in op.outputs:
                if spec.output(name) is None:
                    diagnostics.append(Diagnostic(Severity.ERROR, "semantic.unknown_output", f"{op.kind} has no output {name!r}.", op=op.id))
        for name, value in op.inputs.items():
            items = value if isinstance(value, tuple) else (value,)
            for item in items:
                if isinstance(item, Param) and item.name not in params:
                    diagnostics.append(Diagnostic(Severity.ERROR, "semantic.unknown_param", f"{op.id}.{name} references unknown parameter {item.name!r}.", op=op.id))
                if isinstance(item, Link):
                    upstream = graph.ops.get(item.op)
                    if upstream is None:
                        diagnostics.append(Diagnostic(Severity.ERROR, "semantic.dangling_link", f"{op.id}.{name} references missing operation {item.op!r}.", op=op.id))
                    elif item.output not in upstream.outputs:
                        diagnostics.append(Diagnostic(Severity.ERROR, "semantic.missing_output", f"{op.id}.{name} references missing output {item.op}.{item.output}.", op=op.id))
                    else:
                        _check_types(graph, op, name, item, diagnostics)
                if isinstance(item, Const) and item.type == DataType.ANY and item.value is None:
                    continue
    for out in graph.outputs:
        for link in iter_links(out.value):
            if link.op not in graph.ops:
                diagnostics.append(Diagnostic(Severity.ERROR, "semantic.dangling_output", f"Graph output {out.name!r} references missing operation {link.op!r}."))
    try:
        graph.topological_order()
    except ValueError as exc:
        diagnostics.append(Diagnostic(Severity.ERROR, "semantic.cycle", str(exc)))
    for sub in graph.subgraphs.values():
        diagnostics.extend(validate_semantic(sub))
    return diagnostics


def _check_types(graph: SemanticGraph, op, input_name: str, link: Link, diagnostics: list[Diagnostic]) -> None:
    spec = get_operation(op.kind)
    port = spec.input(input_name) if spec else None
    produced = graph.ops[link.op].outputs[link.output]
    if port is None:
        return
    if produced.field and not port.field and spec and not spec.dynamic:
        diagnostics.append(
            Diagnostic(Severity.ERROR, "semantic.field_into_value", f"A field ({graph.ops[link.op].display_name}) is connected to {op.kind}.{input_name}, which only accepts single values.", op=op.id)
        )
    if conversion(produced.base, port.type) == Conversion.INVALID:
        diagnostics.append(Diagnostic(Severity.ERROR, "semantic.type_mismatch", f"{produced.base.value} cannot flow into {op.kind}.{input_name} ({port.type.value}).", op=op.id))
