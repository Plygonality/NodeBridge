"""Blender add-on package.

Thin UI over the NodeBridge library. It must never contain translation
logic. The add-on is a scaffold: register() is a no-op until the UI
milestone.
"""

bl_info = {
    "name": "NodeBridge",
    "author": "NodeBridge Contributors",
    "version": (0, 2, 0),
    "blender": (4, 2, 0),
    "location": "Node Editor > Sidebar > NodeBridge",
    "description": "Compile Blender Geometry Nodes to and from other DCC procedural graphs via NodeBridge.",
    "category": "Node",
}


def register() -> None:
    """Register add-on classes. UI not implemented yet."""
    return None


def unregister() -> None:
    """Unregister add-on classes. UI not implemented yet."""
    return None
