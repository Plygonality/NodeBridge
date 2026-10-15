"""Explicit unit conversion between Blender, Houdini, and Unreal.

Lengths are converted through meters. Angles are converted through radians.
Time is converted through seconds. Callers choose the conversion; nothing
is rescaled implicitly inside a translator.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class UnitSystem:
    """One DCC's length and the angle unit used by its transform UI."""

    name: str
    meters_per_unit: float
    angle_unit: str


BLENDER = UnitSystem("blender", 1.0, "radians")
HOUDINI = UnitSystem("houdini", 1.0, "degrees")
UNREAL = UnitSystem("unreal", 0.01, "degrees")

SYSTEMS: dict[str, UnitSystem] = {
    BLENDER.name: BLENDER,
    HOUDINI.name: HOUDINI,
    UNREAL.name: UNREAL,
}


def get_system(name: str) -> UnitSystem:
    try:
        return SYSTEMS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown unit system: {name}") from exc


def convert_length(value: float, source: str, target: str) -> float:
    """Convert a distance from ``source`` units into ``target`` units."""

    src = get_system(source)
    dst = get_system(target)
    meters = float(value) * src.meters_per_unit
    return meters / dst.meters_per_unit


def length_scale(source: str, target: str) -> float:
    """Multiply a source length by this factor to obtain the target length."""

    return convert_length(1.0, source, target)


def convert_angle(value: float, source_unit: str, target_unit: str) -> float:
    """Convert an angle between ``radians`` and ``degrees``."""

    if source_unit not in {"radians", "degrees"} or target_unit not in {"radians", "degrees"}:
        raise ValueError(f"Unsupported angle units: {source_unit} -> {target_unit}")
    if source_unit == target_unit:
        return float(value)
    if source_unit == "radians":
        return math.degrees(float(value))
    return math.radians(float(value))


def convert_angle_systems(value: float, source: str, target: str) -> float:
    """Convert an angle from one DCC's native angle unit to another's."""

    return convert_angle(value, get_system(source).angle_unit, get_system(target).angle_unit)


def convert_time(frame: float, *, fps: float, to: str = "seconds") -> float:
    """Convert a frame number to seconds, or seconds back to a frame number."""

    if fps <= 0:
        raise ValueError("fps must be positive")
    if to == "seconds":
        return float(frame) / float(fps)
    if to == "frames":
        return float(frame) * float(fps)
    raise ValueError(f"Unsupported time target: {to}")
