"""Houdini backend package.

``hou`` must only be imported from this package. Generation is Milestone 3.
"""

from nodebridge.backends.houdini.backend import HoudiniBackend

__all__ = ["HoudiniBackend"]
