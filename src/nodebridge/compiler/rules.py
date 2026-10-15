"""Built-in semantic rewrite rules.

These are target-independent normalizations. Each rule is small and
independently testable; new rules register with ``@rewrite_rule``.
"""

from __future__ import annotations

from ..ir.graph import TreeKind
from ..ir.semantic import Const, Link, Param, SemanticGraph, SemanticOp, SourceRef
from ..ir.types import DataType, TypeRef
from .evaluate import FOLDABLE, NotConstant, evaluate_op
from .rewrite import Match, Pattern, remove_unused, rewrite_rule

GEOMETRY = (TreeKind.GEOMETRY,)


def _all_const(op: SemanticOp) -> bool:
    return all(isinstance(v, Const) for v in op.inputs.values())


def _const_match(graph: SemanticGraph, op: SemanticOp) -> Match | None:
    if op.kind in FOLDABLE and op.inputs and _all_const(op) and not any(ref.field for ref in op.outputs.values()):
        return Match(op, {"op": op})
    return None


@rewrite_rule("fold_constants", "Folded constant math", matcher=_const_match, priority=10)
def _fold_constants(graph: SemanticGraph, m: Match) -> bool:
    op = m.root
    try:
        values = evaluate_op(graph, op)
    except (NotConstant, ValueError, ZeroDivisionError, OverflowError):
        return False
    for output, ref in op.outputs.items():
        if output in values:
            graph.replace_uses(Link(op.id, output), Const(values[output], ref.base))
    graph.remove(op.id)
    return True


@rewrite_rule("fold_switch", "Resolved a switch with a constant condition", pattern=Pattern(kind="SWITCH", where=lambda g, op: isinstance(op.inputs.get("switch"), Const)), priority=10)
def _fold_switch(graph: SemanticGraph, m: Match) -> bool:
    op = m.root
    chosen = op.inputs.get("true" if op.inputs["switch"].value else "false")
    graph.replace_uses(Link(op.id, "output"), chosen if chosen is not None else Const(None, op.outputs["output"].base))
    graph.remove(op.id)
    remove_unused(graph, [link.op for _, link in op.links()])
    return True


def _is_identity_transform(graph: SemanticGraph, op: SemanticOp) -> bool:
    checks = (("translation", [0.0, 0.0, 0.0]), ("rotation", [0.0, 0.0, 0.0]), ("scale", [1.0, 1.0, 1.0]))
    for name, identity in checks:
        value = op.inputs.get(name)
        if value is None:
            continue
        if not isinstance(value, Const) or [round(float(v), 9) for v in value.value] != identity:
            return False
    return True


@rewrite_rule("identity_transform", "Removed an identity transform", pattern=Pattern(kind="TRANSFORM", where=_is_identity_transform), kinds=GEOMETRY, priority=20)
def _identity_transform(graph: SemanticGraph, m: Match) -> bool:
    op = m.root
    graph.replace_uses(Link(op.id, "geometry"), op.inputs.get("geometry", Const(None, DataType.GEOMETRY)))
    graph.remove(op.id)
    return True


# --- random instance transforms --------------------------------------------
def _implicit_element_id(graph: SemanticGraph, value) -> bool:
    op = graph.resolve(value)
    return op is not None and op.kind == "FIELD_INPUT" and op.params.get("field") in ("id", "index")


def _random_range(graph: SemanticGraph, value, data_types: tuple[str, ...]) -> SemanticOp | None:
    op = graph.resolve(value)
    if op is None or op.kind != "RANDOM" or op.params.get("data_type") not in data_types:
        return None
    if graph.use_count(op.id) != 1 or not _implicit_element_id(graph, op.inputs.get("id")):
        return None
    for key in ("min", "max", "seed"):
        if not isinstance(op.inputs.get(key), (Const, Param)) and op.inputs.get(key) is not None:
            return None
    return op


def _insert_random_transform(graph: SemanticGraph, before: SemanticOp, random: SemanticOp, attribute: str, *, source: SourceRef) -> SemanticOp:
    uniform = random.params.get("data_type") == "FLOAT"
    inputs = {"geometry": before.inputs["points"], f"{attribute}_min": random.inputs.get("min"), f"{attribute}_max": random.inputs.get("max")}
    if random.inputs.get("seed") is not None:
        inputs["seed"] = random.inputs["seed"]
    op = SemanticOp(
        id=graph.new_id("random_transform"),
        kind="RANDOM_TRANSFORM",
        inputs={k: v for k, v in inputs.items() if v is not None},
        params={"uniform_scale": uniform and attribute == "scale"},
        outputs={"geometry": TypeRef(DataType.POINTS)},
        name=random.display_name,
        source=random.source.merged(source),
    )
    graph.add(op)
    before.inputs["points"] = Link(op.id, "geometry")
    return op


