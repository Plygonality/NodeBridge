"""Blender adapter package.

``bpy`` must only be imported from ``nodebridge.hosts.blender.runtime``.
"""

from nodebridge.adapters.blender.extractor import BlenderExtractor

__all__ = ["BlenderExtractor"]
