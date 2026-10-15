"""Centralized coordinate-system conversion.

The canonical NodeBridge frame is Blender's: right-handed, Z-up, -Y forward,
column vectors, Euler angles in radians. Each target declares a basis
matrix ``B`` such that ``v_target = B @ v_blender``. Every conversion of a
point, direction, normal, scale, rotation, UV or normal map goes through
this module so translators never hand-roll axis swaps.

Houdini: right-handed, Y-up.   (x, y, z) -> (x, z, -y)
Unreal:  left-handed,  Z-up.   (x, y, z) -> (x, -y, z), centimeters

Unit scaling is not applied here; see :mod:`nodebridge.common.units`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

Vec3 = tuple[float, float, float]
Mat3 = tuple[Vec3, Vec3, Vec3]

AXES = "XYZ"


@dataclass(frozen=True)
class CoordinateSystem:
    name: str
    basis: Mat3
    up_axis: str
    handedness: str
    uv_origin: str = "bottom_left"
    normal_map: str = "opengl"
    default_euler_order: str = "XYZ"

    @property
    def determinant(self) -> float:
        return det3(self.basis)


BLENDER = CoordinateSystem("blender", ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)), "Z", "right")
HOUDINI = CoordinateSystem("houdini", ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)), "Y", "right")
UNREAL = CoordinateSystem(
    "unreal",
    ((1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    "Z",
    "left",
    uv_origin="top_left",
    normal_map="directx",
)

SYSTEMS = {system.name: system for system in (BLENDER, HOUDINI, UNREAL)}


def matmul(a: Mat3, b: Mat3) -> Mat3:
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))  # type: ignore[return-value]


def transpose(m: Mat3) -> Mat3:
    return tuple(tuple(m[j][i] for j in range(3)) for i in range(3))  # type: ignore[return-value]


def apply(m: Mat3, v: Sequence[float]) -> Vec3:
    return tuple(m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] for i in range(3))  # type: ignore[return-value]


def det3(m: Mat3) -> float:
    return (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )


def change_of_basis(source: CoordinateSystem, target: CoordinateSystem) -> Mat3:
    """Matrix mapping vectors expressed in ``source`` to ``target``."""
    return matmul(target.basis, transpose(source.basis))


def convert_point(v: Sequence[float], source: CoordinateSystem = BLENDER, target: CoordinateSystem = HOUDINI) -> Vec3:
    return _clean(apply(change_of_basis(source, target), v))


def convert_direction(v: Sequence[float], source: CoordinateSystem = BLENDER, target: CoordinateSystem = HOUDINI) -> Vec3:
    return convert_point(v, source, target)


def convert_normal(v: Sequence[float], source: CoordinateSystem = BLENDER, target: CoordinateSystem = HOUDINI) -> Vec3:
    """Bases are orthogonal, so the inverse-transpose equals the basis itself.

    A handedness change (Blender -> Unreal) also reverses face winding; mesh
    data is never converted by NodeBridge, so only vectors are handled here.
    """
    return convert_point(v, source, target)


def convert_scale(v: Sequence[float], source: CoordinateSystem = BLENDER, target: CoordinateSystem = HOUDINI) -> Vec3:
    """Scale factors follow the axis permutation but never change sign."""
    m = change_of_basis(source, target)
    return _clean(tuple(sum(abs(m[i][k]) * v[k] for k in range(3)) for i in range(3)))  # type: ignore[arg-type]


def axis_rotation(axis: str, angle: float) -> Mat3:
    c, s = math.cos(angle), math.sin(angle)
    if axis == "X":
        return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))
    if axis == "Y":
        return ((c, 0.0, s), (0.0, 1.0, 0.0), (-s, 0.0, c))
    return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))


def euler_to_matrix(euler: Sequence[float], order: str = "XYZ") -> Mat3:
    """Euler angles (radians, indexed by axis X/Y/Z) applied in ``order``.

    ``order="XYZ"`` rotates about X first, then Y, then Z (Blender's and
    Houdini's ``xyz`` convention): ``R = Rz @ Ry @ Rx``.
    """
    result: Mat3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    for axis in order:
        result = matmul(axis_rotation(axis, euler[AXES.index(axis)]), result)
    return result


def _decompose_xyz(m: Mat3) -> Vec3:
    cy = math.hypot(m[0][0], m[1][0])
    if cy > 1e-9:
        return (math.atan2(m[2][1], m[2][2]), math.atan2(-m[2][0], cy), math.atan2(m[1][0], m[0][0]))
    return (math.atan2(-m[1][2], m[1][1]), math.atan2(-m[2][0], cy), 0.0)


def matrix_to_euler(m: Mat3, order: str = "XYZ") -> Vec3:
    """Inverse of :func:`euler_to_matrix` for any of the six axis orders."""
    indices = [AXES.index(axis) for axis in order]
    perm: Mat3 = tuple(tuple(1.0 if indices[row] == col else 0.0 for col in range(3)) for row in range(3))  # type: ignore[assignment]
    sign = det3(perm)
    xyz = _decompose_xyz(matmul(matmul(perm, m), transpose(perm)))
    result = [0.0, 0.0, 0.0]
    for position, axis_index in enumerate(indices):
        result[axis_index] = sign * xyz[position]
    return _clean(tuple(result))  # type: ignore[arg-type]


def convert_rotation_matrix(m: Mat3, source: CoordinateSystem = BLENDER, target: CoordinateSystem = HOUDINI) -> Mat3:
    c = change_of_basis(source, target)
    return matmul(matmul(c, m), transpose(c))


def convert_euler(
    euler: Sequence[float],
    source: CoordinateSystem = BLENDER,
    target: CoordinateSystem = HOUDINI,
    *,
    source_order: str = "XYZ",
    target_order: str | None = None,
) -> tuple[Vec3, str]:
    """Convert an Euler rotation. Returns (angles in radians, target order)."""
    order = target_order or target.default_euler_order
    m = convert_rotation_matrix(euler_to_matrix(euler, source_order), source, target)
    return matrix_to_euler(m, order), order


def matrix_to_quaternion(m: Mat3) -> tuple[float, float, float, float]:
    """Returns (w, x, y, z)."""
    trace = m[0][0] + m[1][1] + m[2][2]
    if trace > 0:
        s = 0.5 / math.sqrt(trace + 1.0)
        q = (0.25 / s, (m[2][1] - m[1][2]) * s, (m[0][2] - m[2][0]) * s, (m[1][0] - m[0][1]) * s)
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = 2.0 * math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2])
        q = ((m[2][1] - m[1][2]) / s, 0.25 * s, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s)
    elif m[1][1] > m[2][2]:
        s = 2.0 * math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2])
        q = ((m[0][2] - m[2][0]) / s, (m[0][1] + m[1][0]) / s, 0.25 * s, (m[1][2] + m[2][1]) / s)
    else:
        s = 2.0 * math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1])
        q = ((m[1][0] - m[0][1]) / s, (m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, 0.25 * s)
    if q[0] < 0:
        q = (-q[0], -q[1], -q[2], -q[3])
    return _clean(q)  # type: ignore[return-value]


def quaternion_to_matrix(q: Sequence[float]) -> Mat3:
    w, x, y, z = q
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )


def unreal_rotator_to_matrix(pitch: float, yaw: float, roll: float) -> Mat3:
    """Unreal ``FRotationMatrix`` (degrees), returned in column-vector form."""
    sp, cp = math.sin(math.radians(pitch)), math.cos(math.radians(pitch))
    sy, cy = math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
    sr, cr = math.sin(math.radians(roll)), math.cos(math.radians(roll))
    rows = (
        (cp * cy, cp * sy, sp),
        (sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp),
        (-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp),
    )
    return transpose(rows)  # Unreal rows are the images of the basis axes.


def matrix_to_unreal_rotator(m: Mat3) -> tuple[float, float, float]:
    """Mirror of Unreal's ``FMatrix::Rotator()``. Returns (pitch, yaw, roll) in degrees."""
    x_axis = (m[0][0], m[1][0], m[2][0])
    y_axis = (m[0][1], m[1][1], m[2][1])
    z_axis = (m[0][2], m[1][2], m[2][2])
    pitch = math.degrees(math.atan2(x_axis[2], math.hypot(x_axis[0], x_axis[1])))
    yaw = math.degrees(math.atan2(x_axis[1], x_axis[0]))
    reference = unreal_rotator_to_matrix(pitch, yaw, 0.0)
    sy_axis = (reference[0][1], reference[1][1], reference[2][1])
    roll = math.degrees(math.atan2(_dot(z_axis, sy_axis), _dot(y_axis, sy_axis)))
    return _clean((pitch, yaw, roll))  # type: ignore[return-value]


def blender_euler_to_unreal_rotator(euler: Sequence[float]) -> tuple[float, float, float]:
    """Blender XYZ Euler (radians) -> Unreal (pitch, yaw, roll) degrees."""
    return matrix_to_unreal_rotator(convert_rotation_matrix(euler_to_matrix(euler, "XYZ"), BLENDER, UNREAL))


def unreal_axis_signs() -> dict[str, tuple[str, float]]:
    """How a pure Blender axis rotation maps onto Unreal rotator components.

    Used to translate independent per-axis random rotation ranges.
    Returns ``{"X": ("roll", sign), "Y": ("pitch", sign), "Z": ("yaw", sign)}``.
    """
    result: dict[str, tuple[str, float]] = {}
    names = ("pitch", "yaw", "roll")
    for axis in AXES:
        euler = [0.0, 0.0, 0.0]
        euler[AXES.index(axis)] = math.radians(10.0)
        rotator = blender_euler_to_unreal_rotator(euler)
        index = max(range(3), key=lambda i: abs(rotator[i]))
        result[axis] = (names[index], 1.0 if rotator[index] > 0 else -1.0)
    return result


def convert_uv(uv: Sequence[float], source: CoordinateSystem = BLENDER, target: CoordinateSystem = UNREAL) -> tuple[float, float]:
    u, v = float(uv[0]), float(uv[1])
    if source.uv_origin != target.uv_origin:
        v = 1.0 - v
    return (u, v)


def uv_flip_required(source: CoordinateSystem, target: CoordinateSystem) -> bool:
    return source.uv_origin != target.uv_origin


def normal_map_green_flip_required(source: CoordinateSystem, target: CoordinateSystem) -> bool:
    return source.normal_map != target.normal_map


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _clean(values: Sequence[float]) -> tuple[float, ...]:
    return tuple(0.0 if abs(value) < 1e-12 else value for value in values)
