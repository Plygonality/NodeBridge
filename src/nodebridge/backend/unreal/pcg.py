"""Geometry Nodes -> Unreal PCG graphs.

PCG operates on point data, so NodeBridge maps the *point-processing*
part of a Geometry Nodes system: surface sampling, random transforms,
density filtering, merging and mesh spawning. Procedural modelling
operations (extrude, booleans, curves) have no PCG node and are
reported as UNSUPPORTED; instance geometry becomes a Static Mesh
reference. The PCG Python API is experimental (UE 5.4+); pin labels are
tried from candidate lists and missing properties are reported.
"""

from __future__ import annotations

import math
from typing import Any

from ...backend.codegen import PyWriter, clean_number, literal
from ...common.coordinates import blender_euler_to_unreal_rotator, unreal_axis_signs
from ...common.names import NameAllocator, python_identifier, unreal_asset_name
from ...common.units import ValueRole
from ...compiler.evaluate import NotConstant, evaluate
from ...ir.semantic import Const, InputValue, Link, Param, SemanticGraph, SemanticOp
from ...ir.types import GEOMETRY_TYPES
from ...translation.confidence import Classification, Confidence as C
from ...translation.registry import translator
from .pyexpr import PyExpr

T, CTX = "unreal", "pcg"
OUT = ["Out"]
IN = ["In"]
BASIC_SHAPES = {
    "cube": ("/Engine/BasicShapes/Cube.Cube", 1.0),
    "uv_sphere": ("/Engine/BasicShapes/Sphere.Sphere", 1.0),
    "ico_sphere": ("/Engine/BasicShapes/Sphere.Sphere", 1.0),
    "cylinder": ("/Engine/BasicShapes/Cylinder.Cylinder", 1.0),
    "cone": ("/Engine/BasicShapes/Cone.Cone", 1.0),
    "grid": ("/Engine/BasicShapes/Plane.Plane", 1.0),
}
CHAIN_KINDS = {"PRIMITIVE", "TRANSFORM", "MATERIAL_ASSIGNMENT", "OBJECT_REFERENCE", "COLLECTION_REFERENCE"}
POINT_KINDS = {"SCATTER", "RANDOM_TRANSFORM", "TRANSFORM_POINTS", "DELETE_GEOMETRY", "SEPARATE", "MERGE", "SET_POSITION", "TRANSFORM"}


def instance_chain(graph: SemanticGraph, op: SemanticOp) -> SemanticOp | None:
    """The INSTANCE op this op feeds as instance geometry (through transforms / materials)."""
    for consumer, name in graph.consumers(op.id):
        if consumer.kind == "INSTANCE" and name == "instance":
            return consumer
        if consumer.kind in CHAIN_KINDS and name == "geometry":
            found = instance_chain(graph, consumer)
            if found is not None:
                return found
    return None


def chain_source(graph: SemanticGraph, value: InputValue | None) -> tuple[SemanticOp | None, list[SemanticOp]]:
    """Walk an instance-geometry chain upstream: (source op, [transform/material ops])."""
    chain: list[SemanticOp] = []
    op = graph.resolve(value)
    while op is not None and op.kind in ("TRANSFORM", "MATERIAL_ASSIGNMENT"):
        chain.append(op)
        op = graph.resolve(op.inputs.get("geometry"))
    return op, chain


def _points_source(graph: SemanticGraph, op: SemanticOp) -> SemanticOp | None:
    return graph.resolve(op.inputs.get("geometry") or op.inputs.get("points"))


