"""Blender node-property capture helpers (Milestone 2)."""

from nodebridge.core.exceptions import AdapterError


def capture_node_properties(node: object) -> None:
    """Reserved for reading Blender node properties into IR parameters."""
    raise AdapterError("Blender property capture is not implemented yet.")
