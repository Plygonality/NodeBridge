"""Blender adapter package.

``bpy`` must only be imported from this package, never from ``nodebridge.core``
or ``nodebridge.ir``. Extraction is Milestone 2.
"""

from nodebridge.adapters.blender.extractor import BlenderExtractor

__all__ = ["BlenderExtractor"]
