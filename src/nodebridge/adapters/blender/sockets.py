"""Blender socket-type mapping helpers (Milestone 2)."""

from nodebridge.core.exceptions import AdapterError


def map_blender_socket_type(bl_idname: str) -> None:
    """Reserved for mapping Blender socket types onto :class:`TypeRef`."""
    raise AdapterError("Blender socket mapping is not implemented yet.")