def _random_instance_match(graph: SemanticGraph, op: SemanticOp) -> Match | None:
    if op.kind != "INSTANCE" or "points" not in op.inputs:
        return None
    for attribute, types in (("scale", ("FLOAT", "FLOAT_VECTOR")), ("rotation", ("FLOAT_VECTOR",))):
        random = _random_range(graph, op.inputs.get(attribute), types)
        if random is not None:
            return Match(op, {"random": random, attribute: random})
    return None


@rewrite_rule("random_instance_attributes", "Recognized random per-instance scale/rotation as RandomTransform", matcher=_random_instance_match, kinds=GEOMETRY)
def _random_instance(graph: SemanticGraph, m: Match) -> bool:
    instance, random = m.root, m["random"]
    attribute = "scale" if "scale" in m.bindings else "rotation"
    _insert_random_transform(graph, instance, random, attribute, source=instance.source)
    instance.inputs.pop(attribute, None)
    graph.remove(random.id)
    remove_unused(graph, [link.op for _, link in random.links()])
    return True


def _uniform_instance_scale(graph: SemanticGraph, instance: SemanticOp) -> bool:
    value = instance.inputs.get("scale")
    if value is None:
        return True
    if isinstance(value, Const):
        components = value.value if isinstance(value.value, (list, tuple)) else [value.value] * 3
        return len(set(round(float(c), 9) for c in components)) == 1
    op = graph.resolve(value)
    return op is not None and op.kind == "RANDOM" and op.params.get("data_type") == "FLOAT"


def _zero(value, length: int = 3) -> bool:
    return value is None or (isinstance(value, Const) and all(abs(float(c)) < 1e-9 for c in (value.value if isinstance(value.value, (list, tuple)) else [value.value] * length)))


def _instance_transform_match(graph: SemanticGraph, op: SemanticOp) -> Match | None:
    if op.kind != "INSTANCE_TRANSFORM" or op.params.get("mode") not in ("rotate", "scale"):
        return None
    instance = graph.resolve(op.inputs.get("geometry"))
    if instance is None or instance.kind != "INSTANCE" or graph.use_count(instance.id) != 1:
        return None
    if op.inputs.get("selection", Const(True)) != Const(True, DataType.BOOL) and not (isinstance(op.inputs.get("selection"), Const) and op.inputs["selection"].value is True):
        return None
    local = op.inputs.get("local_space")
    if not (isinstance(local, Const) and local.value) or not _zero(op.inputs.get("pivot")):
        return None
    attribute = "rotation" if op.params["mode"] == "rotate" else "scale"
    random = _random_range(graph, op.inputs.get(attribute), ("FLOAT_VECTOR",) if attribute == "rotation" else ("FLOAT", "FLOAT_VECTOR"))
    if random is None:
        return None
    if attribute == "rotation" and (not _zero(instance.inputs.get("rotation")) or not _uniform_instance_scale(graph, instance)):
        return None
    return Match(op, {"instance": instance, "random": random})


@rewrite_rule(
    "random_instance_transform",
    "Folded Rotate/Scale Instances with a random value into a RandomTransform before instancing",
    matcher=_instance_transform_match,
    kinds=GEOMETRY,
)
def _random_instance_transform(graph: SemanticGraph, m: Match) -> bool:
    op, instance, random = m.root, m["instance"], m["random"]
    attribute = "rotation" if op.params["mode"] == "rotate" else "scale"
    _insert_random_transform(graph, instance, random, attribute, source=op.source)
    graph.replace_uses(Link(op.id, "geometry"), Link(instance.id, "instances"))
    instance.source = instance.source.merged(op.source)
    graph.remove(op.id)
    graph.remove(random.id)
    remove_unused(graph, [link.op for _, link in random.links()] + [link.op for _, link in op.links()])
    return True


# --- spatial noise mask -----------------------------------------------------
def _noise_mask_match(graph: SemanticGraph, op: SemanticOp) -> Match | None:
    if op.kind != "COMPARE" or op.params.get("data_type", "FLOAT") != "FLOAT":
        return None
    if op.params.get("operation") not in ("LESS_THAN", "LESS_EQUAL", "GREATER_THAN", "GREATER_EQUAL"):
        return None
    if not isinstance(op.inputs.get("b"), (Const, Param)):
        return None
    upstream = graph.resolve(op.inputs.get("a"))
    remap = None
    if upstream is not None and upstream.kind == "MAP_RANGE":
        if graph.use_count(upstream.id) != 1 or upstream.params.get("interpolation") != "LINEAR" or upstream.params.get("data_type") != "FLOAT":
            return None
        keys = ("from_min", "from_max", "to_min", "to_max")
        if not all(isinstance(upstream.inputs.get(k), Const) for k in keys):
            return None
        remap = upstream
        upstream = graph.resolve(upstream.inputs.get("value"))
    if upstream is None or upstream.kind != "NOISE" or graph.use_count(upstream.id) != 1:
        return None
    if upstream.params.get("dimensions") != "3D" or upstream.params.get("noise_type", "FBM") != "FBM":
        return None
    value = op.inputs["a"] if remap is None else remap.inputs["value"]
    if not isinstance(value, Link) or value.output != "fac":
        return None
    position = graph.resolve(upstream.inputs.get("vector"))
    if position is None or position.kind != "FIELD_INPUT" or position.params.get("field") != "position":
        return None
    for key in ("scale", "detail", "roughness"):
        if not isinstance(upstream.inputs.get(key), (Const, Param)):
            return None
    bindings = {"noise": upstream}
    if remap is not None:
        bindings["remap"] = remap
    return Match(op, bindings)


