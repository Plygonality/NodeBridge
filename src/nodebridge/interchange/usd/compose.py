"""Author a root stage that references exported geometry.

The geometry layer is not flattened or rewritten. The root layer sublayers
it with a relative path and writes NodeBridge custom data as an ``over``
on the default prim. Relative paths keep working after the bundle directory
is moved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..errors import BundleError
from .annotate import apply_provenance, provenance_data
from .geometry import stage_axis_metadata


@dataclass
class ComposedStage:
    default_prim: str = ""
    up_axis: str | None = None
    meters_per_unit: float | None = None
    warnings: list[str] = field(default_factory=list)


def _open_stage(path: Path, label: str):
    from pxr import Usd

    try:
        stage = Usd.Stage.Open(str(path))
    except Exception as exc:
        raise BundleError(f"could not open {label}: {exc}") from exc
    if not stage:
        raise BundleError(f"could not open {label}: {path.name}")
    return stage


def _author_metadata(stage, metadata: dict) -> None:
    from pxr import UsdGeom

    if metadata.get("up_axis"):
        UsdGeom.SetStageUpAxis(stage, metadata["up_axis"])
    if metadata.get("meters_per_unit") is not None:
        UsdGeom.SetStageMetersPerUnit(stage, float(metadata["meters_per_unit"]))


def _single_root(stage) -> str:
    roots = list(stage.GetPseudoRoot().GetChildren())
    if len(roots) == 1:
        return str(roots[0].GetPath())
    return ""


def write_layered_root(
    root_usda: Path,
    *,
    geometry_relative: str,
    geometry_file: Path,
    generator_id: str,
    generator_revision: str,
    manifest_relative: str,
    procedural: bool = False,
    semantic_relative: str = "",
) -> ComposedStage:
    from pxr import Usd

    geometry = _open_stage(geometry_file, "geometry layer")
    metadata = stage_axis_metadata(geometry)
    warnings: list[str] = []
    default_prim = metadata["default_prim"]
    if not default_prim:
        default_prim = _single_root(geometry)
        if default_prim:
            warnings.append("Geometry layer had no default prim. The composition root uses its only root prim.")
        else:
            warnings.append("Geometry layer has no default prim. The composition root does not invent one.")
    if root_usda.exists():
        root_usda.unlink()
    stage = Usd.Stage.CreateNew(str(root_usda))
    if not stage:
        raise BundleError(f"could not create {root_usda.name}")
    stage.GetRootLayer().subLayerPaths.append(geometry_relative)
    _author_metadata(stage, metadata)
    if default_prim:
        prim = stage.GetPrimAtPath(default_prim)
        if not prim:
            raise BundleError(f"referenced geometry did not resolve prim {default_prim}. The relative path {geometry_relative!r} was not composed.")
        stage.SetDefaultPrim(prim)
        apply_provenance(
            stage.OverridePrim(default_prim),
            provenance_data(
                generator_id=generator_id,
                manifest_relative=manifest_relative,
                generator_revision=generator_revision,
            ),
        )
    if procedural:
        _author_procedural_marker(stage, default_prim, semantic_relative, warnings)
    stage.GetRootLayer().Save()
    _assert_reference_resolves(root_usda, geometry_relative)
    return ComposedStage(default_prim=default_prim, up_axis=metadata["up_axis"], meters_per_unit=metadata["meters_per_unit"], warnings=warnings)


def write_provenance_overlay(
    overlay_path: Path,
    *,
    scene_relative: str,
    default_prim: str,
    generator_id: str,
    manifest_relative: str,
) -> None:
    """Overlay custom data without modifying the exported geometry file."""
    from pxr import Usd

    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    if overlay_path.exists():
        overlay_path.unlink()
    stage = Usd.Stage.CreateNew(str(overlay_path))
    if not stage:
        raise BundleError(f"could not create {overlay_path.name}")
    stage.GetRootLayer().subLayerPaths.append(scene_relative)
    stage.GetRootLayer().Save()
    stage = _open_stage(overlay_path, "provenance overlay")
    metadata = stage_axis_metadata(stage)
    _author_metadata(stage, metadata)
    prim = stage.GetPrimAtPath(default_prim)
    if not prim:
        raise BundleError(f"provenance overlay could not find {default_prim} through {scene_relative}")
    stage.SetDefaultPrim(prim)
    apply_provenance(
        stage.OverridePrim(default_prim),
        provenance_data(generator_id=generator_id, manifest_relative=manifest_relative),
    )
    stage.GetRootLayer().Save()


def _author_procedural_marker(stage, default_prim: str, semantic_relative: str, warnings: list[str]) -> None:
    try:
        from pxr import UsdProc
    except ImportError:
        warnings.append("UsdProc is not available in this pxr build. The experimental procedural marker was not written.")
        return
    if not default_prim:
        warnings.append("No default prim, so the experimental UsdProc marker was not written.")
        return
    path = default_prim.rstrip("/") + "/NodeBridgeProcedural"
    procedural = UsdProc.GenerativeProcedural.Define(stage, path)
    procedural.CreateProceduralSystemAttr().Set("nodebridge")
    procedural.GetPrim().SetCustomDataByKey(
        "nodebridge",
        {
            "schema": "nodebridge.provenance",
            "schema_version": 1,
            "role": "procedural-marker",
            "semantic": semantic_relative,
            "note": "Identifies NodeBridge as the procedural system. Generic DCCs do not evaluate this prim.",
        },
    )
    warnings.append(
        "UsdProc GenerativeProcedural is an experimental marker only. No generic DCC evaluates it without a NodeBridge-aware implementation."
    )


def _assert_reference_resolves(root_usda: Path, geometry_relative: str) -> None:
    stage = _open_stage(root_usda, "composition root")
    layer = stage.GetRootLayer()
    absolute = layer.ComputeAbsolutePath(geometry_relative)
    if not absolute or not Path(absolute).is_file():
        raise BundleError(f"composition reference does not resolve: {geometry_relative}")
