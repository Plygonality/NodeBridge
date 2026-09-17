"""Compositor extraction is not implemented."""

from nodebridge.core.exceptions import AdapterError


def extract_compositor(node_tree: object) -> None:
    """Reserved for a future compositor frontend."""
    raise AdapterError("Compositor extraction is not implemented.")
