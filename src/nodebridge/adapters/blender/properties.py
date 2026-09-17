"""Blender node-property helpers."""

from typing import Any


def blender_properties(node: Any) -> dict[str, Any]:
    """Read JSON-safe properties from a duck-typed Blender node."""
    values: dict[str, Any] = {}
    for attr in ("operation", "data_type", "domain", "mode", "density", "seed"):
        if hasattr(node, attr):
            value = getattr(node, attr)
            if value is None or isinstance(value, (bool, int, float, str, list, tuple, dict)):
                values[attr] = value
    return values
