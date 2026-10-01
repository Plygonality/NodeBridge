"""Blender frontend: bpy -> Graph IR -> Semantic IR."""

from . import compositor_nodes, geometry_nodes, shader_nodes  # noqa: F401  (register lifters)
from .frontend import BlenderFrontend

__all__ = ["BlenderFrontend"]
