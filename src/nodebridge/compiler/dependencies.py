"""Dependency analysis for graph IR.

Ordering comes from socket links. Node editor coordinates are ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nodebridge.ir.graph_ir import GraphNode, NodeTree


@dataclass
class DependencyReport:
    """Structural facts about one node tree."""

    order: list[str] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    dead_nodes: list[str] = field(default_factory=list)
    branches: list[str] = field(default_factory=list)
    roots: list[str] = field(default_factory=list)

    @property
    def acyclic(self) -> bool:
        return not self.cycles


def analyze_dependencies(tree: NodeTree) -> DependencyReport:
    """Topological order, cycles, dead nodes, and branch points."""
    incoming: dict[str, int] = {node_id: 0 for node_id in tree.nodes}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in tree.nodes}
    incoming_edges: dict[str, int] = {node_id: 0 for node_id in tree.nodes}
    outgoing_edges: dict[str, int] = {node_id: 0 for node_id in tree.nodes}
    for edge in tree.edges:
        if edge.source_node not in tree.nodes or edge.target_node not in tree.nodes:
            continue
        outgoing[edge.source_node].append(edge.target_node)
        incoming[edge.target_node] += 1
        outgoing_edges[edge.source_node] += 1
        incoming_edges[edge.target_node] += 1

    report = DependencyReport(
        roots=sorted(node_id for node_id, count in incoming.items() if count == 0),
        branches=sorted(
            node_id
            for node_id, targets in outgoing.items()
            if len(set(targets)) > 1
        ),
    )
    ready = list(report.roots)
    seen: set[str] = set()
    while ready:
        node_id = ready.pop(0)
        if node_id in seen:
            continue
        seen.add(node_id)
        report.order.append(node_id)
        for successor in sorted(set(outgoing[node_id])):
            incoming[successor] -= outgoing[node_id].count(successor)
            if incoming[successor] <= 0 and successor not in seen:
                ready.append(successor)
                ready.sort()

    if len(report.order) != len(tree.nodes):
        remaining = [node_id for node_id in tree.nodes if node_id not in seen]
        report.cycles = _cycles(remaining, outgoing)

    outputs = {
        node_id
        for node_id, node in tree.nodes.items()
        if _is_output(node)
    }
    if outputs:
        report.dead_nodes = sorted(
            node_id
            for node_id, node in tree.nodes.items()
            if node_id not in outputs
            and outgoing_edges[node_id] == 0
            and not _is_input(node)
        )
    return report


def extract_upstream(tree: NodeTree, node_id: str) -> NodeTree:
    """Return the subgraph of *node_id* and everything it depends on."""
    needed: set[str] = set()
    stack = [node_id]
    incoming_by_target: dict[str, list[str]] = {item: [] for item in tree.nodes}
    for edge in tree.edges:
        incoming_by_target.setdefault(edge.target_node, []).append(edge.source_node)
    while stack:
        current = stack.pop()
        if current in needed or current not in tree.nodes:
            continue
        needed.add(current)
        stack.extend(incoming_by_target.get(current, []))
    return NodeTree(
        id=f"{tree.id}__sub",
        name=f"{tree.name} / {node_id}",
        system=tree.system,
        nodes={item: tree.nodes[item] for item in needed},
        edges=[
            edge
            for edge in tree.edges
            if edge.source_node in needed and edge.target_node in needed
        ],
        metadata={"extracted_from": tree.id, "root": node_id},
    )


def _cycles(remaining: list[str], outgoing: dict[str, list[str]]) -> list[list[str]]:
    cycles: list[list[str]] = []
    visiting: list[str] = []
    visiting_set: set[str] = set()
    visited: set[str] = set()

    def walk(node_id: str) -> None:
        if node_id in visited or node_id not in remaining:
            return
        if node_id in visiting_set:
            start = visiting.index(node_id)
            cycles.append(visiting[start:] + [node_id])
            return
        visiting.append(node_id)
        visiting_set.add(node_id)
        for successor in outgoing.get(node_id, []):
            walk(successor)
        visiting.pop()
        visiting_set.remove(node_id)
        visited.add(node_id)

    for node_id in remaining:
        walk(node_id)
    return cycles


def _is_output(node: GraphNode) -> bool:
    return node.type_name in {
        "NodeGroupOutput",
        "NodeOutput",
        "ShaderNodeOutputMaterial",
        "CompositorNodeComposite",
        "CompositorNodeViewer",
        "CompositorNodeOutputFile",
    }


def _is_input(node: GraphNode) -> bool:
    return node.type_name in {"NodeGroupInput", "CompositorNodeRLayers"}
