"""Read bounded geometry facts from an open USD stage.

Bounds are axis-aligned and in world space, in the stage's linear units.
They are statistics, not a claim of vertex identity. USD model kinds are
recorded as scene organization and are not Geometry Nodes groups.
"""

from __future__ import annotations

MESH_TYPES = frozenset({"Mesh", "Cube", "Sphere", "Cylinder", "Cone", "Capsule", "Plane"})
CURVE_TYPES = frozenset({"BasisCurves", "NurbsCurves"})


def _round(value: float) -> float:
    return round(float(value), 9)


def _vec3(value) -> tuple[float, float, float]:
    return (_round(value[0]), _round(value[1]), _round(value[2]))


def stage_axis_metadata(stage) -> dict:
    from pxr import UsdGeom

    up = UsdGeom.GetStageUpAxis(stage)
    meters = UsdGeom.GetStageMetersPerUnit(stage)
    default = stage.GetDefaultPrim()
    return {
        "up_axis": str(up) if up else None,
        "meters_per_unit": float(meters) if meters is not None else None,
        "default_prim": str(default.GetPath()) if default else "",
        "up_axis_authored": _layer_has_info(stage, "upAxis"),
        "meters_per_unit_authored": _layer_has_info(stage, "metersPerUnit"),
    }


def _layer_has_info(stage, key: str) -> bool:
    """True when any used layer authors this stage metadata key.

    Opinions live on the layer's pseudo-root, including opinions that
    arrive through a sublayer. ``Layer.HasInfo`` is not part of this API.
    """
    try:
        if stage.HasAuthoredMetadata(key):
            return True
    except Exception:
        pass
    for layer in stage.GetUsedLayers():
        root = getattr(layer, "pseudoRoot", None)
        if root is not None and root.HasInfo(key):
            return True
    return False


def world_bounds(prim) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    from pxr import Usd, UsdGeom

    imageable = UsdGeom.Imageable(prim)
    if not imageable:
        return None
    bound = imageable.ComputeWorldBound(Usd.TimeCode.Default(), UsdGeom.Tokens.default_)
    aligned = bound.ComputeAlignedRange()
    if aligned.IsEmpty():
        return None
    return _vec3(aligned.GetMin()), _vec3(aligned.GetMax())


def world_translation(prim) -> tuple[float, float, float] | None:
    from pxr import Usd, UsdGeom

    xformable = UsdGeom.Xformable(prim)
    if not xformable:
        return None
    matrix = xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    return _vec3(matrix.ExtractTranslation())


def topology(prim) -> tuple[int | None, int | None]:
    from pxr import UsdGeom

    mesh = UsdGeom.Mesh(prim)
    if not mesh:
        return None, None
    points = mesh.GetPointsAttr().Get()
    faces = mesh.GetFaceVertexCountsAttr().Get()
    return (len(points) if points is not None else None, len(faces) if faces is not None else None)


def material_path(prim) -> str:
    from pxr import UsdShade

    binding = UsdShade.MaterialBindingAPI(prim)
    if not binding:
        return ""
    try:
        material, _relationship = binding.ComputeBoundMaterial()
    except Exception:
        return ""
    if not material:
        return ""
    path = material.GetPath()
    return "" if not path or str(path) == "/" else str(path)


def usd_kind(prim) -> str:
    from pxr import Usd

    kind = Usd.ModelAPI(prim).GetKind()
    return str(kind) if kind else ""


def is_instance(prim) -> bool:
    return bool(prim.IsInstance())
