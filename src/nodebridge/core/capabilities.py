"""Host-independent capability vocabulary.

Capabilities describe *what kind of system* can implement an operation.
They are not translation mappings and they do not import any DCC SDK.

Host plugins declare a :class:`CapabilitySet`. The compiler asks a host
whether it can implement a semantic operation; translators must not
scatter capability assumptions through lowering code.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable


class Capability(str, Enum):
    """A host-system feature that a frontend or backend may use."""

    GEOMETRY_NODES = "geometry_nodes"
    SOP = "sop"
    VEX = "vex"
    VOP = "vop"
    PCG = "pcg"
    MATERIAL = "material"
    GEOMETRY_SCRIPT = "geometry_script"
    BLUEPRINT = "blueprint"
    POST_PROCESS = "post_process"
    FIELDS = "fields"
    INSTANCES = "instances"
    CURVES = "curves"
    ATTRIBUTES = "attributes"
    PACKED_PRIMITIVES = "packed_primitives"
    POINT_DATA = "point_data"
    SPATIAL_DATA = "spatial_data"
    SPAWNING = "spawning"
    MESH = "mesh"
    TRANSFORMS = "transforms"
    RANDOMNESS = "randomness"
    CUSTOM_CODE = "custom_code"
    UNKNOWN = "unknown"


# Milestone 1 name. New code should use :class:`Capability`.
TargetCapability = Capability


class CapabilitySet:
    """Set of capabilities advertised by a host or required by an operation."""

    def __init__(
        self,
        capabilities: Iterable[Capability | str] | None = None,
    ) -> None:
        self._capabilities: set[Capability] = set()
        for item in capabilities or []:
            self.add(item)

    def add(self, capability: Capability | str) -> None:
        if isinstance(capability, Capability):
            self._capabilities.add(capability)
        else:
            self._capabilities.add(Capability(capability))

    def has(self, capability: Capability | str) -> bool:
        token = capability if isinstance(capability, Capability) else Capability(capability)
        return token in self._capabilities

    def covers(self, required: CapabilitySet) -> bool:
        """Return True if this set includes every capability in *required*."""
        return required._capabilities <= self._capabilities

    def missing(self, required: CapabilitySet) -> list[Capability]:
        """Capabilities in *required* that this set does not provide."""
        return sorted(required._capabilities - self._capabilities, key=lambda item: item.value)

    def as_list(self) -> list[str]:
        """Sorted capability values, for serialization and reports."""
        return sorted(capability.value for capability in self._capabilities)

    def __iter__(self):
        return iter(sorted(self._capabilities, key=lambda item: item.value))

    def __len__(self) -> int:
        return len(self._capabilities)

    def __contains__(self, item: object) -> bool:
        if isinstance(item, Capability):
            return item in self._capabilities
        if isinstance(item, str):
            try:
                return Capability(item) in self._capabilities
            except ValueError:
                return False
        return False
