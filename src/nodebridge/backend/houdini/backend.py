"""Houdini backend.

Geometry graphs become SOP networks. Shader graphs become material builders.
Compositor graphs become COP2 networks where a node type exists, and labeled
nulls where it does not.
"""

from __future__ import annotations

from nodebridge.backend.houdini.generators import render_network
from nodebridge.backend.houdini.mappings import load
from nodebridge.backend.houdini.sop import HoudiniBuild, SpareParm
from nodebridge.ir.semantic import OperationKind, SemanticGraph
from nodebridge.ir.types import DataType
from nodebridge.translation.confidence import Classification, Confidence, TranslationRecord
from nodebridge.translation.registry import REGISTRY


class HoudiniBackend:
    """Generate pasteable Houdini Python from a semantic graph."""

    id = "houdini"

    def supports(self, operation: OperationKind) -> bool:
        load()
        spec = REGISTRY.get(operation, self.id)
        return spec is not None and spec.confidence is not Confidence.UNSUPPORTED

    def classify(self, operation: OperationKind) -> Classification:
        load()
        spec = REGISTRY.get(operation, self.id)
        if spec is None:
            return Classification(
                confidence=Confidence.UNSUPPORTED,
                explanation=f"No Houdini translator is registered for {operation.value}.",
                implementation="none",
                emitted=True,
            )
        return spec.classification()

    def generate(self, graph: SemanticGraph, options) -> tuple[str, list[TranslationRecord]]:
        load()
        if graph.system.value == "shader":
            from nodebridge.backend.houdini.mappings.shading import generate_material

            return generate_material(graph, options)
        if graph.system.value == "compositor":
            from nodebridge.backend.houdini.mappings.compositor import generate_cop

            return generate_cop(graph, options)
        build = HoudiniBuild(graph, options)
        populate(build)
        _promote(build)
        records = collect_records(build, graph)
        return render_network(build), records


def populate(build: HoudiniBuild) -> None:
    """Run translators in dependency order."""

    load()
    for operation in _ordered(build.graph):
        spec = REGISTRY.get(operation.kind, "houdini")
        if spec is None or spec.function is None:
            build.classifications[operation.id] = Classification(
                confidence=Confidence.UNSUPPORTED,
                explanation=f"No Houdini translator is registered for {operation.kind.value}.",
                implementation="none",
            )
            build.emit_unsupported(operation, build.classifications[operation.id].explanation)
            continue
        spec.function(operation, build)
    _fill_missing_markers(build)


def collect_records(build: HoudiniBuild, graph: SemanticGraph) -> list[TranslationRecord]:
    records = []
    for operation in graph.operations:
        classification = build.classifications.get(operation.id)
        if classification is None:
            classification = Classification(
                confidence=Confidence.UNSUPPORTED,
                explanation=f"{operation.kind.value} was not classified.",
                implementation="none",
            )
        records.append(
            TranslationRecord(
                operation_id=operation.id,
                operation_name=operation.name,
                operation=operation.kind.value,
                classification=classification,
                source_types=operation.source.node_types,
                notes=list(operation.notes),
            )
        )
        if operation.subgraph is not None:
            nested = getattr(build, "nested", {}).get(operation.id)
            if nested is not None:
                records.extend(collect_records(nested, operation.subgraph))
    return records


def _ordered(graph: SemanticGraph):
    incoming = {operation.id: 0 for operation in graph.operations}
    outgoing: dict[str, list[str]] = {operation.id: [] for operation in graph.operations}
    known = set(incoming)
    for edge in graph.edges:
        if edge.from_operation not in known or edge.to_operation not in known:
            continue
        incoming[edge.to_operation] += 1
        outgoing[edge.from_operation].append(edge.to_operation)
    queue = [operation_id for operation_id, degree in incoming.items() if degree == 0]
    order = []
    while queue:
        operation_id = queue.pop(0)
        order.append(operation_id)
        for child in outgoing[operation_id]:
            incoming[child] -= 1
            if incoming[child] == 0:
                queue.append(child)
    seen = set(order)
    order.extend(operation.id for operation in graph.operations if operation.id not in seen)
    by_id = {operation.id: operation for operation in graph.operations}
    return [by_id[operation_id] for operation_id in order]


def _promote(build: HoudiniBuild) -> None:
    existing = {spare.name for spare in build.spares}
    for parameter in build.graph.interface:
        if parameter.data_type in {DataType.GEOMETRY, DataType.MESH, DataType.CURVE, DataType.POINTS, DataType.INSTANCES, DataType.MATERIAL, DataType.OBJECT_REFERENCE, DataType.COLLECTION_REFERENCE}:
            continue
        from nodebridge.common.names import sanitize_identifier

        name = sanitize_identifier(parameter.identifier or parameter.name)
        if name in existing:
            continue
        kind = "float"
        default = 0.0 if parameter.default is None else parameter.default
        if parameter.data_type is DataType.INT:
            kind = "int"
            default = int(default or 0)
        elif parameter.data_type is DataType.BOOL:
            kind = "toggle"
            default = bool(default)
        elif parameter.data_type is DataType.STRING:
            kind = "string"
            default = "" if default is None else str(default)
        elif parameter.data_type in {DataType.VECTOR3, DataType.COLOR, DataType.VECTOR4, DataType.VECTOR2}:
            kind = "vector"
            default = tuple(default) if isinstance(default, (list, tuple)) else (0.0, 0.0, 0.0)
        else:
            try:
                default = float(default)
            except (TypeError, ValueError):
                default = 0.0
        build.spares.append(SpareParm(kind, name, parameter.name, default))
        existing.add(name)


def _fill_missing_markers(build: HoudiniBuild) -> None:
    """Every operation id must appear in the script, including noted field ops."""

    present = {node.op_id for node in build.nodes}
    noted = "\n".join(build.notes)
    for operation in build.graph.operations:
        if operation.id in build.classifications and (operation.id in present or f"# operation: {operation.id} " in noted):
            continue
        if operation.id not in build.classifications:
            build.classifications[operation.id] = Classification(
                confidence=Confidence.UNSUPPORTED,
                explanation=f"{operation.kind.value} produced no Houdini node.",
                implementation="none",
            )
        build.note(operation)
