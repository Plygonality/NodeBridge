"""Houdini backend package. ``hou`` is imported only from hosts.houdini.runtime."""

from nodebridge.backends.houdini.backend import HoudiniBackend

__all__ = ["HoudiniBackend"]