@rewrite_rule("spatial_noise_mask", "Recognized Position -> Noise -> Map Range -> Compare as a SpatialNoiseMask", matcher=_noise_mask_match, kinds=GEOMETRY)
def _spatial_noise_mask(graph: SemanticGraph, m: Match) -> bool:
    compare, noise, remap = m.root, m["noise"], m.get("remap")
    params = {"operation": compare.params["operation"], "remap": None, "lacunarity": noise.inputs.get("lacunarity", Const(2.0)).value if isinstance(noise.inputs.get("lacunarity"), Const) else 2.0}
    if remap is not None:
        params["remap"] = {k: float(remap.inputs[k].value) for k in ("from_min", "from_max", "to_min", "to_max")}
        params["remap"]["clamp"] = bool(remap.params.get("clamp", True))
    source = compare.source.merged(noise.source)
    if remap is not None:
        source = source.merged(remap.source)
    mask = SemanticOp(
        id=graph.new_id("spatial_noise_mask"),
        kind="SPATIAL_NOISE_MASK",
        inputs={
            "vector": noise.inputs["vector"],
            "scale": noise.inputs.get("scale", Const(5.0, DataType.FLOAT)),
            "detail": noise.inputs.get("detail", Const(2.0, DataType.FLOAT)),
            "roughness": noise.inputs.get("roughness", Const(0.5, DataType.FLOAT)),
            "threshold": compare.inputs["b"],
        },
        params=params,
        outputs={"mask": TypeRef(DataType.BOOL, True)},
        name=noise.display_name,
        source=source,
    )
    graph.add(mask)
    graph.replace_uses(Link(compare.id, "result"), Link(mask.id, "mask"))
    graph.remove(compare.id)
    if remap is not None:
        graph.remove(remap.id)
    graph.remove(noise.id)
    return True


# --- compositor vignette ---------------------------------------------------
def _vignette_match(graph: SemanticGraph, op: SemanticOp) -> Match | None:
    if op.kind != "MIX" or op.params.get("blend_type") != "MULTIPLY":
        return None
    for image_key, mask_key in (("a", "b"), ("b", "a")):
        upstream = graph.resolve(op.inputs.get(mask_key))
        blur = None
        if upstream is not None and upstream.kind == "BLUR" and graph.use_count(upstream.id) == 1:
            blur = upstream
            upstream = graph.resolve(upstream.inputs.get("image"))
        if upstream is not None and upstream.kind == "ELLIPSE_MASK" and graph.use_count(upstream.id) == 1 and op.inputs.get(image_key) is not None:
            bindings = {"mask": upstream}
            if blur is not None:
                bindings["blur"] = blur
            return Match(op, bindings)
    return None


@rewrite_rule("vignette", "Recognized Ellipse Mask -> Blur -> Multiply as a Vignette", matcher=_vignette_match, kinds=(TreeKind.COMPOSITOR,))
def _vignette(graph: SemanticGraph, m: Match) -> bool:
    mix, mask, blur = m.root, m["mask"], m.get("blur")
    image = mix.inputs["a"] if graph.resolve(mix.inputs.get("a")) not in (mask, blur) else mix.inputs["b"]
    source = mix.source.merged(mask.source)
    if blur is not None:
        source = source.merged(blur.source)
    vignette = SemanticOp(
        id=graph.new_id("vignette"),
        kind="VIGNETTE",
        inputs={
            "image": image,
            "intensity": mix.inputs.get("factor", Const(1.0, DataType.FLOAT)),
            "size": mask.inputs.get("size", Const([0.5, 0.5], DataType.VECTOR2)),
            "softness": blur.inputs.get("size", Const([0.0, 0.0], DataType.VECTOR2)) if blur is not None else Const([0.0, 0.0], DataType.VECTOR2),
        },
        params={"blur_relative": bool(blur.params.get("relative")) if blur is not None else False},
        outputs={"image": TypeRef(DataType.COLOR)},
        name=mix.display_name,
        source=source,
    )
    graph.add(vignette)
    graph.replace_uses(Link(mix.id, "result"), Link(vignette.id, "image"))
    for op in (mix, blur, mask):
        if op is not None:
            graph.remove(op.id)
    return True
