"""Deterministic, reproducible randomness: ``random(seed, element_id)``.

Every DCC has its own random generator, so the same seed gives different
samples in Blender, Houdini and Unreal. NodeBridge cannot change
Blender's generator, so translated graphs are at best EQUIVALENT with
respect to random sample values. What NodeBridge *can* guarantee is that
its own generated code is reproducible: the hash below gives identical
results in Python and VEX, and is documented so other backends can port it.

Algorithm: Park-Miller "minimal standard" LCG (multiplier 48271) evaluated
with Schrage's method, so every intermediate value fits in a signed 32-bit
integer. Interleaved xor-shift mixing decorrelates neighbouring IDs. It is
not cryptographic.
"""

from __future__ import annotations

MODULUS = 2147483647  # 2**31 - 1
_Q = 44488
_R = 3399
_A = 48271


def _lcg(x: int) -> int:
    hi, lo = divmod(x, _Q)
    x = _A * lo - _R * hi
    if x <= 0:
        x += MODULUS
    return x


def _mix(x: int) -> int:
    x = _lcg(x)
    return (x ^ (x >> 13)) % (MODULUS - 1) + 1


def hash_int(seed: int, element_id: int, stream: int = 0) -> int:
    """Hash to an integer in ``[1, MODULUS - 1]``."""
    x = abs(int(element_id)) % (MODULUS - 1) + 1
    x = _mix(x)
    x = (x ^ (abs(int(seed)) % (MODULUS - 1))) % (MODULUS - 1) + 1
    x = _mix(x)
    x = (x ^ (abs(int(stream)) % (MODULUS - 1))) % (MODULUS - 1) + 1
    return _mix(_mix(x))


def random_float(seed: int, element_id: int, stream: int = 0) -> float:
    """Uniform float in ``[0, 1]``."""
    return (hash_int(seed, element_id, stream) - 1) / (MODULUS - 2)


def random_range(seed: int, element_id: int, low: float, high: float, stream: int = 0) -> float:
    return low + (high - low) * random_float(seed, element_id, stream)


def random_vector(seed: int, element_id: int, low, high) -> tuple[float, float, float]:
    return tuple(random_range(seed, element_id, low[i], high[i], stream=i) for i in range(3))  # type: ignore[return-value]


VEX_SOURCE = """\
// NodeBridge deterministic random: identical to nodebridge.common.random.
int nb_lcg(int x) {
    int hi = x / 44488;
    int lo = x % 44488;
    x = 48271 * lo - 3399 * hi;
    if (x <= 0) x += 2147483647;
    return x;
}

int nb_mix(int x) {
    x = nb_lcg(x);
    return (x ^ (x >> 13)) % 2147483646 + 1;
}

int nb_hash(int seed; int id; int stream) {
    int x = abs(id) % 2147483646 + 1;
    x = nb_mix(x);
    x = (x ^ (abs(seed) % 2147483646)) % 2147483646 + 1;
    x = nb_mix(x);
    x = (x ^ (abs(stream) % 2147483646)) % 2147483646 + 1;
    return nb_mix(nb_mix(x));
}

float nb_random(int seed; int id; int stream) {
    return (nb_hash(seed, id, stream) - 1) / 2147483645.0;
}
"""
