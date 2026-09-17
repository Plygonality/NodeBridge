"""Houdini host plugin: SOP frontend and backend."""

from __future__ import annotations

from nodebridge.core.capabilities import CapabilitySet
from nodebridge.hosts.contract import Implementation
from nodebridge.hosts.houdini.backend import HoudiniBackend
from nodebridge.hosts.houdini.capabilities import (
    HOUDINI_GRAPH_SYSTEMS,
    HOUDINI_VERSIONS,
    houdini_capabilities,
)
from nodebridge.hosts.houdini.frontend import HoudiniFrontend


class HoudiniHost:
    """Houdini as a peer host with SOP frontend and backend."""

    id = "houdini"
    display_name = "SideFX Houdini"
    versions = HOUDINI_VERSIONS
    graph_systems = HOUDINI_GRAPH_SYSTEMS

    def __init__(self) -> None:
        self.frontend = HoudiniFrontend()
        self.backend = HoudiniBackend()
        self.capabilities: CapabilitySet = houdini_capabilities()

    def implementation_for(self, operation: str) -> Implementation:
        return self.backend.implementation_for(operation)
