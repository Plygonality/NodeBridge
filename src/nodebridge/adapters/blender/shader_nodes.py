"""Shader Nodes mapping notes.

Shader translation is not part of the Geometry Nodes vertical slice.
``ShaderNodeMath`` and ``ShaderNodeVectorMath`` are used *inside* Geometry
Nodes and are handled by the Blender host mappings.
"""

from nodebridge.hosts.blender.mappings import MATH_OPERATIONS, VECTOR_OPERATIONS

__all__ = ["MATH_OPERATIONS", "VECTOR_OPERATIONS"]
