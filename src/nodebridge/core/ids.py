"""Stable identifiers for graphs, nodes, sockets, and connections.

IDs are opaque strings. Callers may supply their own values (for example
source-application identifiers) or let :class:`IdFactory` mint sequential
ones. Sequential IDs are deterministic and therefore suitable for tests and
generated artefacts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import uuid4

_KIND_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")


def is_valid_id(value: str) -> bool:
    """Return True if *value* is a legal NodeBridge identifier."""
    return bool(value) and _ID_RE.match(value) is not None


def require_id(value: str, *, what: str = "id") -> str:
    """Validate *value* and return it, or raise ``ValueError``."""
    if not is_valid_id(value):
        raise ValueError(f"Invalid {what}: {value!r}")
    return value


@dataclass
class IdFactory:
    """Mint deterministic, unique IDs scoped to one graph-construction session.

    Example::

        ids = IdFactory()
        node_id = ids.next("node")       # "node_0001"
        sock_id = ids.next("socket")     # "socket_0001"
    """

    start: int = 1
    width: int = 4
    _counters: dict[str, int] = field(default_factory=dict)

    def next(self, kind: str) -> str:
        """Return the next sequential ID for *kind* (``node``, ``socket``, ...)."""
        if not _KIND_RE.match(kind):
            raise ValueError(f"Invalid ID kind: {kind!r}")
        current = self._counters.get(kind, self.start - 1) + 1
        self._counters[kind] = current
        return f"{kind}_{current:0{self.width}d}"

    def uuid(self, kind: str) -> str:
        """Return a unique ID that will not collide across independently built graphs."""
        if not _KIND_RE.match(kind):
            raise ValueError(f"Invalid ID kind: {kind!r}")
        return f"{kind}_{uuid4().hex}"

    def peek(self, kind: str) -> int:
        """Return the next integer that would be issued for *kind*."""
        return self._counters.get(kind, self.start)

    def reset(self) -> None:
        """Clear all counters. Intended for tests."""
        self._counters.clear()
