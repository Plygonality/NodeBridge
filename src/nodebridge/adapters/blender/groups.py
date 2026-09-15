"""Nested Blender node-group walking (Milestone 2)."""

from nodebridge.core.exceptions import AdapterError


def walk_node_groups(node_tree: object, *, seen: frozenset[str] | None = None) -> None:
    """Reserved for recursive group extraction with cycle guards."""
    raise AdapterError("Blender group walking is not implemented yet.")
