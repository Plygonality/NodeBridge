import math

import pytest

from nodebridge.common.coordinates import (
    convert_euler,
    convert_location,
    convert_normal,
    convert_point,
    convert_quaternion,
    convert_scale,
    convert_uv,
    matrix_to_quaternion,
    quaternion_to_matrix,
    rotation_matrix_xyz,
)


def test_blender_point_roundtrip_is_identity():
    point = (1.25, -2.0, 4.5)
    assert convert_point(point, "blender", "blender") == pytest.approx(point)


def test_blender_to_houdini_swaps_up_and_forward():
    assert convert_point((1.0, 2.0, 3.0), "blender", "houdini") == pytest.approx((1.0, 3.0, -2.0))
    assert convert_point((1.0, 3.0, -2.0), "houdini", "blender") == pytest.approx((1.0, 2.0, 3.0))


def test_blender_to_unreal_changes_axes_and_scales_to_centimeters():
    assert convert_location((1.0, 2.0, 3.0), "blender", "unreal") == pytest.approx((200.0, 100.0, 300.0))
    assert convert_location((200.0, 100.0, 300.0), "unreal", "blender") == pytest.approx((1.0, 2.0, 3.0))


def test_normal_roundtrip_stays_unit_length():
    converted = convert_normal((0.0, 1.0, 0.0), "blender", "houdini")
    length = math.sqrt(sum(component * component for component in converted))
    assert length == pytest.approx(1.0)
    assert convert_normal(converted, "houdini", "blender") == pytest.approx((0.0, 1.0, 0.0))


def test_scale_permutes_with_axes_and_ignores_sign():
    assert convert_scale((1.0, 2.0, 3.0), "blender", "houdini") == pytest.approx((1.0, 3.0, 2.0))


def test_unreal_uv_flips_v():
    assert convert_uv((0.2, 0.25), "blender", "unreal") == pytest.approx((0.2, 0.75))
    assert convert_uv((0.2, 0.25), "blender", "houdini") == pytest.approx((0.2, 0.25))


def test_euler_roundtrip():
    euler = (0.3, -0.4, 1.2)
    houdini = convert_euler(euler, "blender", "houdini")
    back = convert_euler(houdini, "houdini", "blender")
    assert back == pytest.approx(euler, abs=1e-6)


def test_quaternion_matches_matrix_conversion():
    matrix = rotation_matrix_xyz((0.2, 0.5, -0.7))
    quaternion = matrix_to_quaternion(matrix)
    rebuilt = quaternion_to_matrix(quaternion)
    for row in range(3):
        assert rebuilt[row] == pytest.approx(matrix[row], abs=1e-6)
    converted = convert_quaternion(quaternion, "blender", "unreal")
    restored = convert_quaternion(converted, "unreal", "blender")
    assert tuple(abs(component) for component in restored) == pytest.approx(
        tuple(abs(component) for component in quaternion),
        abs=1e-5,
    )