class PcgBuilder:
    def __init__(self, backend, result, w: PyWriter, variables: NameAllocator) -> None:
        self.backend, self.result, self.w = backend, result, w
        self.graph = result.semantic
        self.vars = variables
        self.expr = PyExpr(self.graph)
        self.streams: dict[tuple[str, str], tuple[str, list[str]]] = {}
        self.depth: dict[str, int] = {}
        self.rows: dict[int, int] = {}
        self.materials: dict[str, str] = {}

    @property
    def options(self):
        return self.result.options

    def position(self, op: SemanticOp) -> tuple[int, int]:
        depth = self.depth.get(op.id, 1)
        row = self.rows.get(depth, 0)
        self.rows[depth] = row + 1
        return depth * 400, row * 250

    def node(self, op: SemanticOp, settings_class: str, suffix: str = "") -> tuple[str, str]:
        base = python_identifier((op.display_name if self.options.preserve_names else op.kind.lower()) + suffix)
        node = self.vars.allocate(base)
        settings = self.vars.allocate(f"{node}_settings")
        x, y = self.position(op)
        self.w.line(f'{node}, {settings} = nb_pcg_node(graph, "{settings_class}", {x}, {y})')
        return node, settings

    def prop(self, settings: str, name: str, expression: str) -> None:
        self.w.line(f'nb_prop({settings}, "{name}", {expression})')

    def stream(self, value: InputValue | None) -> tuple[str, list[str]] | None:
        if isinstance(value, tuple):
            value = value[0] if value else None
        if isinstance(value, Link):
            return self.streams.get((value.op, value.output))
        return None

    def connect(self, target: str, target_pins: list[str], value: InputValue | None) -> None:
        source = self.stream(value)
        if source is not None:
            self.w.line(f"nb_edge(graph, {source[0]}, {source[1]!r}, {target}, {target_pins!r})")

    def set_output(self, op: SemanticOp, output: str, node: str, pins: list[str] | None = None) -> None:
        self.streams[(op.id, output)] = (node, pins or OUT)

    def passthrough(self, op: SemanticOp, output: str, value: InputValue | None) -> None:
        source = self.stream(value)
        if source is not None:
            self.streams[(op.id, output)] = source

    def comment(self, text: str) -> None:
        if self.options.include_comments:
            self.w.comment(text)

    def unsupported(self, op: SemanticOp, reason: str) -> None:
        self.w.line(f"NB_WARNINGS.append({f'Not translated: {op.display_name} ({op.kind}). {reason}'!r})")
        for name, ref in op.outputs.items():
            if ref.base in GEOMETRY_TYPES:
                first = next((v for v in op.inputs.values() if self.stream(v) is not None), None)
                self.passthrough(op, name, first)

    def const(self, value: InputValue | None, default: Any) -> Any:
        try:
            result = evaluate(self.graph, value, default=default)
        except (NotConstant, KeyError):
            return default
        return default if result is None else result

    def build(self) -> None:
        for op in self.graph.topological_order():
            self.depth[op.id] = 1 + max((self.depth.get(dep, 0) for dep in self.graph.dependencies(op.id)), default=0)
            classification = self.result.classification(self.graph, op)
            item = self.backend.translator(op, CTX)
            is_geometry = op.kind in POINT_KINDS | CHAIN_KINDS | {"GEOMETRY_INPUT", "GEOMETRY_OUTPUT", "INSTANCE", "REALIZE_INSTANCES"} or any(r.base in GEOMETRY_TYPES for r in op.outputs.values())
            if not is_geometry:
                continue
            self.w.blank()
            self.comment(f"{op.display_name}: {op.kind} [{classification.confidence.value}] -> {classification.implementation}  (Blender: {', '.join(op.source.types) or 'generated'})")
            if self.result.is_blocked(self.graph, op):
                self.unsupported(op, f"Skipped by strictness ({self.options.strictness.value}).")
                continue
            if item is None or classification.confidence == C.UNSUPPORTED:
                self.unsupported(op, classification.explanation)
                continue
            item.fn(self, op)


def _pcg(kind, confidence, implementation, explanation="", limitations=(), classify=None, fallback=""):
    return translator(kind, target=T, context=CTX, confidence=confidence, implementation=implementation, explanation=explanation, limitations=limitations, classify=classify, fallback=fallback)


NO_PCG = "PCG works on point data; this modelling operation has no PCG node (a Geometry Script backend could cover it later)."
for _kind in ("EXTRUDE", "SUBDIVIDE", "BOOLEAN", "CURVE", "CURVE_RESAMPLE", "CURVE_TO_MESH", "MESH_TO_CURVE", "MESH_TO_POINTS", "ATTRIBUTE_WRITE", "INSTANCE_TRANSFORM", "SWITCH"):
    translator(_kind, target=T, context=CTX, confidence=C.UNSUPPORTED, implementation="none", explanation=NO_PCG)(lambda b, op: b.unsupported(op, NO_PCG))


