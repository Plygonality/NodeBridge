"""Deterministic hash random shared by generated Python and VEX.

``random_unit(seed, element_id)`` is NodeBridge's own sequence. It is not
Blender's random, Houdini's random, or Unreal's random. Backends must say
so whenever a host-native sampler is used instead of this function.

The VEX snippet is a line-by-line port of the Python mixer. It is emitted
into wrangles when deterministic randomness is requested. NodeBridge does
not execute VEX, so identity with Houdini is a property of the port, not a
measured runtime result.
"""

from __future__ import annotations

_MASK = 0xFFFFFFFF


def _mix(value: int) -> int:
    value &= _MASK
    value ^= value >> 16
    value = (value * 0x7FEB352D) & _MASK
    value ^= value >> 15
    value = (value * 0x846CA68B) & _MASK
    value ^= value >> 16
    return value


def random_unit(seed: int, element_id: int) -> float:
    """Return a float in ``[0, 1)`` from *seed* and *element_id*."""
    mixed = _mix((int(seed) * 0x9E3779B1) ^ (int(element_id) * 0x85EBCA6B))
    return (mixed & 0xFFFFFF) / 16777216.0


def random_range(seed: int, element_id: int, minimum: float, maximum: float) -> float:
    """Lerp ``random_unit`` into ``[minimum, maximum)``."""
    return float(minimum) + (float(maximum) - float(minimum)) * random_unit(seed, element_id)


def vex_hash_random() -> str:
    """VEX helpers that implement the same mixer as :func:`random_unit`."""
    return """// NodeBridge deterministic random. Not Blender's or Houdini's rand().
int nb_mix(int value) {
    value = value & 0xFFFFFFFF;
    value = value ^ (value >> 16);
    value = (value * 0x7FEB352D) & 0xFFFFFFFF;
    value = value ^ (value >> 15);
    value = (value * 0x846CA68B) & 0xFFFFFFFF;
    value = value ^ (value >> 16);
    return value;
}
float nb_random(int seed; int element_id) {
    int mixed = nb_mix((seed * 0x9E3779B1) ^ (element_id * 0x85EBCA6B));
    return float(mixed & 0xFFFFFF) / 16777216.0;
}
"""
