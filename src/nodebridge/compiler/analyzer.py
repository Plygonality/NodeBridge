"""Dependency analysis built from socket connections only.

Editor node locations are never used for ordering. The same generic
algorithms serve the Graph IR (node level) and the Semantic IR.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Hashable, Iterable

from ..ir.graph import NodeTree, TreeKind

OUTPUT_NODE_TYPES = {
    TreeKind.GEOMETRY: {"NodeGroupOutput"},
    TreeKind.SHADER: {"ShaderNodeOutputMaterial", "ShaderNodeOutputWorld", "ShaderNodeOutputLight", "ShaderNodeOutputAOV", "NodeGroupOutput"},
    TreeKind.COMPOSITOR: {"CompositorNodeComposite", "CompositorNodeViewer", "CompositorNodeOutputFile", "NodeGroupOutput"},
}
IGNORED_NODE_TYPES = {"NodeFrame"}


def topological_sort(nodes: Iterable[Hashable], edges: Iterable[tuple[Hashable, Hashable]]) -> tuple[list, set]:
    """Kahn's algorithm with stable ordering.

    Returns ``(order, cyclic)`` where ``cyclic`` holds nodes that are part
    of, or downstream of, a cycle and therefore could not be ordered.
    """
    node_list = list(dict.fromkeys(nodes))
    position = {node: index for index, node in enumerate(node_list)}
    indegree = {node: 0 for node in node_list}
    successors: dict = defaultdict(list)
    for source, target in edges:
        if source not in indegree or target not in indegree:
            continue
        successors[source].append(target)
        indegree[target] += 1
    ready = deque(sorted((n for n in node_list if indegree[n] == 0), key=position.__getitem__))
    order = []
    while ready:
        node = ready.popleft()
        order.append(node)
        for nxt in sorted(successors[node], key=position.__getitem__):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
    cyclic = {n for n in node_list if indegree[n] > 0}
    return order, cyclic


def find_cycles(nodes: Iterable[Hashable], edges: Iterable[tuple[Hashable, Hashable]]) -> list[list]:
    """Strongly connected components with more than one node (or a self loop)."""
    node_list = list(dict.fromkeys(nodes))
    adjacency: dict = defaultdict(list)
    self_loops = set()
    for source, target in edges:
        adjacency[source].append(target)
        if source == target:
            self_loops.add(source)
    index_of: dict = {}
    low: dict = {}
    stack: list = []
    on_stack: set = set()
    result: list[list] = []
    counter = [0]

    def strongconnect(start):
        work = [(start, iter(adjacency[start]))]
        index_of[start] = low[start] = counter[0]
        counter[0] += 1
        stack.append(start)
        on_stack.add(start)
        while work:
            node, it = work[-1]
            advanced = False
            for nxt in it:
                if nxt not in index_of:
                    index_of[nxt] = low[nxt] = counter[0]
                    counter[0] += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, iter(adjacency[nxt])))
                    advanced = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index_of[nxt])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index_of[node]:
                component = []
                while True:
                    item = stack.pop()
                    on_stack.discard(item)
                    component.append(item)
                    if item == node:
                        break
                if len(component) > 1 or node in self_loops:
                    result.append(sorted(component, key=str))

    for node in node_list:
        if node not in index_of:
            strongconnect(node)
    return result


def reachable_upstream(targets: Iterable[Hashable], edges: Iterable[tuple[Hashable, Hashable]]) -> set:
    predecessors: dict = defaultdict(list)
    for source, target in edges:
        predecessors[target].append(source)
    seen: set = set()
    pending = list(targets)
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        pending.extend(predecessors[node])
    return seen


def branch_points(edges: Iterable[tuple[Hashable, Hashable]]) -> dict:
    """Nodes whose outputs feed more than one downstream node."""
    fanout: dict = defaultdict(set)
    for source, target in edges:
        fanout[source].add(target)
    return {node: sorted(targets, key=str) for node, targets in fanout.items() if len(targets) > 1}


@dataclass
class TreeAnalysis:
    tree: str
    order: list[str] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    dead_nodes: list[str] = field(default_factory=list)
    branches: dict[str, list[str]] = field(default_factory=dict)
    output_nodes: list[str] = field(default_factory=list)
    depth: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "tree": self.tree,
            "order": self.order,
            "cycles": self.cycles,
            "dead_nodes": self.dead_nodes,
            "branches": self.branches,
            "output_nodes": self.output_nodes,
        }


def node_edges(tree: NodeTree) -> list[tuple[str, str]]:
    return [(e.from_node, e.to_node) for e in tree.edges if e.valid and not e.muted and e.from_node in tree.nodes and e.to_node in tree.nodes]


def output_nodes(tree: NodeTree) -> list[str]:
    types = OUTPUT_NODE_TYPES.get(tree.kind, set())
    result = []
    for node in tree.nodes.values():
        if node.type not in types:
            continue
        if node.parameters.get("is_active_output") is False and node.type != "CompositorNodeViewer":
            continue
        result.append(node.id)
    return result


def analyze_tree(tree: NodeTree) -> TreeAnalysis:
    edges = node_edges(tree)
    ids = [n for n in tree.nodes if tree.nodes[n].type not in IGNORED_NODE_TYPES]
    order, cyclic = topological_sort(ids, edges)
    outputs = output_nodes(tree)
    live = reachable_upstream(outputs, edges)
    dead = [n for n in ids if n not in live]
    depth: dict[str, int] = {}
    for node in order:
        preds = [s for s, t in edges if t == node]
        depth[node] = 1 + max((depth.get(p, 0) for p in preds), default=0)
    return TreeAnalysis(
        tree=tree.name,
        order=order,
        cycles=find_cycles(ids, edges) if cyclic else [],
        dead_nodes=dead,
        branches=branch_points(edges),
        output_nodes=outputs,
        depth=depth,
    )


def extract_subgraph(tree: NodeTree, roots: Iterable[str]) -> NodeTree:
    """The upstream closure of ``roots`` as a standalone tree."""
    keep = reachable_upstream(roots, node_edges(tree))
    sub = NodeTree(name=f"{tree.name}::subgraph", kind=tree.kind, interface=list(tree.interface), is_group=tree.is_group, metadata=dict(tree.metadata))
    for node_id, node in tree.nodes.items():
        if node_id in keep:
            sub.add(node)
    sub.edges = [e for e in tree.edges if e.from_node in keep and e.to_node in keep]
    return sub
