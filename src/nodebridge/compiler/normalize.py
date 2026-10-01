"""Graph IR normalization.

Removes editor-only structure before semantic lifting:

* frames are dropped
* reroutes are bypassed
* muted nodes are bypassed through their internal links (as Blender does)
* invalid and muted links are removed
* dead nodes (not reaching an output) are removed and reported

Every removal is recorded as a diagnostic.
"""

from __future__ import annotations

import copy

from ..ir.graph import GraphEdge, NodeTree
from .analyzer import analyze_tree
from .diagnostics import DiagnosticBag


def normalize_tree(tree: NodeTree, diagnostics: DiagnosticBag, *, remove_dead: bool = True) -> NodeTree:
    tree = copy.deepcopy(tree)
    _drop_frames(tree)
    _drop_bad_links(tree, diagnostics)
    _bypass(tree, diagnostics, lambda n: n.type == "NodeReroute", reason=None)
    _bypass(tree, diagnostics, lambda n: n.muted, reason="muted")
    if remove_dead:
        analysis = analyze_tree(tree)
        for node_id in analysis.dead_nodes:
            node = tree.nodes.pop(node_id)
            diagnostics.info(
                "graph.dead_node",
                f"{node.display_name} ({node.type}) does not contribute to any output and was ignored.",
                tree=tree.name,
                nodes=[node_id],
            )
        tree.edges = [e for e in tree.edges if e.from_node in tree.nodes and e.to_node in tree.nodes]
    return tree


def _drop_frames(tree: NodeTree) -> None:
    for node_id in [n for n, node in tree.nodes.items() if node.type == "NodeFrame"]:
        del tree.nodes[node_id]


def _drop_bad_links(tree: NodeTree, diagnostics: DiagnosticBag) -> None:
    kept: list[GraphEdge] = []
    for edge in tree.edges:
        if edge.from_node not in tree.nodes or edge.to_node not in tree.nodes:
            continue
        if edge.muted:
            diagnostics.info("graph.muted_link", f"Muted link into {tree.nodes[edge.to_node].display_name} ignored.", tree=tree.name, nodes=[edge.to_node])
            continue
        if not edge.valid:
            diagnostics.warning("graph.invalid_link", f"Invalid link into {tree.nodes[edge.to_node].display_name} ignored (Blender marks it red).", tree=tree.name, nodes=[edge.to_node])
            continue
        kept.append(edge)
    tree.edges = kept


def _bypass(tree: NodeTree, diagnostics: DiagnosticBag, predicate, reason: str | None) -> None:
    for node_id in [n for n, node in tree.nodes.items() if predicate(node)]:
        node = tree.nodes[node_id]
        incoming = [e for e in tree.edges if e.to_node == node_id]
        outgoing = [e for e in tree.edges if e.from_node == node_id]
        if node.type == "NodeReroute":
            mapping = {out.identifier: node.inputs[0].identifier for out in node.outputs} if node.inputs else {}
        else:
            mapping = {to_socket: from_socket for from_socket, to_socket in node.internal_links}
        rewired: list[GraphEdge] = []
        for edge in outgoing:
            input_identifier = mapping.get(edge.from_socket)
            source = next((e for e in incoming if e.to_socket == input_identifier), None) if input_identifier else None
            if source is not None:
                rewired.append(GraphEdge(source.from_node, source.from_socket, edge.to_node, edge.to_socket))
            elif input_identifier and reason:
                socket = node.input(input_identifier)
                target = tree.nodes[edge.to_node].input(edge.to_socket)
                if socket is not None and target is not None:
                    target.default = socket.default
        tree.edges = [e for e in tree.edges if e.to_node != node_id and e.from_node != node_id] + rewired
        del tree.nodes[node_id]
        if reason:
            diagnostics.info("graph.muted_node", f"{node.display_name} is muted; its input passes straight through.", tree=tree.name, nodes=[node_id])
