"""Blender add-on registration.

``bpy`` is passed in by :func:`nodebridge.register`. This package imports
without Blender.
"""

from __future__ import annotations

_CLASSES = []


def register(bpy) -> None:
    """Register the NodeBridge N-panel and operators."""

    global _CLASSES
    from nodebridge.addon.ui import build_classes

    _CLASSES = build_classes(bpy)
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.nodebridge = bpy.props.PointerProperty(type=_CLASSES[0])


def unregister(bpy) -> None:
    """Remove the NodeBridge N-panel and operators."""

    global _CLASSES
    if hasattr(bpy.types.Scene, "nodebridge"):
        del bpy.types.Scene.nodebridge
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    _CLASSES = []
