"""Unreal Engine 5 backend.

Host-plugin implementation lives in ``nodebridge.hosts.unreal``.
"""

from nodebridge.hosts.unreal.backend import UnrealBackend, emit_unreal_script

__all__ = ["UnrealBackend", "emit_unreal_script"]
