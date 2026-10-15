"""Shared conversion layers used by every backend.

Coordinate changes, unit changes, and randomness live here so translators
do not invent their own conventions.
"""

from nodebridge.common.coordinates import (
    convert_euler,
    convert_location,
    convert_normal,
    convert_point,
    convert_quaternion,
    convert_scale,
    convert_uv,
)
from nodebridge.common.names import sanitize_identifier, unique_name
from nodebridge.common.random import hash32, random01, random_range, random_vector
from nodebridge.common.units import convert_angle, convert_length, convert_time

__all__ = [
    "convert_angle",
    "convert_euler",
    "convert_length",
    "convert_location",
    "convert_normal",
    "convert_point",
    "convert_quaternion",
    "convert_scale",
    "convert_time",
    "convert_uv",
    "hash32",
    "random01",
    "random_range",
    "random_vector",
    "sanitize_identifier",
    "unique_name",
]
