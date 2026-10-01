"""Development loader for the NodeBridge add-on.

Blender's installable add-on is the ``nodebridge`` package in ``src/``.
Zip that folder and install it. This module exists so a checkout can be
enabled from ``blender_addon/nodebridge`` while the library stays in ``src``.
"""

from __future__ import annotations

import sys
from pathlib import Path

bl_info = {
    "name": "NodeBridge",
    "author": "NodeBridge Contributors",
    "version": (0, 3, 0),
    "blender": (4, 2, 0),
    "location": "Node Editor > Sidebar > NodeBridge",
    "description": "Cross-DCC procedural compiler. Translate Blender node graphs into native Houdini and Unreal graphs.",
    "category": "Node",
}

_SRC = Path(__file__).resolve().parents[2] / "src"


def _library():
    src = str(_SRC)
    if not _SRC.is_dir():
        raise RuntimeError(
            "NodeBridge library was not found. Install the src/nodebridge folder "
            "as the add-on, or keep this file inside a full checkout."
        )
    if src not in sys.path:
        sys.path.insert(0, src)
    addon = sys.modules.get("nodebridge")
    if addon is not None and not hasattr(addon, "compiler"):
        sys.modules["nodebridge_addon_entry"] = addon
        del sys.modules["nodebridge"]
    import nodebridge

    return nodebridge


def register() -> None:
    _library().register()


def unregister() -> None:
    _library().unregister()
