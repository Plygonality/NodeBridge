"""Central coordinate conversion.

Canonical space is right-handed, X right, Y forward, Z up, in the source
length unit. Blender world space already uses that axis convention.

Houdini is right-handed and Y-up. A Blender point ``(x, y, z)`` becomes
Houdini ``(x, z, -y)``.

Unreal is left-handed, Z-up, and X-forward. A Blender point ``(x, y, z)``
becomes Unreal ``(y, x, z)`` before unit scaling. Unit scaling is applied
only by :func:`convert_location`.

UV conversion flips V when one frame stores V upward and the other stores
V downward. Houdini is treated as V-up, matching Blender. Unreal is V-down.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from nodebridge.common.units import length_scale


class Axis(str, Enum):
    X = "x"
    Y = "y"
    Z = "z"


class Handedness(str, Enum):
    RIGHT = "right"
    LEFT = "left"


Matrix3 = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]
Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class CoordinateFrame:
    """How one DCC orients axes relative to canonical space."""

    name: str
    handedness: Handedness
    up: Axis
    forward: Axis
    to_canonical: Matrix3
    uv_v_up: bool = True


def _mat_vec(matrix: Matrix3, vector: Vec3) -> Vec3:
    return (
        matrix[0][0] * vector[0] + matrix[0][1] * vector[1] + matrix[0][2] * vector[2],
        matrix[1][0] * vector[0] + matrix[1][1] * vector[1] + matrix[1][2] * vector[2],
        matrix[2][0] * vector[0] + matrix[2][1] * vector[1] + matrix[2][2] * vector[2],
    )


def _mul(left: Matrix3, right: Matrix3) -> Matrix3:
    return tuple(
        tuple(sum(left[row][k] * right[k][col] for k in range(3)) for col in range(3))
        for row in range(3)
    )  # type: ignore[return-value]


def _invert(matrix: Matrix3) -> Matrix3:
    a, b, c = matrix[0]
    d, e, f = matrix[1]
    g, h, i = matrix[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-12:
        raise ValueError("coordinate matrix is singular")
    inv = 1.0 / det
    return (
        ((e * i - f * h) * inv, (c * h - b * i) * inv, (b * f - c * e) * inv),
        ((f * g - d * i) * inv, (a * i - c * g) * inv, (c * d - a * f) * inv),
        ((d * h - e * g) * inv, (b * g - a * h) * inv, (a * e - b * d) * inv),
    )


def _identity() -> Matrix3:
    return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


BLENDER = CoordinateFrame(
    name="blender",
    handedness=Handedness.RIGHT,
    up=Axis.Z,
    forward=Axis.Y,
    to_canonical=_identity(),
    uv_v_up=True,
)

# Maps Houdini (X right, Y up, Z back relative to Blender forward) into canonical.
HOUDINI = CoordinateFrame(
    name="houdini",
    handedness=Handedness.RIGHT,
    up=Axis.Y,
    forward=Axis.Z,
    to_canonical=(
        (1.0, 0.0, 0.0),
        (0.0, 0.0, -1.0),
        (0.0, 1.0, 0.0),
    ),
    uv_v_up=True,
)

# Maps Unreal (X forward, Y right, Z up) into canonical, before centimeter scaling.
UNREAL = CoordinateFrame(
    name="unreal",
    handedness=Handedness.LEFT,
    up=Axis.Z,
    forward=Axis.X,
    to_canonical=(
        (0.0, 1.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
    ),
    uv_v_up=False,
)

FRAMES: dict[str, CoordinateFrame] = {
    BLENDER.name: BLENDER,
    HOUDINI.name: HOUDINI,
    UNREAL.name: UNREAL,
}


def get_frame(name: str | CoordinateFrame) -> CoordinateFrame:
    if isinstance(name, CoordinateFrame):
        return name
    try:
        return FRAMES[name]
    except KeyError as exc:
        raise KeyError(f"Unknown coordinate frame: {name}") from exc


def _change_basis(source: CoordinateFrame, target: CoordinateFrame) -> Matrix3:
    """Matrix that maps source-space vectors into target space."""

    return _mul(_invert(target.to_canonical), source.to_canonical)


def convert_vector(vector: Vec3, source: str | CoordinateFrame, target: str | CoordinateFrame) -> Vec3:
    """Convert a free vector (position, direction) between axis conventions."""

    src = get_frame(source)
    dst = get_frame(target)
    return _mat_vec(_change_basis(src, dst), (float(vector[0]), float(vector[1]), float(vector[2])))


def convert_point(point: Vec3, source: str | CoordinateFrame, target: str | CoordinateFrame) -> Vec3:
    """Convert a point between axis conventions without changing units."""

    return convert_vector(point, source, target)


def convert_location(point: Vec3, source: str, target: str) -> Vec3:
    """Convert a point between DCCs, including axis remap and unit scale."""

    remapped = convert_point(point, source, target)
    scale = length_scale(source, target)
    return (remapped[0] * scale, remapped[1] * scale, remapped[2] * scale)


def convert_normal(normal: Vec3, source: str | CoordinateFrame, target: str | CoordinateFrame) -> Vec3:
    """Convert a direction and renormalize it."""

    converted = convert_vector(normal, source, target)
    length = math.sqrt(sum(component * component for component in converted))
    if length < 1e-12:
        return converted
    return (converted[0] / length, converted[1] / length, converted[2] / length)


def convert_scale(scale: Vec3, source: str | CoordinateFrame, target: str | CoordinateFrame) -> Vec3:
    """Permute scale by the absolute axis remap. Scale is unitless."""

    src = get_frame(source)
    dst = get_frame(target)
    basis_change = _change_basis(src, dst)
    output = [1.0, 1.0, 1.0]
    for axis, component in enumerate(scale):
        basis = [0.0, 0.0, 0.0]
        basis[axis] = 1.0
        landed = _mat_vec(basis_change, (basis[0], basis[1], basis[2]))
        index = max(range(3), key=lambda item: abs(landed[item]))
        output[index] = float(component)
    return (output[0], output[1], output[2])


def convert_uv(uv: tuple[float, float], source: str | CoordinateFrame, target: str | CoordinateFrame) -> tuple[float, float]:
    """Flip V when the frames disagree about which way texture V points."""

    src = get_frame(source)
    dst = get_frame(target)
    u = float(uv[0])
    v = float(uv[1])
    if src.uv_v_up != dst.uv_v_up:
        v = 1.0 - v
    return (u, v)


def rotation_matrix_xyz(euler_radians: Vec3) -> Matrix3:
    """Blender-style intrinsic XYZ Euler angles to a 3x3 matrix."""

    rx, ry, rz = euler_radians
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    rot_x: Matrix3 = ((1.0, 0.0, 0.0), (0.0, cx, -sx), (0.0, sx, cx))
    rot_y: Matrix3 = ((cy, 0.0, sy), (0.0, 1.0, 0.0), (-sy, 0.0, cy))
    rot_z: Matrix3 = ((cz, -sz, 0.0), (sz, cz, 0.0), (0.0, 0.0, 1.0))
    return _mul(rot_z, _mul(rot_y, rot_x))


def euler_xyz_from_matrix(matrix: Matrix3) -> Vec3:
    """Extract intrinsic XYZ Euler angles, in radians, from a rotation matrix."""

    sy = max(-1.0, min(1.0, -matrix[2][0]))
    ry = math.asin(sy)
    if abs(matrix[2][0]) < 0.999999:
        rx = math.atan2(matrix[2][1], matrix[2][2])
        rz = math.atan2(matrix[1][0], matrix[0][0])
    else:
        rx = math.atan2(-matrix[1][2], matrix[1][1])
        rz = 0.0
    return (rx, ry, rz)


def convert_euler(
    euler: Vec3,
    source: str | CoordinateFrame,
    target: str | CoordinateFrame,
    *,
    degrees: bool = False,
) -> Vec3:
    """Convert an XYZ Euler rotation into the target frame."""

    radians = tuple(math.radians(component) for component in euler) if degrees else euler
    matrix = rotation_matrix_xyz((float(radians[0]), float(radians[1]), float(radians[2])))
    change = _change_basis(get_frame(source), get_frame(target))
    converted = _mul(change, _mul(matrix, _invert(change)))
    result = euler_xyz_from_matrix(converted)
    if degrees:
        return tuple(math.degrees(component) for component in result)  # type: ignore[return-value]
    return result


def matrix_to_quaternion(matrix: Matrix3) -> tuple[float, float, float, float]:
    """Return a quaternion as ``(x, y, z, w)``."""

    trace = matrix[0][0] + matrix[1][1] + matrix[2][2]
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * scale
        x = (matrix[2][1] - matrix[1][2]) / scale
        y = (matrix[0][2] - matrix[2][0]) / scale
        z = (matrix[1][0] - matrix[0][1]) / scale
    elif matrix[0][0] > matrix[1][1] and matrix[0][0] > matrix[2][2]:
        scale = math.sqrt(1.0 + matrix[0][0] - matrix[1][1] - matrix[2][2]) * 2.0
        w = (matrix[2][1] - matrix[1][2]) / scale
        x = 0.25 * scale
        y = (matrix[0][1] + matrix[1][0]) / scale
        z = (matrix[0][2] + matrix[2][0]) / scale
    elif matrix[1][1] > matrix[2][2]:
        scale = math.sqrt(1.0 + matrix[1][1] - matrix[0][0] - matrix[2][2]) * 2.0
        w = (matrix[0][2] - matrix[2][0]) / scale
        x = (matrix[0][1] + matrix[1][0]) / scale
        y = 0.25 * scale
        z = (matrix[1][2] + matrix[2][1]) / scale
    else:
        scale = math.sqrt(1.0 + matrix[2][2] - matrix[0][0] - matrix[1][1]) * 2.0
        w = (matrix[1][0] - matrix[0][1]) / scale
        x = (matrix[0][2] + matrix[2][0]) / scale
        y = (matrix[1][2] + matrix[2][1]) / scale
        z = 0.25 * scale
    return (x, y, z, w)


def quaternion_to_matrix(quaternion: tuple[float, float, float, float]) -> Matrix3:
    x, y, z, w = quaternion
    norm = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    return (
        (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)),
        (2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)),
        (2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)),
    )


def convert_quaternion(
    quaternion: tuple[float, float, float, float],
    source: str | CoordinateFrame,
    target: str | CoordinateFrame,
) -> tuple[float, float, float, float]:
    """Convert a quaternion by changing the basis of its rotation matrix."""

    matrix = quaternion_to_matrix(quaternion)
    change = _change_basis(get_frame(source), get_frame(target))
    converted = _mul(change, _mul(matrix, _invert(change)))
    return matrix_to_quaternion(converted)
