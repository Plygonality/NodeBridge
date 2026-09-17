"""Blender host plugin: Geometry Nodes frontend and backend."""

from __future__ import annotations

from nodebridge.core.capabilities import CapabilitySet
from nodebridge.hosts.blender.backend import BlenderBackend
from nodebridge.hosts.blender.capabilities import (
    BLENDER_GRAPH_SYSTEMS,
    BLENDER_VERSIONS,
    blender_capabilities,
)
from nodebridge.hosts.blender.frontend import BlenderFrontend
from nodebridge.hosts.contract import Implementation


class BlenderHost:
    """Blender as a peer host, not a privileged source."""

    id = "blender"
    display_name = "Blender"
    versions = BLENDER_VERSIONS
    graph_systems = BLENDER_GRAPH_SYSTEMS

    def __init__(self) -> None:
        self.frontend = BlenderFrontend()
        self.backend = BlenderBackend()
        self.capabilities: CapabilitySet = blender_capabilities()

    def implementation_for(self, operation: str) -> Implementation:
        return self.backend.implementation_for(operation)
