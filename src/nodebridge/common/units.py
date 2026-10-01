"""Centralized unit conversion.

Every unit-bearing value in the Semantic IR carries a :class:`ValueRole`.
Backends never multiply by 100 or convert radians themselves; they ask
this module. The canonical NodeBridge unit system is Blender's: meters
(times the scene's ``unit_settings.scale_length``), radians, seconds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ValueRole(str, Enum):
    """Semantic meaning of a value, used to pick conversions."""

    SCALAR = "scalar"
    FACTOR = "factor"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    LENGTH = "length"
    AREA_DENSITY = "area_density"  # elements per square unit
    ANGLE = "angle"
    POSITION = "position"
    DIRECTION = "direction"
    NORMAL = "normal"
    SCALE = "scale"
    EULER = "euler"
    COLOR = "color"
    UV = "uv"
    TIME = "time"
    FRAME = "frame"
    STRING = "string"
    REFERENCE = "reference"


class AngleUnit(str, Enum):
    RADIANS = "radians"
    DEGREES = "degrees"


@dataclass(frozen=True)
class UnitSystem:
    """Units a DCC uses for parameters it exposes."""

    name: str
    meters_per_unit: float
    angle_unit: AngleUnit
    frames_per_second: float = 24.0

    def length_from_meters(self, meters: float) -> float:
        return meters / self.meters_per_unit


BLENDER_UNITS = UnitSystem("blender", 1.0, AngleUnit.RADIANS)
HOUDINI_UNITS = UnitSystem("houdini", 1.0, AngleUnit.DEGREES)
"""Houdini parameters use degrees; VEX trigonometry uses radians (see VEX_UNITS)."""
HOUDINI_VEX_UNITS = UnitSystem("houdini_vex", 1.0, AngleUnit.RADIANS)
UNREAL_UNITS = UnitSystem("unreal", 0.01, AngleUnit.DEGREES)


def convert_length(value: float, source: UnitSystem, target: UnitSystem, *, scene_scale: float = 1.0) -> float:
    meters = value * source.meters_per_unit * scene_scale
    return target.length_from_meters(meters)


def convert_area_density(value: float, source: UnitSystem, target: UnitSystem, *, scene_scale: float = 1.0) -> float:
    """Elements per square unit. Density scales with the inverse square of length."""
    factor = convert_length(1.0, source, target, scene_scale=scene_scale)
    return value / (factor * factor)


def convert_angle(value: float, source: AngleUnit, target: AngleUnit) -> float:
    if source == target:
        return value
    if source == AngleUnit.RADIANS:
        return math.degrees(value)
    return math.radians(value)


def frame_to_seconds(frame: float, fps: float, *, frame_start: float = 1.0) -> float:
    return (frame - frame_start) / fps


def seconds_to_frame(seconds: float, fps: float, *, frame_start: float = 1.0) -> float:
    return seconds * fps + frame_start


def convert_frame(frame: float, source_fps: float, target_fps: float, *, source_start: float = 1.0, target_start: float = 1.0) -> float:
    return seconds_to_frame(frame_to_seconds(frame, source_fps, frame_start=source_start), target_fps, frame_start=target_start)


def convert_scalar(value: Any, role: ValueRole, source: UnitSystem, target: UnitSystem, *, scene_scale: float = 1.0) -> Any:
    """Convert a scalar or a sequence of scalars according to its role.

    Vector roles (position, direction, euler, scale) only convert units
    here. Axis changes belong to :mod:`nodebridge.common.coordinates`.
    """
    if isinstance(value, (list, tuple)):
        return type(value)(convert_scalar(item, role, source, target, scene_scale=scene_scale) for item in value)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return value
    if role in (ValueRole.LENGTH, ValueRole.POSITION):
        return convert_length(float(value), source, target, scene_scale=scene_scale)
    if role == ValueRole.AREA_DENSITY:
        return convert_area_density(float(value), source, target, scene_scale=scene_scale)
    if role in (ValueRole.ANGLE, ValueRole.EULER):
        return convert_angle(float(value), source.angle_unit, target.angle_unit)
    return value
