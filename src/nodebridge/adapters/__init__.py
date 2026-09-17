"""Source adapters. Prefer ``nodebridge.hosts`` for new code.

These modules re-export host frontends so existing imports keep working.
"""

from nodebridge.adapters.base import SourceAdapter, UnimplementedAdapter

__all__ = ["SourceAdapter", "UnimplementedAdapter"]
