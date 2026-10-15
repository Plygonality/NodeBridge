"""Unreal PCG graph scripts for geometry semantic graphs."""

from __future__ import annotations

from nodebridge.backend.unreal.python import script_header
from nodebridge.common.names import sanitize_identifier
from nodebridge.ir.semantic import OperationKind, SemanticGraph
from nodebridge.translation.confidence import Classification, Confidence, TranslationRecord


def generate_pcg(graph: SemanticGraph, options) -> tuple[str, list[TranslationRecord]]:
    asset = "NB_" + sanitize_identifier(graph.name)
    lines = script_header(
        "NodeBridge Unreal PCG graph.",
        f"Source: {graph.system.value} / {graph.name}",
    )
    lines.extend(
        [
            "def build(package_path='/Game/NodeBridge'):",
            "    tools = unreal.AssetToolsHelpers.get_asset_tools()",
            "    factory = unreal.PCGGraphFactory()",
            f"    graph = tools.create_asset({asset!r}, package_path, unreal.PCGGraph, factory)",
            "    if graph is None:",
            f"        raise RuntimeError('Could not create PCG graph {asset}')",
            "    input_node = graph.get_input_node()",
            "    output_node = graph.get_output_node()",
            "    previous = input_node",
            "    previous_labels = ['In', 'Out']",
            "    created = {'input': input_node, 'output': output_node}",
        ]
    )
    records: list[TranslationRecord] = []
    x = 250
    for operation in graph.operations:
        block, record, output_name, output_labels = _operation(operation, x, options)
        lines.extend(block)
        records.append(record)
        if output_name:
            lines.append(f"    if {output_name} is not None and previous is not None:")
            labels = ", ".join(repr(label) for label in output_labels)
            lines.append(f"        _connect(graph, previous, previous_labels, {output_name}, [{labels}, 'In', 'Surface'])")
            lines.append(f"        previous = {output_name}")
            lines.append(f"        previous_labels = [{labels}, 'Out']")
            lines.append(f"        created[{operation.id!r}] = {output_name}")
        x += 250
    lines.extend(
        [
            "    if previous is not None and output_node is not None:",
            "        _connect(graph, previous, previous_labels, output_node, ['Out', 'In'])",
            "    unreal.EditorAssetLibrary.save_asset(graph.get_path_name())",
            "    return graph",
            "",
            "",
            "if __name__ == '__main__':",
            "    build()",
            "",
        ]
    )
    return "\n".join(lines), records


