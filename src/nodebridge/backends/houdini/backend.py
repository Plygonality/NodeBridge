"""Houdini SOP backend.

Host-plugin implementation lives in ``nodebridge.hosts.houdini``. This
module re-exports it so existing imports keep working.
"""

from nodebridge.hosts.houdini.backend import HoudiniBackend, emit_houdini_script

__all__ = ["HoudiniBackend", "emit_houdini_script"]
