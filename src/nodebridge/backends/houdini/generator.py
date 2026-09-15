"""Structured Houdini Python script emitter (Milestone 3)."""

from nodebridge.core.exceptions import BackendError


def emit_houdini_script(graph: object) -> str:
    """Reserved for readable, deterministic ``hou`` script generation."""
    raise BackendError("Houdini script generation is not implemented yet.")
