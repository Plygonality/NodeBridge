"""Central coordinate conversion.

Blender is Z-up and right-handed (X right, Y forward, Z up).
Houdini is Y-up and right-handed (X right, Y up, Z forward out of the screen
in the default view, which is Blender's -Y after the axis swap below).
Unreal is Z-up and left-handed (X forward, Y right, Z up).

Position conversion Blender → Houdini::

    (x, y, z) → (x, z, -y)

Position conversion Blender → Unreal::

    (x, y, z) → (y, x, z)

The Unreal mapping is a single-axis reflection, which is what changes
handedness. UV V is not flipped unless the caller asks: Geometry Nodes and
Houdini commonly share a V-up convention, while Unreal material UVs are
often V-down.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


Vector3 = tuple[float, float, float]
Vector2 = tuple[float, float]


@dataclass(frozen=True)
class CoordinateSystem:
    """Named axis convention. Conversion tables live in this module."""

    name: str
    up_axis: str
    handedness: str
    euler_order: str = "XYZ"

    def __post_init__(self) -> None:
        if self.up_axis not in {"Y", "Z"}:
            raise ValueError("up_axis must be Y or Z")
        if self.handedness not in {"right", "left"}:
            raise ValueError("handedness must be right or left")


BLENDER_COORDINATES = CoordinateSystem("blender", up_axis="Z", handedness="right")
HOUDINI_COORDINATES = CoordinateSystem("houdini", up_axis="Y", handedness="right")
UNREAL_COORDINATES = CoordinateSystem("unreal", up_axis="Z", handedness="left")

_BY_NAME = {
    "blender": BLENDER_COORDINATES,
    "houdini": HOUDINI_COORDINATES,
    "unreal": UNREAL_COORDINATES,
}


def coordinate_system(name: str) -> CoordinateSystem:
    key = name.strip().lower()
    if key not in _BY_NAME:
        raise KeyError(f"Unknown coordinate system {name!r}")
    return _BY_NAME[key]


def _as_vec3(value: Sequence[float]) -> Vector3:
    if len(value) < 3:
        raise ValueError("A 3D vector requires three components")
    return (float(value[0]), float(value[1]), float(value[2]))


def _permute(vector: Vector3, order: tuple[int, int, int], signs: tuple[float, float, float]) -> Vector3:
    return (
        signs[0] * vector[order[0]],
        signs[1] * vector[order[1]],
        signs[2] * vector[order[2]],
    )


# (source, target) → (component indices into the source vector, signs)
_POSITION = {
    ("blender", "houdini"): ((0, 2, 1), (1.0, 1.0, -1.0)),
    ("houdini", "blender"): ((0, 2, 1), (1.0, -1.0, 1.0)),
    ("blender", "unreal"): ((1, 0, 2), (1.0, 1.0, 1.0)),
    ("unreal", "blender"): ((1, 0, 2), (1.0, 1.0, 1.0)),
    ("houdini", "unreal"): ((2, 0, 1), (-1.0, 1.0, 1.0)),
    ("unreal", "houdini"): ((1, 2, 0), (1.0, 1.0, -1.0)),
}


def convert_position(
    vector: Sequence[float],
    source: CoordinateSystem | str,
    target: CoordinateSystem | str,
) -> Vector3:
    """Convert a position or translation between coordinate systems."""
    return _convert(vector, source, target)


def convert_scale(
    vector: Sequence[float],
    source: CoordinateSystem | str,
    target: CoordinateSystem | str,
) -> Vector3:
    """Permute scale axes. Signs stay positive; scale does not reflect."""
    src = _name(source)
    dst = _name(target)
    values = _as_vec3(vector)
    if src == dst:
        return values
    order, _signs = _POSITION[(src, dst)]
    return (abs(values[order[0]]), abs(values[order[1]]), abs(values[order[2]]))


def convert_normal(
    vector: Sequence[float],
    source: CoordinateSystem | str,
    target: CoordinateSystem | str,
) -> Vector3:
    """Convert a direction or normal. Same mapping as positions."""
    return _convert(vector, source, target)


def convert_euler(
    degrees_or_radians: Sequence[float],
    source: CoordinateSystem | str,
    target: CoordinateSystem | str,
    *,
    degrees: bool = False,
) -> Vector3:
    """Convert an XYZ Euler triplet by rotating the equivalent axes.

    The components are treated as Euler XYZ in *source* space. This is a
    basis change of the rotation vector, not a re-decomposition into a
    different Euler order. Callers that need degrees vs radians should
    convert units separately, or pass ``degrees=True`` when both sides
    already share an angle unit.
    """
    del degrees
    return _convert(degrees_or_radians, source, target)


def convert_uv(uv: Sequence[float], *, flip_v: bool = False) -> Vector2:
    """Return UV coordinates, optionally flipping V for Unreal materials."""
    if len(uv) < 2:
        raise ValueError("UV requires two components")
    u = float(uv[0])
    v = float(uv[1])
    if flip_v:
        v = 1.0 - v
    return (u, v)


def _convert(
    vector: Sequence[float],
    source: CoordinateSystem | str,
    target: CoordinateSystem | str,
) -> Vector3:
    src = _name(source)
    dst = _name(target)
    values = _as_vec3(vector)
    if src == dst:
        return values
    order, signs = _POSITION[(src, dst)]
    return _permute(values, order, signs)


def _name(system: CoordinateSystem | str) -> str:
    if isinstance(system, CoordinateSystem):
        return system.name
    return coordinate_system(system).name


def quaternion_to_euler_xyz(quaternion: Sequence[float], *, degrees: bool = False) -> Vector3:
    """Convert a quaternion ``(x, y, z, w)`` to an XYZ Euler triplet.

    Provided so backends do not each reimplement the conversion. This is
    the standard Hamilton right-handed decomposition.
    """
    if len(quaternion) < 4:
        raise ValueError("Quaternion requires x, y, z, w")
    x, y, z, w = (float(quaternion[0]), float(quaternion[1]), float(quaternion[2]), float(quaternion[3]))
    sin_r = 2.0 * (w * x + y * z)
    cos_r = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sin_r, cos_r)
    sin_p = 2.0 * (w * y - z * x)
    sin_p = max(-1.0, min(1.0, sin_p))
    pitch = math.asin(sin_p)
    sin_y = 2.0 * (w * z + x * y)
    cos_y = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(sin_y, cos_y)
    result = (roll, pitch, yaw)
    if degrees:
        return tuple(math.degrees(component) for component in result)  # type: ignore[return-value]
    return result