def _operation(operation, x: int, options):
    kind = operation.kind
    marker = f"    # operation: {operation.id} kind={kind.value}"
    if kind is OperationKind.SCATTER:
        density = float(operation.parameters.get("density", 10.0) or 10.0)
        seed = int(operation.parameters.get("seed", 0) or 0)
        explanation = (
            "Surface Sampler is the PCG equivalent of distributing points on a surface. "
            "Unreal's sample positions are not Blender's, even with the same seed."
        )
        lines = [
            marker + " confidence=equivalent",
            f"    # {explanation}",
            f"    sampler_{x}, sampler_settings_{x} = _add(graph, 'PCGSurfaceSamplerSettings', {x}, 0)",
            f"    _try_set(sampler_settings_{x}, 'points_per_squared_meter', {density!r})",
            f"    _try_set(sampler_settings_{x}, 'seed', {seed!r})",
        ]
        return lines, _record(operation, Confidence.EQUIVALENT, "PCGSurfaceSamplerSettings", explanation, ("Target random samples may differ.",)), f"sampler_{x}", ["Out"]
    if kind is OperationKind.INSTANCE:
        explanation = (
            "Static Mesh Spawner instances a mesh on the points. "
            "Assign the mesh on the spawner; the Python API used here does not construct a mesh from a Blender primitive."
        )
        lines = [
            marker + " confidence=equivalent",
            f"    # {explanation}",
            f"    spawner_{x}, spawner_settings_{x} = _add(graph, 'PCGStaticMeshSpawnerSettings', {x}, 0)",
        ]
        return lines, _record(operation, Confidence.EQUIVALENT, "PCGStaticMeshSpawnerSettings", explanation, ("The instance mesh is not generated from Blender geometry.",)), f"spawner_{x}", ["Out"]
    if kind in {OperationKind.RANDOM, OperationKind.RANDOM_TRANSFORM} or (
        kind is OperationKind.TRANSFORM and operation.parameters.get("mode") in {"instance_rotation", "instance_scale"}
    ):
        explanation = (
            "Scale and rotation ranges are written to PCGTransformPointsSettings when that class exists. "
            "Unreal's random series is not NodeBridge's hash and is not Blender's."
        )
        minimum = operation.parameters.get("minimum", operation.parameters.get("scale", 0.4))
        maximum = operation.parameters.get("maximum", operation.parameters.get("scale", 1.2))
        lines = [
            marker + " confidence=approximate",
            f"    # {explanation}",
            f"    transform_{x}, transform_settings_{x} = _add(graph, 'PCGTransformPointsSettings', {x}, 0)",
            f"    _try_set(transform_settings_{x}, 'seed', {int(operation.parameters.get('seed', 0) or 0)!r})",
            f"    # Blender range minimum={minimum!r} maximum={maximum!r}",
        ]
        return lines, _record(operation, Confidence.APPROXIMATE, "PCGTransformPointsSettings", explanation, ("Property names are guarded. A missing property is logged and skipped.",)), f"transform_{x}", ["Out"]
    if kind is OperationKind.PRIMITIVE:
        explanation = "PCG has no primitive-cube node in the Python API used here. The graph input is the surface, and the spawner mesh is assigned by hand."
        lines = [
            marker + " confidence=approximate",
            f"    # {explanation}",
            f"    # primitive {operation.parameters.get('primitive')} size={operation.parameters.get('size')!r}",
        ]
        return lines, _record(operation, Confidence.APPROXIMATE, "graph input", explanation), None, []
    if kind in {OperationKind.GROUP_INPUT, OperationKind.GEOMETRY_INPUT}:
        explanation = "The PCG graph input is the surface sampled by the graph actor or pinned input."
        lines = [marker + " confidence=equivalent", f"    # {explanation}"]
        return lines, _record(operation, Confidence.EQUIVALENT, "PCGGraph input", explanation), None, []
    if kind in {OperationKind.GROUP_OUTPUT, OperationKind.GEOMETRY_OUTPUT}:
        explanation = "The PCG graph output receives the last generated node."
        lines = [marker + " confidence=exact", f"    # {explanation}"]
        return lines, _record(operation, Confidence.EXACT, "PCGGraph output", explanation), None, []
    if kind is OperationKind.REALIZE_INSTANCES:
        explanation = "PCG Static Mesh Spawner already emits instances. There is no separate realize node in this mapping."
        lines = [marker + " confidence=equivalent", f"    # {explanation}"]
        return lines, _record(operation, Confidence.EQUIVALENT, "spawner output", explanation), None, []
    if kind is OperationKind.SUBGRAPH and operation.subgraph is not None:
        explanation = "Nested groups are separate PCG assets when PCGSubgraphSettings exists. This script records the group and does not silently flatten it."
        lines = [
            marker + " confidence=approximate",
            f"    # {explanation}",
            f"    subgraph_{x}, subgraph_settings_{x} = _add(graph, 'PCGSubgraphSettings', {x}, 0)",
        ]
        return lines, _record(operation, Confidence.APPROXIMATE, "PCGSubgraphSettings", explanation, ("The subgraph asset reference is not assigned automatically.",)), f"subgraph_{x}", ["Out"]
    if kind is OperationKind.UNSUPPORTED:
        reason = str(operation.parameters.get("reason") or "Unsupported operation.")
        lines = [marker + " confidence=unsupported", f"    # {reason}"]
        return lines, _record(operation, Confidence.UNSUPPORTED, "none", reason, fallback="omitted from the PCG graph"), None, []
    explanation = f"No PCG node is mapped for {kind.value}. The operation is reported and omitted from the graph."
    lines = [marker + " confidence=unsupported", f"    # {explanation}"]
    confidence = Confidence.UNSUPPORTED
    if kind in {OperationKind.MATH, OperationKind.VECTOR_MATH, OperationKind.MAP_RANGE, OperationKind.COMPARE, OperationKind.ATTRIBUTE_READ}:
        confidence = Confidence.APPROXIMATE
        explanation = f"{kind.value} is not a first-class PCG node in this script. Constant values are baked into downstream settings when a consumer reads them."
        lines = [marker + " confidence=approximate", f"    # {explanation}"]
    return lines, _record(operation, confidence, "comment", explanation), None, []


def _record(operation, confidence, implementation, explanation, limitations=(), fallback=None) -> TranslationRecord:
    return TranslationRecord(
        operation_id=operation.id,
        operation_name=operation.name,
        operation=operation.kind.value,
        classification=Classification(
            confidence=confidence,
            explanation=explanation,
            implementation=implementation,
            limitations=tuple(limitations),
            fallback=fallback,
            emitted=confidence is not Confidence.UNSUPPORTED,
        ),
        source_types=operation.source.node_types,
    )
