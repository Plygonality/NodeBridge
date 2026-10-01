"""Explicit unit conversion between Blender, Houdini, and Unreal.

Lengths are converted through meters. Angles are converted through radians.
Frame numbers are not silently turned into seconds; callers pass a frame
rate when they want that conversion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class UnitSystem:
    """One application's unit convention.

    ``meters_per_unit`` is the length of one numeric unit in meters.
    ``angles`` is the unit used by that application's transform parameters.
    """

    name: str
    meters_per_unit: float
    angles: str  # "radians" or "degrees"

    def __post_init__(self) -> None:
        if self.meters_per_unit <= 0:
            raise ValueError(f"{self.name} meters_per_unit must be positive")
        if self.angles not in {"radians", "degrees"}:
            raise ValueError(f"{self.name} angles must be radians or degrees")


BLENDER_UNITS = UnitSystem("blender", meters_per_unit=1.0, angles="radians")
HOUDINI_UNITS = UnitSystem("houdini", meters_per_unit=1.0, angles="degrees")
UNREAL_UNITS = UnitSystem("unreal", meters_per_unit=0.01, angles="degrees")

_BY_NAME = {
    "blender": BLENDER_UNITS,
    "houdini": HOUDINI_UNITS,
    "unreal": UNREAL_UNITS,
}


def unit_system(name: str) -> UnitSystem:
    """Return a known unit system by application id."""
    key = name.strip().lower()
    if key not in _BY_NAME:
        raise KeyError(f"Unknown unit system {name!r}")
    return _BY_NAME[key]


def convert_length(value: float, source: UnitSystem | str, target: UnitSystem | str) -> float:
    """Convert a distance from *source* units into *target* units."""
    src = source if isinstance(source, UnitSystem) else unit_system(source)
    dst = target if isinstance(target, UnitSystem) else unit_system(target)
    meters = float(value) * src.meters_per_unit
    return meters / dst.meters_per_unit


def convert_angle(value: float, source: UnitSystem | str, target: UnitSystem | str) -> float:
    """Convert an angle from *source* convention into *target* convention."""
    src = source if isinstance(source, UnitSystem) else unit_system(source)
    dst = target if isinstance(target, UnitSystem) else unit_system(target)
    radians = math.radians(float(value)) if src.angles == "degrees" else float(value)
    if dst.angles == "degrees":
        return math.degrees(radians)
    return radians


def frames_to_seconds(frames: float, *, frames_per_second: float = 24.0) -> float:
    """Convert a frame index to seconds at *frames_per_second*."""
    if frames_per_second <= 0:
        raise ValueError("frames_per_second must be positive")
    return float(frames) / float(frames_per_second)


def seconds_to_frames(seconds: float, *, frames_per_second: float = 24.0) -> float:
    """Convert seconds to a frame index at *frames_per_second*."""
    if frames_per_second <= 0:
        raise ValueError("frames_per_second must be positive")
    return float(seconds) * float(frames_per_second)