@_pcg("GEOMETRY_INPUT", C.EQUIVALENT, "PCG graph Input node", "The actor or volume owning the PCG component replaces the modifier object.", ("Assign the graph to a PCG Volume or a PCG Component on the actor you want to populate.",))
def _input(b: PcgBuilder, op: SemanticOp) -> None:
    b.set_output(op, "geometry", "input_node", ["Input", "In"])


@_pcg("GEOMETRY_OUTPUT", C.EQUIVALENT, "PCG graph Output node", "Final point data / spawned meshes.")
def _output(b: PcgBuilder, op: SemanticOp) -> None:
    source = b.stream(op.inputs.get("geometry"))
    if source is not None and source[0] != "input_node":
        b.w.line(f"nb_edge(graph, {source[0]}, {source[1]!r}, output_node, ['Out', 'Output'])")


def _scatter_classify(op, graph, base):
    source = graph.resolve(op.inputs.get("geometry"))
    limitations = list(base.limitations)
    confidence = base.confidence
    if source is None or source.kind != "GEOMETRY_INPUT":
        confidence = C.APPROXIMATE
        limitations.append("PCG samples the PCG component's actor surface; the Blender geometry feeding this scatter is not rebuilt.")
    if op.params.get("distribution_mode") == "poisson":
        confidence = C.APPROXIMATE
        limitations.append("Poisson disk minimum distance is not enforced.")
    if not (isinstance(op.inputs.get("selection"), Const) and op.inputs["selection"].value):
        confidence = C.APPROXIMATE
        limitations.append("The face selection is not translated; the whole surface is sampled.")
    return Classification(confidence, base.explanation, base.implementation, limitations, base.fallback)


@_pcg(
    "SCATTER",
    C.EQUIVALENT,
    "PCGSurfaceSamplerSettings",
    "Distribute Points on Faces becomes a Surface Sampler with the same density per square meter.",
    ("Sample positions differ (different generators).",),
    classify=_scatter_classify,
)
def _scatter(b: PcgBuilder, op: SemanticOp) -> None:
    node, settings = b.node(op, "PCGSurfaceSamplerSettings")
    b.connect(node, ["Surface", "In"], op.inputs.get("geometry"))
    density = op.inputs.get("density", op.inputs.get("density_max"))
    b.prop(settings, "points_per_squared_meter", b.expr.scalar(density, 10.0, ValueRole.AREA_DENSITY))
    b.prop(settings, "seed", f"int({b.expr.scalar(op.inputs.get('seed'), 0)})")
    b.set_output(op, "points", node)


def _range(b: PcgBuilder, op: SemanticOp, key: str, default: list[float]) -> list[float]:
    raw = b.const(op.inputs.get(key), default)
    items = list(raw) if isinstance(raw, (list, tuple)) else [raw] * 3
    return [float(v) for v in (items + default)[:3]]


