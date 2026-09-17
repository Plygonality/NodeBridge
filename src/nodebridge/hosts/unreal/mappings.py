"""Unreal PCG ↔ semantic operation mappings.

Native types are PCG settings class names (without the ``unreal.`` prefix).
"""

from __future__ import annotations

from nodebridge.core.diagnostics import TranslationStatus
from nodebridge.core.node import IRNode
from nodebridge.core.values import JSONValue
from nodebridge.hosts.native import NativeGraph, NativeNode
from nodebridge.hosts.recipes import NodeTemplate, Recipe

STATIC_OPERATIONS = {
    "PCGGraphInput": "graph.input",
    "Input": "graph.input",
    "PCGGraphOutput": "graph.output",
    "Output": "graph.output",
    "PCGSurfaceSamplerSettings": "points.distribute",
    "SurfaceSampler": "points.distribute",
    "PCGStaticMeshSpawnerSettings": "geometry.instance",
    "StaticMeshSpawner": "geometry.instance",
    "PCGTransformPointsSettings": "geometry.transform",
    "TransformPoints": "geometry.transform",
    "PCGMergeSettings": "geometry.join",
    "PCGMergePointsSettings": "geometry.join",
    "Merge": "geometry.join",
    "PCGCopyPointsSettings": "geometry.instance",
    "CopyPoints": "geometry.instance",
    "PCGAttributeNoiseSettings": "random.float",
    "AttributeNoise": "random.float",
    "PCGDensityFilterSettings": "geometry.delete",
    "DensityFilter": "geometry.delete",
    "PCGPointFromMeshSettings": "points.distribute",
    "MeshSampler": "points.distribute",
}


def resolve_unreal_node(node: NativeNode, graph: NativeGraph) -> tuple[str, dict[str, object]]:
    del graph
    extras: dict[str, object] = {}
    native_type = node.type
    if native_type in STATIC_OPERATIONS:
        operation = STATIC_OPERATIONS[native_type]
        if operation == "random.float" and str(node.parameters.get("dimension") or "") == "vector":
            return "random.vector", extras
        return operation, extras
    return "unknown", extras


def _params(node: IRNode) -> dict[str, JSONValue]:
    values = {name: parameter.value for name, parameter in node.parameters.items()}
    for socket in node.inputs.values():
        if socket.default is not None and socket.name not in values:
            values[socket.name] = socket.default
    return values


def _recipe(
    operation: str,
    native_type: str,
    *,
    fidelity: TranslationStatus = TranslationStatus.EXACT,
    inputs: tuple[str, ...] = ("In",),
    outputs: tuple[str, ...] = ("Out",),
    expose_inputs: dict[str, tuple[str, str]] | None = None,
    expose_outputs: dict[str, tuple[str, str]] | None = None,
    note: str = "",
    parameter_builder=None,
) -> Recipe:
    return Recipe(
        operation=operation,
        fidelity=fidelity,
        nodes=(
            NodeTemplate(local_id="node", native_type=native_type, inputs=inputs, outputs=outputs),
        ),
        expose_inputs=expose_inputs or {"geometry": ("node", inputs[0] if inputs else "In")},
        expose_outputs=expose_outputs or {"geometry": ("node", outputs[0] if outputs else "Out")},
        note=note,
        parameter_builder=parameter_builder,
    )


