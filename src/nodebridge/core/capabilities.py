"""Target capability vocabulary.

Capabilities describe *what kind of system* can implement an operation.
They are not translation mappings and they do not import any DCC SDK.
"""

from __future__ import annotations

from enum import Enum


class TargetCapability(str, Enum):
    """A host-system feature that a backend may use to realize an operation."""

    SOP = "sop"
    VEX = "vex"
    VOP = "vop"
    PCG = "pcg"
    MATERIAL = "material"
    GEOMETRY_SCRIPT = "geometry_script"
    BLUEPRINT = "blueprint"
    POST_PROCESS = "post_process"
    UNKNOWN = "unknown"


class CapabilitySet:
    """Set of capabilities advertised by a backend or required by an operation."""

    def __init__(self, capabilities: list[TargetCapability] | None = None) -> None:
        self._capabilities = set(capabilities or [])

    def add(self, capability: TargetCapability) -> None:
        self._capabilities.add(capability)

    def has(self, capability: TargetCapability) -> bool:
        return capability in self._capabilities

    def covers(self, required: CapabilitySet) -> bool:
        """Return True if this set includes every capability in *required*."""
        return required._capabilities <= self._capabilities

    def as_list(self) -> list[str]:
        """Sorted capability values, for serialization and reports."""
        return sorted(capability.value for capability in self._capabilities)
