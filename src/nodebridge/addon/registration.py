"""Register the Blender add-on classes. Imported only from register()."""

from __future__ import annotations

import bpy

from nodebridge.addon.operators import CLASSES as OPERATOR_CLASSES
from nodebridge.addon.panels import CLASSES as PANEL_CLASSES
from nodebridge.addon.properties import NodeBridgeProperties

_CLASSES = (NodeBridgeProperties, *OPERATOR_CLASSES, *PANEL_CLASSES)


def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.nodebridge = bpy.props.PointerProperty(type=NodeBridgeProperties)


def unregister() -> None:
    if hasattr(bpy.types.WindowManager, "nodebridge"):
        del bpy.types.WindowManager.nodebridge
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
