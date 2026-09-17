"""Unreal Material Editor fragment builders.

Not part of the PCG vertical slice. Left as an explicit gap so PCG is
not silently used as a material substitute.
"""

from nodebridge.core.exceptions import BackendError


def build_material_fragment(operation: str) -> None:
    """Reserved for a future Material Editor backend."""
    raise BackendError(
        f"Unreal material generation is not implemented for {operation!r}."
    )
