"""Unreal Geometry Script fragment builders.

Not part of the PCG vertical slice.
"""

from nodebridge.core.exceptions import BackendError


def build_geometry_script_fragment(operation: str) -> None:
    """Reserved for a future Geometry Script backend."""
    raise BackendError(
        f"Unreal Geometry Script generation is not implemented for {operation!r}."
    )