UNREAL_RECIPES: dict[str, Recipe] = {
    "graph.input": _recipe(
        "graph.input",
        "Input",
        inputs=(),
        outputs=("In",),
        expose_inputs={},
        expose_outputs={"geometry": ("node", "In")},
        note="PCG graph input node. Pin label is In.",
    ),
    "graph.output": _recipe(
        "graph.output",
        "Output",
        inputs=("Out",),
        outputs=(),
        expose_inputs={"geometry": ("node", "Out")},
        expose_outputs={},
        note="PCG graph output node. Pin label is Out.",
    ),
    "points.distribute": _recipe(
        "points.distribute",
        "PCGSurfaceSamplerSettings",
        inputs=("Surface",),
        outputs=("Out",),
        expose_inputs={"geometry": ("node", "Surface"), "density": ("node", "Surface")},
        expose_outputs={"points": ("node", "Out"), "geometry": ("node", "Out")},
        parameter_builder=lambda node: {
            "points_per_squared_meter": node.parameters["density"].value
            if "density" in node.parameters
            else _params(node).get("density", 10.0)
        },
        note="Surface Sampler. Main input pin is Surface, not In.",
    ),
    "geometry.instance": _recipe(
        "geometry.instance",
        "PCGStaticMeshSpawnerSettings",
        inputs=("In",),
        outputs=("Out",),
        expose_inputs={
            "points": ("node", "In"),
            "instance": ("node", "In"),
            "scale": ("node", "In"),
            "rotation": ("node", "In"),
        },
        expose_outputs={"instances": ("node", "Out"), "geometry": ("node", "Out")},
        fidelity=TranslationStatus.APPROXIMATE,
        note="Static Mesh Spawner emits actors/meshes; it is not a packed-instance graph node.",
        parameter_builder=_params,
    ),
    "geometry.realize_instances": _recipe(
        "geometry.realize_instances",
        "PCGStaticMeshSpawnerSettings",
        fidelity=TranslationStatus.APPROXIMATE,
        note="PCG has no Realize Instances analogue; spawning already materializes meshes.",
        expose_inputs={"geometry": ("node", "In")},
        expose_outputs={"geometry": ("node", "Out")},
    ),
    "geometry.transform": _recipe(
        "geometry.transform",
        "PCGTransformPointsSettings",
        expose_inputs={
            "geometry": ("node", "In"),
            "translation": ("node", "In"),
            "rotation": ("node", "In"),
            "scale": ("node", "In"),
        },
        parameter_builder=_params,
    ),
    "geometry.join": _recipe(
        "geometry.join",
        "PCGMergePointsSettings",
        inputs=("In", "In_001"),
        expose_inputs={"geometry": ("node", "In"), "geometry_001": ("node", "In_001")},
    ),
    "geometry.delete": _recipe(
        "geometry.delete",
        "PCGDensityFilterSettings",
        fidelity=TranslationStatus.APPROXIMATE,
        note="Density Filter is the closest PCG analogue of element deletion.",
    ),
    "geometry.primitive": _recipe(
        "geometry.primitive",
        "PCGPointFromMeshSettings",
        inputs=(),
        fidelity=TranslationStatus.APPROXIMATE,
        note="PCG samples points from a mesh asset; it does not author a mesh primitive SOP-style.",
        expose_inputs={},
        parameter_builder=_params,
    ),
    "random.float": _recipe(
        "random.float",
        "PCGAttributeNoiseSettings",
        expose_outputs={"value": ("node", "Out"), "geometry": ("node", "Out")},
        parameter_builder=_params,
    ),
    "random.vector": _recipe(
        "random.vector",
        "PCGAttributeNoiseSettings",
        fidelity=TranslationStatus.APPROXIMATE,
        note="Attribute Noise is scalar-oriented; vector noise is an approximation.",
        expose_outputs={"vector": ("node", "Out"), "geometry": ("node", "Out")},
        parameter_builder=_params,
    ),
    "random.integer": _recipe(
        "random.integer",
        "PCGAttributeNoiseSettings",
        fidelity=TranslationStatus.APPROXIMATE,
        note="PCG Attribute Noise does not emit integers natively.",
        expose_outputs={"value": ("node", "Out")},
        parameter_builder=_params,
    ),
    "attribute.read": _recipe(
        "attribute.read",
        "PCGAttributeGetFromPointIndexSettings",
        fidelity=TranslationStatus.APPROXIMATE,
        note="PCG attribute access is point-data oriented and API-unstable across versions.",
        expose_outputs={"value": ("node", "Out"), "geometry": ("node", "Out")},
        parameter_builder=_params,
    ),
    "attribute.write": _recipe(
        "attribute.write",
        "PCGMetadataOperationSettings",
        fidelity=TranslationStatus.APPROXIMATE,
        note="PCG metadata operations vary by engine version; this is a construction-plan placeholder.",
        parameter_builder=_params,
    ),
}

SETTINGS_CLASSES = {
    "PCGSurfaceSamplerSettings": "unreal.PCGSurfaceSamplerSettings",
    "PCGStaticMeshSpawnerSettings": "unreal.PCGStaticMeshSpawnerSettings",
    "PCGTransformPointsSettings": "unreal.PCGTransformPointsSettings",
    "PCGMergePointsSettings": "unreal.PCGMergePointsSettings",
    "PCGAttributeNoiseSettings": "unreal.PCGAttributeNoiseSettings",
    "PCGDensityFilterSettings": "unreal.PCGDensityFilterSettings",
    "PCGPointFromMeshSettings": "unreal.PCGPointFromMeshSettings",
    "PCGCopyPointsSettings": "unreal.PCGCopyPointsSettings",
    "PCGAttributeGetFromPointIndexSettings": "unreal.PCGAttributeGetFromPointIndexSettings",
    "PCGMetadataOperationSettings": "unreal.PCGMetadataOperationSettings",
}
