"""Nested Blender node-group walking.

Group calls are represented in IR as ``graph.group`` with
``nested_graph_id``. Recursive bpy walking is not implemented; fixtures
may include nested NativeGraphs later.
"""

from nodebridge.core.exceptions import AdapterError


def walk_node_groups(node_tree: object, *, seen: frozenset[str] | None = None) -> None:
    """Reserved for recursive group extraction with cycle guards."""
    raise AdapterError("Blender group walking is not implemented yet.")
