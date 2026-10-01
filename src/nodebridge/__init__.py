"""NodeBridge — a cross-DCC procedural compiler.

NodeBridge translates procedural meaning. Source nodes are syntax. The
semantic IR is the meaning. Target backends choose a native implementation.

Importing this package does not require Blender, Houdini, or Unreal.
"""

from nodebridge.ir.serialization import IR_VERSION

__version__ = "0.3.0"

bl_info = {
    "name": "NodeBridge",
    "author": "NodeBridge Contributors",
    "version": (0, 3, 0),
    "blender": (4, 2, 0),
    "location": "View3D and Node Editor > Sidebar > NodeBridge",
    "description": "Cross-DCC procedural compiler for Geometry Nodes, shaders, and the compositor",
    "category": "Node",
}

__all__ = ["IR_VERSION", "__version__", "bl_info"]


def register() -> None:
    """Register the Blender add-on. Outside Blender this is a no-op."""

    try:
        import bpy  # type: ignore
    except ImportError:
        return
    from nodebridge.addon import register as register_addon

    register_addon(bpy)


def unregister() -> None:
    """Unregister the Blender add-on. Outside Blender this is a no-op."""

    try:
        import bpy  # type: ignore
    except ImportError:
        return
    from nodebridge.addon import unregister as unregister_addon

    unregister_addon(bpy)
