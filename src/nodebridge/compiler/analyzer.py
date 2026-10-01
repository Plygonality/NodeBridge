"""Dependency analysis for a source graph.

Ordering comes from socket links. Node editor coordinates are ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nodebridge.ir.graph import NodeTree

_STRUCTURAL = {"NodeReroute", "NodeFrame"}
_OUTPUTS = {
    "NodeGroupOutput",
    "ShaderNodeOutputMaterial",
    "CompositorNodeComposite",
    "CompositorNodeViewer",
    "CompositorNodeOutputFile",
}


@dataclass
class GraphAnalysis:
    """Topological order plus the structural facts the report needs."""

    order: list[str] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    dead_nodes: list[str] = field(default_factory=list)
    muted_nodes: list[str] = field(default_factory=list)
    branches: list[str] = field(default_factory=list)
    roots: list[str] = field(default_factory=list)
    sinks: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def analyze(tree: NodeTree) -> GraphAnalysis:
    """Build the dependency graph and report cycles, branches, and dead nodes."""

    analysis = GraphAnalysis()
    ids = [node.id for node in tree.nodes]
    known = set(ids)
    incoming: dict[str, set[str]] = {node_id: set() for node_id in ids}
    outgoing: dict[str, set[str]] = {node_id: set() for node_id in ids}

    for edge in tree.edges:
        if edge.from_node not in known or edge.to_node not in known:
            analysis.errors.append(
                f"Link {edge.id} references a missing node ({edge.from_node} -> {edge.to_node})."
            )
            continue
        if edge.from_node == edge.to_node:
            analysis.cycles.append([edge.from_node])
        incoming[edge.to_node].add(edge.from_node)
        outgoing[edge.from_node].add(edge.to_node)

    indegree = {node_id: len(incoming[node_id]) for node_id in ids}
    queue = [node_id for node_id in ids if indegree[node_id] == 0]
    order: list[str] = []
    while queue:
        node_id = queue.pop(0)
        order.append(node_id)
        for child in sorted(outgoing[node_id]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    analysis.order = order

    cyclic_ids = [node_id for node_id in ids if node_id not in set(order)]
    if cyclic_ids:
        analysis.cycles.extend(_cycle_paths(cyclic_ids, outgoing))
        analysis.errors.append(
            "Cycle detected: " + ", ".join(cyclic_ids) + ". Generation keeps the acyclic prefix."
        )

    outputs = [node.id for node in tree.nodes if node.node_type in _OUTPUTS]
    if not outputs:
        outputs = [node_id for node_id in ids if not outgoing[node_id]]

    reachable: set[str] = set()
    stack = list(outputs)
    while stack:
        current = stack.pop()
        if current in reachable or current not in known:
            continue
        reachable.add(current)
        stack.extend(incoming[current])

    for node in tree.nodes:
        if node.mute:
            analysis.muted_nodes.append(node.id)
        if node.node_type in _STRUCTURAL:
            continue
        if node.id not in reachable and node.id not in cyclic_ids:
            analysis.dead_nodes.append(node.id)

    analysis.branches = [node_id for node_id in ids if len(outgoing[node_id]) > 1]
    analysis.roots = [node_id for node_id in ids if not incoming[node_id]]
    analysis.sinks = [node_id for node_id in ids if not outgoing[node_id]]
    return analysis


def _cycle_paths(cyclic_ids: list[str], outgoing: dict[str, set[str]]) -> list[list[str]]:
    cyclic = set(cyclic_ids)
    paths: list[list[str]] = []
    seen: set[str] = set()
    for start in cyclic_ids:
        if start in seen:
            continue
        path = [start]
        cursor = start
        while True:
            nxt = next((item for item in outgoing[cursor] if item in cyclic), None)
            if nxt is None or nxt in path:
                if nxt is not None:
                    path.append(nxt)
                break
            path.append(nxt)
            cursor = nxt
        for item in path:
            seen.add(item)
        paths.append(path)
    return paths
