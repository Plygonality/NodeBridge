"""Unreal Engine 5 backend (Milestone 7).

UE5 is heterogeneous: PCG, Material Editor, Geometry Script, and
Blueprints may all be valid targets depending on source semantics.
"""

from __future__ import annotations

from nodebridge.backends.base import UnimplementedBackend
from nodebridge.core.capabilities import CapabilitySet, TargetCapability
from nodebridge.core.exceptions import BackendError
from nodebridge.core.graph import IRGraph


class UnrealBackend(UnimplementedBackend):
    """Translate IR graphs into an appropriate Unreal procedural system."""

    name = "unreal"
    capabilities = CapabilitySet(
        [
            TargetCapability.PCG,
            TargetCapability.MATERIAL,
            TargetCapability.GEOMETRY_SCRIPT,
            TargetCapability.BLUEPRINT,
        ]
    )

    def generate(self, graph: IRGraph) -> str:
        raise BackendError(
            "Unreal generation is Milestone 7. Milestone 1 only defines the IR."
        )
