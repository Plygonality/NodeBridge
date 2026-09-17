"""Blender host capability declaration."""

from __future__ import annotations

from nodebridge.core.capabilities import Capability, CapabilitySet

BLENDER_GRAPH_SYSTEMS = ("geometry_nodes",)
BLENDER_VERSIONS = ("4.2", "4.3", "4.4", "4.5")


def blender_capabilities() -> CapabilitySet:
    """Features the Blender Geometry Nodes host can represent."""
    return CapabilitySet(
        [
            Capability.GEOMETRY_NODES,
            Capability.FIELDS,
            Capability.INSTANCES,
            Capability.CURVES,
            Capability.ATTRIBUTES,
            Capability.MESH,
            Capability.TRANSFORMS,
            Capability.RANDOMNESS,
            Capability.POINT_DATA,
            Capability.CUSTOM_CODE,
        ]
    )
