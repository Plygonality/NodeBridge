"""Blender node-tree extractor.

The extractor is the Blender host frontend. ``bpy`` is never imported here.
"""

from __future__ import annotations

from typing import Any

from nodebridge.hosts.blender.frontend import BlenderFrontend
from nodebridge.ir.schema import IRDocument


class BlenderExtractor(BlenderFrontend):
    """Inspect a Blender node tree and emit IR.

    Accepts a :class:`~nodebridge.hosts.native.NativeGraph` fixture, a JSON
    dict, or a duck-typed bpy tree. Live bpy inspection lives in
    ``nodebridge.hosts.blender.runtime``.
    """

    application = "blender"

    def extract(self, source: Any) -> IRDocument:
        return super().extract(source)
