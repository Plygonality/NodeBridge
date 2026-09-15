"""Blender add-on package (Milestone 6).

The add-on must stay a thin UI over the NodeBridge library. It should
never contain translation logic.
"""

bl_info = {
    "name": "NodeBridge",
    "author": "NodeBridge Contributors",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "Node Editor > Sidebar > NodeBridge",
    "description": "Export Blender node trees through the NodeBridge IR.",
    "category": "Node",
}


def register() -> None:
    """Register add-on classes. Implemented in Milestone 6."""
    return None


def unregister() -> None:
    """Unregister add-on classes. Implemented in Milestone 6."""
    return None
