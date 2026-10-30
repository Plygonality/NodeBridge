"""Read-only USD stage inspection.

The summary is deterministic: prims are ordered by path, and layer
identifiers inside the stage directory are stored relative to that
directory so a moved bundle does not change the reported paths.
"""

from __future__ import annotations

from pathlib import Path

from ..compare import PrimSummary, StageSummary
from .annotate import read_provenance
from .availability import require_pxr
from .geometry import CURVE_TYPES, MESH_TYPES, is_instance, material_path, stage_axis_metadata, topology, usd_kind, world_bounds, world_translation


def inspect_stage(path: Path) -> StageSummary:
    require_pxr("USD stage inspection")
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    from pxr import Sdf, Usd

    name = file_path.name
    try:
        stage = Usd.Stage.Open(str(file_path))
    except Exception as exc:
        return StageSummary(status="error", identifier=name, root_layer=name, error=str(exc), warnings=[f"could not open stage: {exc}"])
    if not stage:
        return StageSummary(status="error", identifier=name, root_layer=name, error=f"could not open {name}", warnings=[f"could not open {name}"])

    root_dir = file_path.parent.resolve()
    metadata = stage_axis_metadata(stage)
    warnings: list[str] = []
    if not metadata["up_axis_authored"]:
        warnings.append("upAxis is not authored. The reported value is the USD composition default.")
    if not metadata["meters_per_unit_authored"]:
        warnings.append("metersPerUnit is not authored. The reported value is the USD composition default.")
    if not metadata["default_prim"]:
        warnings.append("The stage has no default prim.")

    missing: list[str] = []
    references: list[str] = []
    layers: list[str] = []
    seen_layers: set[str] = set()
    _walk_layer(stage.GetRootLayer(), root_dir, seen_layers, missing, references, layers, Sdf)

    prims: list[PrimSummary] = []
    mesh_count = xform_count = curve_count = points_count = instance_count = material_count = 0
    bounds_min = None
    bounds_max = None
    for prim in stage.Traverse():
        type_name = str(prim.GetTypeName())
        if type_name in MESH_TYPES:
            mesh_count += 1
        elif type_name == "Xform":
            xform_count += 1
        elif type_name in CURVE_TYPES:
            curve_count += 1
        elif type_name == "Points":
            points_count += 1
        elif type_name == "Material":
            material_count += 1
        if is_instance(prim):
            instance_count += 1
        provenance = read_provenance(prim)
        points, faces = topology(prim)
        bounds = world_bounds(prim)
        summary = PrimSummary(
            path=str(prim.GetPath()),
            type_name=type_name,
            generator_id=str(provenance.get("generator_id", "")),
            world_translation=world_translation(prim),
            bounds_min=bounds[0] if bounds else None,
            bounds_max=bounds[1] if bounds else None,
            point_count=points,
            face_count=faces,
            material_path=material_path(prim),
            instance=is_instance(prim),
            usd_kind=usd_kind(prim),
        )
        prims.append(summary)
        if bounds and summary.type_name in MESH_TYPES or (bounds and summary.type_name in CURVE_TYPES):
            bounds_min, bounds_max = _union(bounds_min, bounds_max, bounds[0], bounds[1])
    prims.sort(key=lambda item: item.path)
    missing_sorted = sorted(set(missing))
    if missing_sorted:
        warnings.append("Unresolved references: " + ", ".join(missing_sorted))
    return StageSummary(
        status="open",
        identifier=name,
        root_layer=name,
        default_prim=metadata["default_prim"],
        prim_count=len(prims),
        up_axis=metadata["up_axis"],
        meters_per_unit=metadata["meters_per_unit"],
        up_axis_authored=metadata["up_axis_authored"],
        meters_per_unit_authored=metadata["meters_per_unit_authored"],
        layers=layers,
        references=sorted(set(references)),
        mesh_count=mesh_count,
        xform_count=xform_count,
        curve_count=curve_count,
        points_count=points_count,
        instance_count=instance_count,
        material_count=material_count,
        bounds_min=bounds_min,
        bounds_max=bounds_max,
        prims=prims,
        missing=missing_sorted,
        warnings=warnings,
    )


def _union(current_min, current_max, new_min, new_max):
    if current_min is None:
        return new_min, new_max
    return tuple(min(a, b) for a, b in zip(current_min, new_min)), tuple(max(a, b) for a, b in zip(current_max, new_max))


def _display(root_dir: Path, identifier: str) -> str:
    if not identifier or identifier.startswith("anon:"):
        return identifier
    candidate = Path(identifier)
    if not candidate.is_absolute():
        return identifier.replace("\\", "/")
    try:
        return candidate.resolve().relative_to(root_dir).as_posix()
    except (OSError, ValueError):
        return candidate.name


def _external_references(layer) -> list[str]:
    getter = getattr(layer, "GetExternalReferences", None)
    if getter is None:
        return [str(item) for item in layer.subLayerPaths]
    try:
        refs = getter()
    except Exception:
        return [str(item) for item in layer.subLayerPaths]
    if isinstance(refs, (list, tuple)):
        return [str(item) for item in refs]
    return [str(item) for item in layer.subLayerPaths]


def _walk_layer(layer, root_dir: Path, seen: set[str], missing: list[str], references: list[str], layers: list[str], sdf) -> None:
    identifier = layer.identifier or ""
    if identifier in seen:
        return
    seen.add(identifier)
    shown = _display(root_dir, identifier)
    if shown and shown not in layers:
        layers.append(shown)
    for asset in _external_references(layer):
        if asset not in references:
            references.append(asset)
        try:
            absolute = layer.ComputeAbsolutePath(asset)
        except Exception:
            absolute = ""
        if not absolute or not Path(absolute).is_file():
            missing.append(asset)
            continue
        opened = sdf.Layer.FindOrOpen(absolute)
        if opened is not None:
            _walk_layer(opened, root_dir, seen, missing, references, layers, sdf)
