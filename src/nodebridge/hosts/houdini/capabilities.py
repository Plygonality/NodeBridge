"""Houdini host capability declaration."""

from __future__ import annotations

from nodebridge.core.capabilities import Capability, CapabilitySet

HOUDINI_GRAPH_SYSTEMS = ("sop",)
HOUDINI_VERSIONS = ("20.0", "20.5", "21.0")


def houdini_capabilities() -> CapabilitySet:
    """Features the Houdini SOP host can represent."""
    return CapabilitySet(
        [
            Capability.SOP,
            Capability.VEX,
            Capability.ATTRIBUTES,
            Capability.PACKED_PRIMITIVES,
            Capability.CURVES,
            Capability.INSTANCES,
            Capability.MESH,
            Capability.TRANSFORMS,
            Capability.RANDOMNESS,
            Capability.POINT_DATA,
            Capability.CUSTOM_CODE,
        ]
    )
