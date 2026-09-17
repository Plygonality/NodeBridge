"""Host plugins: frontends, backends, and native construction plans.

Core compiler code looks up hosts through the registry. It never switches
on application names.
"""

from nodebridge.hosts.contract import (
    HostBackend,
    HostFrontend,
    HostPlugin,
    Implementation,
    LoweringFragment,
)
from nodebridge.hosts.native import NativeGraph, NativeLink, NativeNode, NativeSocket
from nodebridge.hosts.registry import (
    DEFAULT_HOST_REGISTRY,
    get_host,
    list_hosts,
    register_host,
)

__all__ = [
    "DEFAULT_HOST_REGISTRY",
    "HostBackend",
    "HostFrontend",
    "HostPlugin",
    "Implementation",
    "LoweringFragment",
    "NativeGraph",
    "NativeLink",
    "NativeNode",
    "NativeSocket",
    "get_host",
    "list_hosts",
    "register_host",
]


def register_builtin_hosts() -> None:
    """Register Blender, Houdini, and Unreal if they are not already present."""
    from nodebridge.hosts.blender import BlenderHost
    from nodebridge.hosts.houdini import HoudiniHost
    from nodebridge.hosts.unreal import UnrealHost

    registry = DEFAULT_HOST_REGISTRY
    for host in (BlenderHost(), HoudiniHost(), UnrealHost()):
        if not registry.contains(host.id):
            registry.register(host)


register_builtin_hosts()
