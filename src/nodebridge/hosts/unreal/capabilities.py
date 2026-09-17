"""Unreal Engine 5 PCG host capability declaration."""

from __future__ import annotations

from nodebridge.core.capabilities import Capability, CapabilitySet

UNREAL_GRAPH_SYSTEMS = ("pcg",)
UNREAL_VERSIONS = ("5.4", "5.5", "5.6", "5.7")


def unreal_capabilities() -> CapabilitySet:
    """Features the Unreal PCG host can represent.

    PCG Python graph construction exists in UE 5.7+ (experimental):
    ``PCGGraph.add_node_of_type``, ``add_edge``, ``get_input_node``,
    ``get_output_node``. Inspection of pin edges is incomplete. Runtime
    execution requires the Unreal editor; CI uses construction plans.
    """
    return CapabilitySet(
        [
            Capability.PCG,
            Capability.POINT_DATA,
            Capability.SPATIAL_DATA,
            Capability.ATTRIBUTES,
            Capability.SPAWNING,
            Capability.INSTANCES,
            Capability.TRANSFORMS,
            Capability.RANDOMNESS,
            Capability.MESH,
            Capability.MATERIAL,
            Capability.GEOMETRY_SCRIPT,
            Capability.BLUEPRINT,
        ]
    )
