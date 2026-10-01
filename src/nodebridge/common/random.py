"""Deterministic hash random shared by Python, generated VEX, and reports.

``random01(seed, element_id)`` is NodeBridge's own sequence. It is not
Blender's, Houdini's, or Unreal's random. Backends may call this function
only when deterministic randomness is enabled and the backend actually emits
the matching snippet. Native scatter nodes keep their own distribution and
are classified as equivalent, not exact.
"""

from __future__ import annotations

_MIX_A = 747796405
_MIX_B = -1403630843  # 2891336453 as signed 32-bit
_MIX_C = -2048144777  # 2246822519 as signed 32-bit
_MIX_D = -1028477379  # 3266489917 as signed 32-bit
_MASK24 = 0xFFFFFF


def _i32(value: int) -> int:
    """Wrap to a signed 32-bit integer, matching VEX ``int`` arithmetic."""

    value &= 0xFFFFFFFF
    if value & 0x80000000:
        value -= 0x100000000
    return value


def _lshr(value: int, bits: int) -> int:
    """Logical right shift on a signed 32-bit value."""

    return _i32(value) >> bits & ((1 << (32 - bits)) - 1)


def hash32(seed: int, element_id: int) -> int:
    """Return a signed 32-bit hash of ``seed`` and ``element_id``."""

    x = _i32(_i32(seed) ^ _i32(_i32(element_id) * _MIX_A + _MIX_B))
    x = _i32(_i32(x ^ _lshr(x, 16)) * _MIX_C)
    x = _i32(_i32(x ^ _lshr(x, 13)) * _MIX_D)
    return _i32(x ^ _lshr(x, 16))


def random01(seed: int, element_id: int) -> float:
    """Return a float in ``[0, 1)`` from :func:`hash32`."""

    return (hash32(seed, element_id) & _MASK24) / float(0x1000000)


def random_range(seed: int, element_id: int, minimum: float, maximum: float) -> float:
    """Lerp ``minimum`` and ``maximum`` with :func:`random01`."""

    return float(minimum) + (float(maximum) - float(minimum)) * random01(seed, element_id)


def random_vector(
    seed: int,
    element_id: int,
    minimum: tuple[float, float, float],
    maximum: tuple[float, float, float],
) -> tuple[float, float, float]:
    """Three independent components, salted so they do not repeat."""

    salts = (11, 29, 47)
    return tuple(
        random_range(int(seed) + salt, element_id, minimum[index], maximum[index])
        for index, salt in enumerate(salts)
    )  # type: ignore[return-value]


def vex_random_library() -> str:
    """VEX functions that implement the same 32-bit hash as :func:`hash32`.

    The integer constants are the signed forms of the Python mix constants.
    CI does not execute VEX; the classification for deterministic random is
    equivalent until that snippet is run inside Houdini.
    """

    return "\n".join(
        [
            "int nb_lshr(int value; int bits) {",
            "    int shifted = value >> bits;",
            "    int mask = (1 << (32 - bits)) - 1;",
            "    return shifted & mask;",
            "}",
            "int nb_hash(int seed; int elem) {",
            "    int x = seed ^ (elem * 747796405 + (-1403630843));",
            "    x = (x ^ nb_lshr(x, 16)) * (-2048144777);",
            "    x = (x ^ nb_lshr(x, 13)) * (-1028477379);",
            "    x = x ^ nb_lshr(x, 16);",
            "    return x;",
            "}",
            "float nb_rand(int seed; int elem) {",
            "    return float(nb_hash(seed, elem) & 16777215) / 16777216.0;",
            "}",
        ]
    )


def unreal_random_library() -> str:
    """Python implementation embedded in generated Unreal scripts.

    Unreal PCG sampling still uses the engine distribution. This helper is
    for editor-side values NodeBridge computes itself.
    """

    return "\n".join(
        [
            "def _nb_i32(value):",
            "    value &= 0xFFFFFFFF",
            "    if value & 0x80000000:",
            "        value -= 0x100000000",
            "    return value",
            "",
            "def _nb_lshr(value, bits):",
            "    return _nb_i32(value) >> bits & ((1 << (32 - bits)) - 1)",
            "",
            "def nb_hash(seed, element_id):",
            "    x = _nb_i32(_nb_i32(seed) ^ _nb_i32(_nb_i32(element_id) * 747796405 + (-1403630843)))",
            "    x = _nb_i32(_nb_i32(x ^ _nb_lshr(x, 16)) * (-2048144777))",
            "    x = _nb_i32(_nb_i32(x ^ _nb_lshr(x, 13)) * (-1028477379))",
            "    return _nb_i32(x ^ _nb_lshr(x, 16))",
            "",
            "def nb_rand(seed, element_id):",
            "    return (nb_hash(seed, element_id) & 16777215) / 16777216.0",
        ]
    )
