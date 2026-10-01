"""Target-safe identifiers derived from source names."""

from __future__ import annotations

import re

_NON_IDENT = re.compile(r"[^0-9A-Za-z]+")


def sanitize_identifier(name: str, *, fallback: str = "node") -> str:
    """Turn a human label into a lowercase identifier.

    ``Building Scatter`` becomes ``building_scatter``. The result always
    starts with a letter so it is a legal Houdini node name and a legal
    Python identifier fragment.
    """
    text = _NON_IDENT.sub("_", (name or "").strip()).strip("_").lower()
    if not text:
        text = fallback
    if text[0].isdigit():
        text = f"n_{text}"
    return text[:64]
