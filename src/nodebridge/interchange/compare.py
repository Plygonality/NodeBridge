"""Compare two inspected USD stages.

The verdict is geometric evidence only. It does not classify a NodeBridge
translation. Correspondence uses a provenance id when both prims carry one,
then an exact prim path. Geometry prims that cannot be paired make the
result INCONCLUSIVE rather than MATCH. Unmatched non-geometry prims are
reported and do not by themselves reject a match of the geometry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

GEOM_TYPES = frozenset({"Mesh", "Cube", "Sphere", "Cylinder", "Cone", "Capsule", "Plane", "Points", "BasisCurves", "NurbsCurves"})


class Verdict(str, Enum):
    MATCH = "MATCH"
    DIFFERENCE = "DIFFERENCE"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class PrimSummary:
    path: str
    type_name: str
    generator_id: str = ""
    world_translation: tuple[float, float, float] | None = None
    bounds_min: tuple[float, float, float] | None = None
    bounds_max: tuple[float, float, float] | None = None
    point_count: int | None = None
    face_count: int | None = None
    material_path: str = ""
    instance: bool = False
    usd_kind: str = ""

    @property
    def is_geometry(self) -> bool:
        return self.type_name in GEOM_TYPES or self.point_count is not None

    def as_dict(self) -> dict:
        data = {"path": self.path, "type": self.type_name}
        if self.generator_id:
            data["generator_id"] = self.generator_id
        if self.world_translation is not None:
            data["world_translation"] = list(self.world_translation)
        if self.bounds_min is not None and self.bounds_max is not None:
            data["bounds_min"] = list(self.bounds_min)
            data["bounds_max"] = list(self.bounds_max)
        if self.point_count is not None:
            data["point_count"] = self.point_count
        if self.face_count is not None:
            data["face_count"] = self.face_count
        if self.material_path:
            data["material_path"] = self.material_path
        if self.instance:
            data["instance"] = True
        if self.usd_kind:
            data["usd_kind"] = self.usd_kind
        return data


@dataclass
class StageSummary:
    status: str
    identifier: str
    root_layer: str = ""
    default_prim: str = ""
    prim_count: int = 0
    up_axis: str | None = None
    meters_per_unit: float | None = None
    up_axis_authored: bool = False
    meters_per_unit_authored: bool = False
    layers: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    mesh_count: int = 0
    xform_count: int = 0
    curve_count: int = 0
    points_count: int = 0
    instance_count: int = 0
    material_count: int = 0
    bounds_min: tuple[float, float, float] | None = None
    bounds_max: tuple[float, float, float] | None = None
    prims: list[PrimSummary] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "identifier": self.identifier,
            "root_layer": self.root_layer,
            "default_prim": self.default_prim,
            "prim_count": self.prim_count,
            "up_axis": self.up_axis,
            "meters_per_unit": self.meters_per_unit,
            "up_axis_authored": self.up_axis_authored,
            "meters_per_unit_authored": self.meters_per_unit_authored,
            "layers": list(self.layers),
            "references": list(self.references),
            "counts": {
                "mesh": self.mesh_count,
                "xform": self.xform_count,
                "curves": self.curve_count,
                "points": self.points_count,
                "instances": self.instance_count,
                "materials": self.material_count,
            },
            "bounds_min": list(self.bounds_min) if self.bounds_min is not None else None,
            "bounds_max": list(self.bounds_max) if self.bounds_max is not None else None,
            "prims": [prim.as_dict() for prim in self.prims],
            "missing": list(self.missing),
            "warnings": list(self.warnings),
            "error": self.error,
            "limitations": [
                "World bounds are axis-aligned and include transforms. They are not a vertex-identity test.",
                "Instance prototypes are not expanded.",
                "USD kind (component, group, assembly) is scene metadata, not a Geometry Nodes group.",
            ],
        }


@dataclass
class CompareResult:
    source_stage: dict
    target_stage: dict
    matched_prim_count: int
    unmatched_prims: list[str]
    transform_differences: list[dict]
    bounds_differences: list[dict]
    topology_differences: list[dict]
    material_binding_differences: list[dict]
    warnings: list[str]
    verdict: Verdict

    def as_dict(self) -> dict:
        return {
            "source_stage": self.source_stage,
            "target_stage": self.target_stage,
            "matched_prim_count": self.matched_prim_count,
            "unmatched_prims": list(self.unmatched_prims),
            "transform_differences": self.transform_differences,
            "bounds_differences": self.bounds_differences,
            "topology_differences": self.topology_differences,
            "material_binding_differences": self.material_binding_differences,
            "warnings": list(self.warnings),
            "verdict": self.verdict.value,
            "note": "USD comparison is geometric evidence. NodeBridge translation confidence is the EXACT/EQUIVALENT/APPROXIMATE/UNSUPPORTED report.",
        }


def _meters(value: float, meters_per_unit: float | None) -> float:
    scale = 1.0 if meters_per_unit is None else meters_per_unit
    return value * scale


def _far(a: tuple[float, float, float], b: tuple[float, float, float], scale_a: float | None, scale_b: float | None, tolerance: float) -> bool:
    return any(abs(_meters(x, scale_a) - _meters(y, scale_b)) > tolerance for x, y in zip(a, b))


def _pair(source: StageSummary, target: StageSummary):
    used_s: set[str] = set()
    used_t: set[str] = set()
    pairs: list[tuple[PrimSummary, PrimSummary, str]] = []
    source_by_id = {prim.generator_id: prim for prim in source.prims if prim.generator_id}
    target_by_id = {prim.generator_id: prim for prim in target.prims if prim.generator_id}
    for gid in sorted(set(source_by_id) & set(target_by_id)):
        left = source_by_id[gid]
        right = target_by_id[gid]
        pairs.append((left, right, "provenance"))
        used_s.add(left.path)
        used_t.add(right.path)
    target_by_path = {prim.path: prim for prim in target.prims}
    for prim in source.prims:
        if prim.path in used_s:
            continue
        other = target_by_path.get(prim.path)
        if other is not None and other.path not in used_t:
            pairs.append((prim, other, "path"))
            used_s.add(prim.path)
            used_t.add(other.path)
    unmatched = [f"source:{prim.path}" for prim in source.prims if prim.path not in used_s]
    unmatched.extend(f"target:{prim.path}" for prim in target.prims if prim.path not in used_t)
    unpaired_geometry = any(prim.is_geometry and prim.path not in used_s for prim in source.prims) or any(
        prim.is_geometry and prim.path not in used_t for prim in target.prims
    )
    return pairs, unmatched, unpaired_geometry


def compare_summaries(source: StageSummary, target: StageSummary, *, tolerance: float = 1e-4) -> CompareResult:
    warnings = list(source.warnings) + list(target.warnings)
    if source.status != "open" or target.status != "open":
        warnings.append("One or both stages did not open.")
        return _result(source, target, [], [], [], [], [], [], warnings, Verdict.INCONCLUSIVE)
    if source.missing or target.missing:
        warnings.append("A stage has missing references: " + ", ".join(source.missing + target.missing))
    units_known = source.meters_per_unit is not None and target.meters_per_unit is not None
    if not units_known:
        warnings.append("metersPerUnit is missing on at least one stage. Numeric comparison uses stage units and cannot confirm physical scale.")
    pairs, unmatched, unpaired_geometry = _pair(source, target)
    transforms: list[dict] = []
    bounds: list[dict] = []
    topology: list[dict] = []
    materials: list[dict] = []
    metric_gap = False
    for left, right, how in pairs:
        label = left.path if left.path == right.path else f"{left.path} ~ {right.path}"
        if left.world_translation is not None and right.world_translation is not None:
            if _far(left.world_translation, right.world_translation, source.meters_per_unit, target.meters_per_unit, tolerance):
                transforms.append(
                    {
                        "prim": label,
                        "match": how,
                        "source": list(left.world_translation),
                        "target": list(right.world_translation),
                    }
                )
        elif left.world_translation is not None or right.world_translation is not None:
            metric_gap = True
            warnings.append(f"{label}: transform exists on only one prim")
        if left.bounds_min is not None and right.bounds_min is not None and left.bounds_max is not None and right.bounds_max is not None:
            if _far(left.bounds_min, right.bounds_min, source.meters_per_unit, target.meters_per_unit, tolerance) or _far(
                left.bounds_max, right.bounds_max, source.meters_per_unit, target.meters_per_unit, tolerance
            ):
                bounds.append(
                    {
                        "prim": label,
                        "match": how,
                        "source_min": list(left.bounds_min),
                        "source_max": list(left.bounds_max),
                        "target_min": list(right.bounds_min),
                        "target_max": list(right.bounds_max),
                    }
                )
        elif left.is_geometry and right.is_geometry and (left.bounds_min is None or right.bounds_min is None):
            metric_gap = True
            warnings.append(f"{label}: bounds exist on only one prim")
        if left.point_count != right.point_count or left.face_count != right.face_count:
            if left.point_count is None and right.point_count is None and left.face_count is None and right.face_count is None:
                pass
            elif None in (left.point_count, right.point_count, left.face_count, right.face_count) and (
                left.point_count != right.point_count or left.face_count != right.face_count
            ):
                # Authored topology on one side only is a measured difference when the other side is an implicit prim.
                if (left.point_count is None) != (right.point_count is None) or (left.face_count is None) != (right.face_count is None):
                    topology.append({"prim": label, "match": how, "source_points": left.point_count, "target_points": right.point_count, "source_faces": left.face_count, "target_faces": right.face_count})
            else:
                topology.append({"prim": label, "match": how, "source_points": left.point_count, "target_points": right.point_count, "source_faces": left.face_count, "target_faces": right.face_count})
        if left.material_path != right.material_path:
            materials.append({"prim": label, "match": how, "source": left.material_path, "target": right.material_path})

    measured = bool(transforms or bounds or topology or materials)
    if not pairs and (source.prims or target.prims):
        verdict = Verdict.INCONCLUSIVE
        warnings.append("No prim correspondence was found.")
    elif measured:
        verdict = Verdict.DIFFERENCE
    elif unpaired_geometry or not units_known or metric_gap or source.missing or target.missing:
        verdict = Verdict.INCONCLUSIVE
        if unpaired_geometry:
            warnings.append("Geometry prims have no provenance id or path correspondence.")
    elif not source.prims and not target.prims:
        verdict = Verdict.INCONCLUSIVE
        warnings.append("Both stages have no prims.")
    else:
        verdict = Verdict.MATCH
    return _result(source, target, unmatched, transforms, bounds, topology, materials, pairs, warnings, verdict)


def _result(source, target, unmatched, transforms, bounds, topology, materials, pairs, warnings, verdict: Verdict) -> CompareResult:
    return CompareResult(
        source_stage={"identifier": source.identifier, "default_prim": source.default_prim, "prim_count": source.prim_count},
        target_stage={"identifier": target.identifier, "default_prim": target.default_prim, "prim_count": target.prim_count},
        matched_prim_count=len(pairs) if isinstance(pairs, list) else 0,
        unmatched_prims=unmatched,
        transform_differences=transforms,
        bounds_differences=bounds,
        topology_differences=topology,
        material_binding_differences=materials,
        warnings=warnings,
        verdict=verdict,
    )


def compare_stages(source: Path, target: Path, *, tolerance: float = 1e-4) -> CompareResult:
    """Open two USD stages. Requires pxr."""
    from .usd.availability import require_pxr
    from .usd.inspect import inspect_stage

    require_pxr("USD stage comparison")
    return compare_summaries(inspect_stage(source), inspect_stage(target), tolerance=tolerance)
