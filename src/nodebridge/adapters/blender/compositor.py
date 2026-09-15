"""Compositor extraction helpers (later milestone)."""

from nodebridge.core.exceptions import AdapterError


def extract_compositor(node_tree: object) -> None:
    """Reserved for compositor-graph extraction."""
    raise AdapterError("Compositor extraction is not implemented yet.")