@_pcg(
    "RANDOM_TRANSFORM",
    C.EQUIVALENT,
    "PCGTransformPointsSettings",
    "Random rotation / scale ranges become Transform Points min/max ranges.",
    ("PCG's random stream differs from Blender's; ranges are preserved.", "Euler ranges are mapped per axis to roll / pitch / yaw."),
)
def _random_transform(b: PcgBuilder, op: SemanticOp) -> None:
    node, settings = b.node(op, "PCGTransformPointsSettings")
    b.connect(node, IN, op.inputs.get("geometry"))
    if "rotation_min" in op.inputs or "rotation_max" in op.inputs:
        lo, hi = _range(b, op, "rotation_min", [0.0] * 3), _range(b, op, "rotation_max", [0.0] * 3)
        rot_lo, rot_hi = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}, {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
        for index, (axis, (component, sign)) in enumerate(unreal_axis_signs().items()):
            a, c = math.degrees(lo[index]) * sign, math.degrees(hi[index]) * sign
            rot_lo[component], rot_hi[component] = round(min(a, c), 3) + 0.0, round(max(a, c), 3) + 0.0
        b.prop(settings, "rotation_min", f"unreal.Rotator(roll={literal(rot_lo['roll'])}, pitch={literal(rot_lo['pitch'])}, yaw={literal(rot_lo['yaw'])})")
        b.prop(settings, "rotation_max", f"unreal.Rotator(roll={literal(rot_hi['roll'])}, pitch={literal(rot_hi['pitch'])}, yaw={literal(rot_hi['yaw'])})")
    if "scale_min" in op.inputs or "scale_max" in op.inputs:
        if op.params.get("uniform_scale"):
            lo, hi = b.expr.scalar(op.inputs.get("scale_min"), 1.0), b.expr.scalar(op.inputs.get("scale_max"), 1.0)
            b.prop(settings, "uniform_scale", "True")
            b.prop(settings, "scale_min", f"unreal.Vector({lo}, {lo}, {lo})")
            b.prop(settings, "scale_max", f"unreal.Vector({hi}, {hi}, {hi})")
        else:
            lo = b.expr.vector(op.inputs.get("scale_min"), [1.0] * 3, ValueRole.SCALE)
            hi = b.expr.vector(op.inputs.get("scale_max"), [1.0] * 3, ValueRole.SCALE)
            b.prop(settings, "uniform_scale", "False")
            b.prop(settings, "scale_min", f"unreal.Vector({', '.join(lo)})")
            b.prop(settings, "scale_max", f"unreal.Vector({', '.join(hi)})")
    if "seed" in op.inputs:
        b.prop(settings, "seed", f"int({b.expr.scalar(op.inputs.get('seed'), 0)})")
    b.set_output(op, "geometry", node)


def _transform_points(b: PcgBuilder, op: SemanticOp, offset_key: str, rotation_key: str | None, scale_key: str | None, stream_key: str) -> None:
    node, settings = b.node(op, "PCGTransformPointsSettings")
    b.connect(node, IN, op.inputs.get(stream_key))
    offset = b.expr.vector(op.inputs.get(offset_key), [0.0] * 3, ValueRole.POSITION)
    b.prop(settings, "offset_min", f"unreal.Vector({', '.join(offset)})")
    b.prop(settings, "offset_max", f"unreal.Vector({', '.join(offset)})")
    if rotation_key:
        pitch, yaw, roll = blender_euler_to_unreal_rotator(_range(b, op, rotation_key, [0.0] * 3))
        rotator = f"unreal.Rotator(roll={literal(round(roll, 3) + 0.0)}, pitch={literal(round(pitch, 3) + 0.0)}, yaw={literal(round(yaw, 3) + 0.0)})"
        b.prop(settings, "rotation_min", rotator)
        b.prop(settings, "rotation_max", rotator)
    if scale_key:
        scale = b.expr.vector(op.inputs.get(scale_key), [1.0] * 3, ValueRole.SCALE)
        b.prop(settings, "scale_min", f"unreal.Vector({', '.join(scale)})")
        b.prop(settings, "scale_max", f"unreal.Vector({', '.join(scale)})")
    b.set_output(op, "geometry", node)


def _on_points(op, graph, base):
    source = _points_source(graph, op)
    if source is None or source.kind not in POINT_KINDS | {"INSTANCE"}:
        return Classification(C.UNSUPPORTED, "PCG can only transform point data; this geometry is a mesh.", "none")
    for key in ("offset", "translation", "rotation", "scale", "position"):
        value = op.inputs.get(key)
        if isinstance(value, Link) and graph.ops[value.op].outputs[value.output].field:
            return Classification(C.UNSUPPORTED, "Per-point field expressions cannot be built with PCG's Python API.", "none")
    return None


@_pcg("TRANSFORM", C.EQUIVALENT, "PCGTransformPointsSettings (fixed values)", "A rigid transform of points as Transform Points with min = max.", classify=lambda op, g, base: _chain_classify(op, g, base) or _on_points(op, g, base))
def _transform(b: PcgBuilder, op: SemanticOp) -> None:
    if instance_chain(b.graph, op) is not None:
        return
    _transform_points(b, op, "translation", "rotation", "scale", "geometry")


@_pcg("TRANSFORM_POINTS", C.EQUIVALENT, "PCGTransformPointsSettings", "Fixed per-point transform.", classify=_on_points)
def _transform_points_op(b: PcgBuilder, op: SemanticOp) -> None:
    _transform_points(b, op, "offset", "rotation", "scale", "geometry")


@_pcg("SET_POSITION", C.EQUIVALENT, "PCGTransformPointsSettings (offset)", "A constant Set Position offset becomes a Transform Points offset.", classify=lambda op, g, base: Classification(C.UNSUPPORTED, "Absolute positions are not translated to PCG.", "none") if "position" in op.inputs else _on_points(op, g, base))
def _set_position(b: PcgBuilder, op: SemanticOp) -> None:
    _transform_points(b, op, "offset", None, None, "geometry")


@_pcg("MERGE", C.EQUIVALENT, "PCGMergeSettings", "Join Geometry becomes Merge Points.", ("Mesh geometry inputs are not merged; only point data and spawned results flow on.",))
def _merge(b: PcgBuilder, op: SemanticOp) -> None:
    node, settings = b.node(op, "PCGMergeSettings")
    values = op.inputs.get("geometry", ())
    for value in values if isinstance(values, tuple) else (values,):
        source = b.stream(value)
        if source is not None and source[0] != "input_node":
            b.w.line(f"nb_edge(graph, {source[0]}, {source[1]!r}, {node}, ['In'])")
    b.set_output(op, "geometry", node)


def _mask_classify(op, graph, base):
    selection = op.inputs.get("selection")
    if isinstance(selection, Const):
        return Classification(C.EXACT, "Constant selection.", "pass-through" if not selection.value else "empty")
    mask = graph.resolve(selection)
    if mask is None or mask.kind != "SPATIAL_NOISE_MASK":
        return Classification(C.UNSUPPORTED, "Only noise-based selections are translated to PCG (Spatial Noise + Density Filter).", "none")
    source = _points_source(graph, op)
    if source is None or source.kind not in POINT_KINDS:
        return Classification(C.UNSUPPORTED, "PCG can only filter point data.", "none")
    return None


@_pcg(
    "DELETE_GEOMETRY",
    C.APPROXIMATE,
    "PCGSpatialNoiseSettings + PCGDensityFilterSettings",
    "A noise-driven point deletion becomes PCG Spatial Noise written to density, filtered by the same threshold.",
    ("PCG's spatial noise is 2D and numerically different from Blender's noise.",),
    classify=_mask_classify,
)
def _delete(b: PcgBuilder, op: SemanticOp) -> None:
    _density_filter(b, op, op.inputs.get("geometry"), invert=False, output="geometry")


@_pcg("SEPARATE", C.APPROXIMATE, "Spatial Noise + Density Filter (x2)", "Noise-driven separation as two density filters.", ("PCG's spatial noise differs from Blender's.",), classify=_mask_classify)
def _separate(b: PcgBuilder, op: SemanticOp) -> None:
    _density_filter(b, op, op.inputs.get("geometry"), invert=True, output="selection")
    _density_filter(b, op, op.inputs.get("geometry"), invert=False, output="inverted")


def _density_filter(b: PcgBuilder, op: SemanticOp, stream: InputValue | None, *, invert: bool, output: str) -> None:
    selection = op.inputs.get("selection")
    if isinstance(selection, Const):
        if not selection.value:
            b.passthrough(op, output, stream)
        return
    mask = b.graph.resolve(selection)
    noise, noise_settings = b.node(op, "PCGSpatialNoiseSettings", "_noise")
    b.connect(noise, IN, stream)
    b.w.line(f'nb_prop({noise_settings}, "mode", nb_enum("PCGSpatialNoiseMode", "FRACTIONAL_BROWNIAN2D", "FRACTIONAL_BROWNIAN", "PERLIN2D"))')
    b.prop(noise_settings, "iterations", str(int(b.const(mask.inputs.get("detail"), 2.0)) + 1))
    b.w.line(f"# Blender noise scale {clean_number(float(b.const(mask.inputs.get('scale'), 5.0)))} per meter; PCG Spatial Noise scales in world units.")
    threshold = b.expr.scalar(mask.inputs.get("threshold"), 0.5)
    remap = mask.params.get("remap")
    if remap:
        span_to = remap["to_max"] - remap["to_min"] or 1.0
        threshold = f"{literal(remap['from_min'])} + ({threshold} - {literal(remap['to_min'])}) / {literal(span_to)} * {literal(remap['from_max'] - remap['from_min'])}"
    keep_above = mask.params.get("operation") in ("LESS_THAN", "LESS_EQUAL")
    if invert:
        keep_above = not keep_above
    node, settings = b.node(op, "PCGDensityFilterSettings", f"_{output}_filter")
    b.w.line(f"nb_edge(graph, {noise}, ['Out'], {node}, ['In'])")
    if keep_above:
        b.prop(settings, "lower_bound", threshold)
        b.prop(settings, "upper_bound", "1.0")
    else:
        b.prop(settings, "lower_bound", "0.0")
        b.prop(settings, "upper_bound", threshold)
    b.set_output(op, output, node)


@_pcg(
    "SPATIAL_NOISE_MASK",
    C.APPROXIMATE,
    "folded into Spatial Noise + Density Filter",
    "Consumed by the point filter that uses it.",
    ("PCG noise is 2D and differs numerically.",),
    classify=lambda op, g, base: None if all(c.kind in ("DELETE_GEOMETRY", "SEPARATE") for c, _ in g.consumers(op.id)) else Classification(C.UNSUPPORTED, "Noise masks are only translated when they drive point deletion.", "none"),
)
def _noise_mask(b: PcgBuilder, op: SemanticOp) -> None:
    return None


def _instance_classify(op, graph, base):
    source, chain = chain_source(graph, op.inputs.get("instance"))
    limitations = list(base.limitations)
    confidence = base.confidence
    if source is None or source.kind not in ("PRIMITIVE", "OBJECT_REFERENCE", "COLLECTION_REFERENCE"):
        return Classification(C.UNSUPPORTED, "The instanced geometry is procedural; PCG spawns Static Mesh assets.", "none", fallback="Convert the instance geometry to a Static Mesh asset and assign it on the spawner.")
    if source.kind != "PRIMITIVE" or source.params.get("shape") not in BASIC_SHAPES:
        limitations.append("Assign the matching Static Mesh asset on the spawner.")
    if any(o.kind == "TRANSFORM" for o in chain):
        limitations.append("Translation / rotation applied to the instance geometry is dropped; scale is kept.")
    for key in ("rotation", "scale"):
        value = op.inputs.get(key)
        if isinstance(value, Link):
            confidence = C.UNSUPPORTED
            return Classification(confidence, "Per-instance field values that are not simple random ranges cannot be built in PCG.", "none")
    return Classification(confidence, base.explanation, base.implementation, limitations, base.fallback)


@_pcg(
    "INSTANCE",
    C.APPROXIMATE,
    "PCGStaticMeshSpawnerSettings",
    "Instance on Points becomes a Static Mesh Spawner; mesh primitives map to /Engine/BasicShapes meshes scaled to size.",
    ("Geometry Nodes instances arbitrary geometry; PCG spawns Static Mesh assets.",),
    classify=_instance_classify,
)
def _instance(b: PcgBuilder, op: SemanticOp) -> None:
    source, chain = chain_source(b.graph, op.inputs.get("instance"))
    points = op.inputs.get("points")
    factor = [1.0, 1.0, 1.0]
    mesh_path = ""
    if source is not None and source.kind == "PRIMITIVE" and source.params.get("shape") in BASIC_SHAPES:
        mesh_path, unit = BASIC_SHAPES[source.params["shape"]]
        factor = _primitive_scale(b, source, unit)
    elif source is not None and source.kind == "OBJECT_REFERENCE":
        ref = b.const(source.inputs.get("object"), {}) or {}
        mesh_path = f"/Game/{unreal_asset_name(ref.get('name', 'Mesh'))}"
    for transform in (o for o in chain if o.kind == "TRANSFORM"):
        scale = _range(b, transform, "scale", [1.0, 1.0, 1.0])
        factor = [f * s for f, s in zip(factor, scale)]
    if isinstance(op.inputs.get("scale"), Const):
        constant = op.inputs["scale"].value
        constant = constant if isinstance(constant, (list, tuple)) else [constant] * 3
        factor = [f * float(s) for f, s in zip(factor, constant)]
    if any(abs(f - 1.0) > 1e-6 for f in factor):
        node, settings = b.node(op, "PCGTransformPointsSettings", "_mesh_size")
        b.connect(node, IN, points)
        vector = f"unreal.Vector({', '.join(literal(clean_number(f)) for f in factor)})"
        b.prop(settings, "scale_min", vector)
        b.prop(settings, "scale_max", vector)
        b.streams[(op.id, "_sized")] = (node, OUT)
        points = Link(op.id, "_sized")
    spawner, settings = b.node(op, "PCGStaticMeshSpawnerSettings")
    b.connect(spawner, IN, points)
    material = next((o for o in chain if o.kind == "MATERIAL_ASSIGNMENT"), None)
    material_expr = "None"
    if material is not None:
        ref = b.const(material.inputs.get("material"), {}) or {}
        if ref.get("name") in b.materials:
            material_expr = b.materials[ref["name"]]
    if mesh_path:
        b.w.line(f'nb_spawner_mesh({settings}, "{mesh_path}", {material_expr})')
    b.set_output(op, "instances", spawner)


def _primitive_scale(b: PcgBuilder, op: SemanticOp, unit_meters: float) -> list[float]:
    shape = op.params.get("shape")
    get = lambda key, default: b.const(op.inputs.get(key), default)  # noqa: E731
    if shape == "cube":
        size = get("size", [1.0, 1.0, 1.0])
        return [float(v) / unit_meters for v in size]
    if shape in ("uv_sphere", "ico_sphere"):
        return [2.0 * float(get("radius", 1.0)) / unit_meters] * 3
    if shape == "cylinder":
        r = 2.0 * float(get("radius", 1.0))
        return [r, r, float(get("depth", 2.0))]
    if shape == "cone":
        r = 2.0 * max(float(get("radius_bottom", 1.0)), float(get("radius_top", 0.0)))
        return [r, r, float(get("depth", 2.0))]
    if shape == "grid":
        return [float(get("size_x", 1.0)), float(get("size_y", 1.0)), 1.0]
    return [1.0, 1.0, 1.0]


def _chain_classify(op, graph, base):
    if instance_chain(graph, op) is not None:
        if op.kind == "MATERIAL_ASSIGNMENT":
            return Classification(C.EQUIVALENT, "Material assigned as the spawner's override material.", "Static Mesh Spawner override material")
        if op.kind == "PRIMITIVE":
            shape = op.params.get("shape")
            if shape in BASIC_SHAPES:
                return Classification(C.APPROXIMATE, f"The {shape.replace('_', ' ')} becomes {BASIC_SHAPES[shape][0]} scaled to size.", "Engine basic shape", ["Mesh resolution and UVs differ."])
            return Classification(C.UNSUPPORTED, f"No engine mesh matches a {shape}.", "none")
        if op.kind == "TRANSFORM":
            return Classification(C.APPROXIMATE, "Folded into the spawned mesh scale.", "Transform Points scale", ["Translation and rotation of the instance geometry are dropped."])
        return Classification(C.APPROXIMATE, "Referenced as a Static Mesh asset with the same name.", "Static Mesh reference", ["Make sure an asset with this name exists."])
    return None


@_pcg("PRIMITIVE", C.UNSUPPORTED, "none", "PCG does not generate meshes; primitives are only translated as instance meshes.", classify=_chain_classify)
def _primitive(b: PcgBuilder, op: SemanticOp) -> None:
    return None


@_pcg("MATERIAL_ASSIGNMENT", C.UNSUPPORTED, "none", "Materials are only translated on spawned meshes.", classify=_chain_classify)
def _material(b: PcgBuilder, op: SemanticOp) -> None:
    if instance_chain(b.graph, op) is None:
        b.passthrough(op, "geometry", op.inputs.get("geometry"))


@_pcg("OBJECT_REFERENCE", C.UNSUPPORTED, "none", "Scene objects are only translated as spawned Static Mesh references.", classify=_chain_classify)
def _object(b: PcgBuilder, op: SemanticOp) -> None:
    return None


@_pcg(
    "REALIZE_INSTANCES",
    C.APPROXIMATE,
    "none (pass-through)",
    "PCG spawns instanced static mesh components; there is no 'realize' step.",
    ("Spawned meshes stay instances.",),
)
def _realize(b: PcgBuilder, op: SemanticOp) -> None:
    b.passthrough(op, "geometry", op.inputs.get("geometry"))
