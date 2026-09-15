"""Target backends. Milestone 1 ships only the backend contract."""

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
