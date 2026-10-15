import math

import pytest

from nodebridge.common.units import convert_angle, convert_length, convert_time


def test_blender_meter_is_100_unreal_centimeters():
    assert convert_length(1.0, "blender", "unreal") == pytest.approx(100.0)
    assert convert_length(100.0, "unreal", "blender") == pytest.approx(1.0)


def test_houdini_length_matches_blender_meters():
    assert convert_length(2.5, "blender", "houdini") == pytest.approx(2.5)


def test_angle_conversion():
    assert convert_angle(math.pi, "radians", "degrees") == pytest.approx(180.0)
    assert convert_angle(90.0, "degrees", "radians") == pytest.approx(math.pi / 2)


def test_frame_time_uses_fps():
    assert convert_time(48, fps=24, to="seconds") == pytest.approx(2.0)
    assert convert_time(2.0, fps=24, to="frames") == pytest.approx(48.0)


def test_unknown_system_is_rejected():
    with pytest.raises(KeyError):
        convert_length(1.0, "blender", "maya")
