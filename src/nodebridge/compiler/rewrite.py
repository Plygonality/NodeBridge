"""Graph rewrite rules.

Rules match semantic operations, not Blender node names. A rule may replace
several operations with one operation when the extra nodes have no other
consumers. The source node ids stay on the replacement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from nodebridge.ir.semantic import Operation, OperationKind, SemanticEdge, SemanticGraph, SourceRef
from nodebridge.ir.types import DataType
from nodebridge.ir.operations import field_port


class RewriteRule(Protocol):
    name: str

    def apply(self, graph: SemanticGraph) -> bool:
        """Return True when the graph changed."""


@dataclass
class Match:
    rule: str
    operation_ids: tuple[str, ...]


def apply_rewrites(graph: SemanticGraph, rules: list[RewriteRule] | None = None) -> SemanticGraph:
    """Apply rules until none of them fire. Each rule is responsible for one pattern."""

    active = list(rules if rules is not None else DEFAULT_RULES)
    changed = True
    guard = 0
    while changed and guard < 32:
        changed = False
        guard += 1
        for rule in active:
            changed = rule.apply(graph) or changed
    graph.metadata["rewrites"] = [rule.name for rule in active]
    return graph


class SpatialNoiseMaskRule:
    """Noise -> Map Range -> Compare becomes one spatial mask when the chain is linear."""

    name = "spatial_noise_mask"

    def apply(self, graph: SemanticGraph) -> bool:
        compares = [op for op in graph.operations if op.kind is OperationKind.COMPARE]
        for compare in compares:
            map_edge = graph.edge_to(compare.id, "a")
            if map_edge is None:
                continue
            map_range = graph.try_get(map_edge.from_operation)
            if map_range is None or map_range.kind is not OperationKind.MAP_RANGE:
                continue
            noise_edge = graph.edge_to(map_range.id, "value")
            if noise_edge is None:
                continue
            noise = graph.try_get(noise_edge.from_operation)
            if noise is None or noise.kind is not OperationKind.NOISE:
                continue
            if not _exclusive_consumer(graph, noise.id, map_range.id):
                continue
            if not _exclusive_consumer(graph, map_range.id, compare.id):
                continue
            fused = Operation(
                id=f"{compare.id}_mask",
                kind=OperationKind.SPATIAL_NOISE_MASK,
                name=f"{noise.name} Mask",
                parameters={
                    "scale": noise.parameters.get("scale", 5.0),
                    "detail": noise.parameters.get("detail", 2.0),
                    "roughness": noise.parameters.get("roughness", 0.5),
                    "threshold": compare.parameters.get("b", 0.5),
                    "comparison": compare.parameters.get("operation", "greater_than"),
                    "from_min": map_range.parameters.get("from_min", 0.0),
                    "from_max": map_range.parameters.get("from_max", 1.0),
                    "to_min": map_range.parameters.get("to_min", 0.0),
                    "to_max": map_range.parameters.get("to_max", 1.0),
                },
                inputs={"vector": field_port("vector", DataType.VECTOR3)},
                outputs={"result": field_port("result", DataType.BOOL)},
                source=_merge_source(noise, map_range, compare),
                notes=["Fused from noise, map range, and compare."],
            )
            _replace_chain(graph, fused, (noise, map_range, compare), compare.id)
            return True
        return False


class RandomTransformRule:
    """Instance rotation and scale driven in series become one random transform."""

    name = "random_transform"

    def apply(self, graph: SemanticGraph) -> bool:
        transforms = [
            op
            for op in graph.operations
            if op.kind is OperationKind.TRANSFORM and op.parameters.get("mode") in {"instance_rotation", "instance_scale"}
        ]
        if len(transforms) < 1:
            return False
        # A single instance-space transform driven by random is enough to name the intent.
        for transform in transforms:
            driver = _random_driver(graph, transform)
            if driver is None:
                continue
            if len(graph.outgoing(driver.id)) != 1:
                continue
            fused = Operation(
                id=f"{transform.id}_variation",
                kind=OperationKind.RANDOM_TRANSFORM,
                name=transform.name or "Random Transform",
                parameters={
                    "channel": transform.parameters.get("mode"),
                    "seed": driver.parameters.get("seed", 0),
                    "minimum": driver.parameters.get("minimum", 0.0),
                    "maximum": driver.parameters.get("maximum", 1.0),
                    "data_type": driver.parameters.get("data_type", "float"),
                },
                inputs={"geometry": graph_port_geometry()},
                outputs={"geometry": graph_port_geometry()},
                source=_merge_source(driver, transform),
                notes=["Fused from a random value driving an instance transform."],
            )
            _replace_chain(graph, fused, (driver, transform), transform.id)
            return True
        return False


def graph_port_geometry():
    from nodebridge.ir.operations import geometry_port

    return geometry_port("geometry")


def _exclusive_consumer(graph: SemanticGraph, source_id: str, consumer_id: str) -> bool:
    outgoing = graph.outgoing(source_id)
    return len(outgoing) == 1 and outgoing[0].to_operation == consumer_id


def _random_driver(graph: SemanticGraph, transform: Operation):
    for port in ("rotation", "scale", "translation"):
        edge = graph.edge_to(transform.id, port)
        if edge is None:
            continue
        source = graph.try_get(edge.from_operation)
        if source is not None and source.kind is OperationKind.RANDOM:
            return source
    return None


def _merge_source(*operations: Operation) -> SourceRef:
    ids: list[str] = []
    types: list[str] = []
    names: list[str] = []
    for operation in operations:
        ids.extend(operation.source.node_ids)
        types.extend(operation.source.node_types)
        names.extend(operation.source.node_names)
    return SourceRef(tuple(ids), tuple(types), tuple(names))


def _replace_chain(graph: SemanticGraph, fused: Operation, removed: tuple[Operation, ...], output_id: str) -> None:
    removed_ids = {operation.id for operation in removed}
    incoming = [edge for edge in graph.edges if edge.to_operation in removed_ids and edge.from_operation not in removed_ids]
    outgoing = [edge for edge in graph.edges if edge.from_operation == output_id and edge.to_operation not in removed_ids]
    graph.operations = [operation for operation in graph.operations if operation.id not in removed_ids]
    graph.operations.append(fused)
    graph.edges = [
        edge
        for edge in graph.edges
        if edge.from_operation not in removed_ids and edge.to_operation not in removed_ids
    ]
    for edge in incoming:
        if edge.to_port in fused.inputs or edge.to_port in {"vector", "geometry"}:
            port = edge.to_port if edge.to_port in fused.inputs else next(iter(fused.inputs))
            graph.edges.append(
                SemanticEdge(
                    id=f"{edge.id}_fused_in",
                    from_operation=edge.from_operation,
                    from_port=edge.from_port,
                    to_operation=fused.id,
                    to_port=port,
                )
            )
    for edge in outgoing:
        graph.edges.append(
            SemanticEdge(
                id=f"{edge.id}_fused_out",
                from_operation=fused.id,
                from_port=next(iter(fused.outputs)),
                to_operation=edge.to_operation,
                to_port=edge.to_port,
            )
        )


DEFAULT_RULES: list[RewriteRule] = [SpatialNoiseMaskRule(), RandomTransformRule()]
