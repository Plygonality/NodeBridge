"""Blender socket classification shared by the parser and tests."""

from __future__ import annotations

from nodebridge.ir.types import DataType, data_type_from_blender_socket


def socket_data_type(socket: object) -> DataType:
    """Read a Blender socket, or a duck-typed fixture socket."""

    socket_type = (
        getattr(socket, "bl_idname", None)
        or getattr(socket, "type", None)
        or getattr(socket, "socket_type", None)
        or ""
    )
    if not isinstance(socket_type, str):
        socket_type = str(socket_type)
    return data_type_from_blender_socket(socket_type)


def is_field_socket(socket: object) -> bool:
    """Geometry Nodes draws field sockets as diamonds."""

    if getattr(socket, "is_field", False):
        return True
    shape = str(getattr(socket, "display_shape", "") or "")
    return shape.upper() == "DIAMOND"


def pythonize(value: object) -> object:
    """Convert bpy and mathutils values into JSON-safe Python values."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    type_name = type(value).__name__
    if type_name in {"Vector", "Euler", "Color", "Quaternion", "bpy_prop_array"} or isinstance(value, (list, tuple)):
        return [pythonize(item) for item in list(value)]
    if hasattr(value, "name") and type_name not in {"Vector", "Euler", "Color", "Quaternion"}:
        return str(getattr(value, "name"))
    return str(value)
