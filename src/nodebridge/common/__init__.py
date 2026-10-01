"""Cross-cutting conversions shared by every backend.

Coordinate changes, unit changes, naming, and deterministic randomness
live here so translators do not invent their own conventions.
"""

from nodebridge.common.coordinates import (
    BLENDER_COORDINATES,
    HOUDINI_COORDINATES,
    UNREAL_COORDINATES,
    CoordinateSystem,
    convert_euler,
    convert_normal,
    convert_position,
    convert_scale,
    convert_uv,
)
from nodebridge.common.names import sanitize_identifier
from nodebridge.common.random import random_unit, vex_hash_random
from nodebridge.common.units import (
    BLENDER_UNITS,
    HOUDINI_UNITS,
    UNREAL_UNITS,
    UnitSystem,
    convert_angle,
    convert_length,
)

__all__ = [
    "BLENDER_COORDINATES",
    "BLENDER_UNITS",
    "HOUDINI_COORDINATES",
    "HOUDINI_UNITS",
    "UNREAL_COORDINATES",
    "UNREAL_UNITS",
    "CoordinateSystem",
    "UnitSystem",
    "convert_angle",
    "convert_euler",
    "convert_length",
    "convert_normal",
    "convert_position",
    "convert_scale",
    "convert_uv",
    "random_unit",
    "sanitize_identifier",
    "vex_hash_random",
]
