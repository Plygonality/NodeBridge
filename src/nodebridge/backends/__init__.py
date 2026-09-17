"""Target backends. Prefer ``nodebridge.hosts`` for new code.

GraphFragment remains the one-to-many backend return type used by tests
and compatibility shims.
"""

from nodebridge.backends.base import (
    GraphFragment,
    TargetBackend,
    TargetConnectionSpec,
    TargetNodeSpec,
    UnimplementedBackend,
)

__all__ = [
    "GraphFragment",
    "TargetBackend",
    "TargetConnectionSpec",
    "TargetNodeSpec",
    "UnimplementedBackend",
]
