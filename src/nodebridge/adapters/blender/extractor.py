"""Blender node-tree extractor (Milestone 2).

This module intentionally does not import ``bpy``. Doing so would make the
core package require Blender at install time.
"""

from __future__ import annotations

from typing import Any

from nodebridge.adapters.base import UnimplementedAdapter
from nodebridge.core.exceptions import AdapterError
from nodebridge.ir.schema import IRDocument


class BlenderExtractor(UnimplementedAdapter):
    """Inspect a Blender node tree through ``bpy`` and emit IR.

    Planned coverage (Milestone 2, Geometry Nodes subset):

    * ``math.*``
    * ``vector.*``
    * ``geometry.transform``
    * ``geometry.join``
    * ``geometry.modify_position``
    """

    application = "blender"

    def extract(self, source: Any) -> IRDocument:
        raise AdapterError(
            "Blender extraction is Milestone 2. Pass a serialized IR document "
            "to inspect or validate graphs in Milestone 1."
        )
