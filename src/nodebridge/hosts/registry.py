"""Registry of host plugins.

Future hosts register themselves here. The compiler looks up hosts by id
instead of switching on application names.
"""

from __future__ import annotations

from nodebridge.core.exceptions import HostError
from nodebridge.hosts.contract import HostPlugin

HOST_ALIASES: dict[str, str] = {
    "bpy": "blender",
    "blender-gn": "blender",
    "geometry_nodes": "blender",
    "houdini-sop": "houdini",
    "sidefx": "houdini",
    "ue": "unreal",
    "ue5": "unreal",
    "unrealengine": "unreal",
    "pcg": "unreal",
}


class HostRegistry:
    """id → host plugin."""

    def __init__(self) -> None:
        self._hosts: dict[str, HostPlugin] = {}

    def register(self, host: HostPlugin) -> HostPlugin:
        host_id = getattr(host, "id", "")
        if not host_id:
            raise HostError("Host plugin is missing an id")
        if host_id in self._hosts:
            raise HostError(f"Host already registered: {host_id}")
        self._hosts[host_id] = host
        return host

    def get(self, host_id: str) -> HostPlugin:
        canonical = canonicalize_host_id(host_id)
        try:
            return self._hosts[canonical]
        except KeyError as exc:
            raise HostError(f"Unknown host: {host_id!r}") from exc

    def contains(self, host_id: str) -> bool:
        return canonicalize_host_id(host_id) in self._hosts

    def names(self) -> list[str]:
        return sorted(self._hosts)

    def all(self) -> list[HostPlugin]:
        return [self._hosts[name] for name in self.names()]


DEFAULT_HOST_REGISTRY = HostRegistry()


def canonicalize_host_id(host_id: str) -> str:
    """Return the canonical host id for *host_id*."""
    key = host_id.strip().lower().replace(" ", "")
    return HOST_ALIASES.get(key, key)


def register_host(
    host: HostPlugin,
    *,
    registry: HostRegistry | None = None,
) -> HostPlugin:
    """Register *host* on the default (or provided) registry."""
    catalog = registry or DEFAULT_HOST_REGISTRY
    return catalog.register(host)


def get_host(host_id: str, *, registry: HostRegistry | None = None) -> HostPlugin:
    """Look up a registered host."""
    catalog = registry or DEFAULT_HOST_REGISTRY
    return catalog.get(host_id)


def list_hosts(*, registry: HostRegistry | None = None) -> list[str]:
    """Sorted registered host ids."""
    catalog = registry or DEFAULT_HOST_REGISTRY
    return catalog.names()
