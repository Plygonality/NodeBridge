"""Unreal Engine 5 host plugin: PCG frontend and backend."""

from __future__ import annotations

from nodebridge.core.capabilities import CapabilitySet
from nodebridge.hosts.contract import Implementation
from nodebridge.hosts.unreal.backend import UnrealBackend
from nodebridge.hosts.unreal.capabilities import (
    UNREAL_GRAPH_SYSTEMS,
    UNREAL_VERSIONS,
    unreal_capabilities,
)
from nodebridge.hosts.unreal.frontend import UnrealFrontend


class UnrealHost:
    """Unreal as a peer host, not a terminal export target."""

    id = "unreal"
    display_name = "Unreal Engine 5"
    versions = UNREAL_VERSIONS
    graph_systems = UNREAL_GRAPH_SYSTEMS

    def __init__(self) -> None:
        self.frontend = UnrealFrontend()
        self.backend = UnrealBackend()
        self.capabilities: CapabilitySet = unreal_capabilities()

    def implementation_for(self, operation: str) -> Implementation:
        return self.backend.implementation_for(operation)
