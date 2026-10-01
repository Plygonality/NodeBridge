"""NodeBridge: a cross-DCC procedural compiler.

NodeBridge reads procedural node trees in Blender, translates their
procedural intent through a typed intermediate representation, and
generates code that builds a native procedural system in another DCC.

This package is both a pure-Python library and a Blender add-on. The
compiler never imports ``bpy``; only ``nodebridge.addon`` and
``nodebridge.frontend.blender.context`` touch the Blender API, and only
when Blender loads the add-on. All internal imports are relative so the
package works as a Blender 4.2+ extension (``bl_ext.*.nodebridge``), as a
legacy add-on, and as a normal Python package.
"""

__version__ = "0.3.0"

bl_info = {
    "name": "NodeBridge",
    "author": "NodeBridge Contributors",
    "version": (0, 3, 0),
    "blender": (4, 2, 0),
    "location": "Node Editor > Sidebar (N) > NodeBridge",
    "description": "Compile Geometry, Shader and Compositor node trees into native Houdini or Unreal Engine 5 code.",
    "category": "Node",
}


def register() -> None:
    from . import addon

    addon.register()


def unregister() -> None:
    from . import addon

    addon.unregister()
