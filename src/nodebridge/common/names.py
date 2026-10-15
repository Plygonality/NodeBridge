"""Target-safe names derived from source labels."""

from __future__ import annotations

import re

_UNSAFE = re.compile(r"[^a-z0-9_]+")
_UNDERSCORES = re.compile(r"_+")


def sanitize_identifier(name: str, *, fallback: str = "node") -> str:
    """Turn a source label into a lowercase identifier.

    ``Building Scatter`` becomes ``building_scatter``. The result is safe for
    Houdini node names, spare parameters, and Unreal asset names.
    """

    text = (name or "").strip().lower().replace("-", "_")
    text = _UNSAFE.sub("_", text)
    text = _UNDERSCORES.sub("_", text).strip("_")
    if not text:
        text = fallback
    if text[0].isdigit():
        text = f"n_{text}"
    return text[:64]


def unique_name(name: str, used: set[str], *, fallback: str = "node") -> str:
    """Return a sanitized name that is not already in ``used``."""

    base = sanitize_identifier(name, fallback=fallback)
    candidate = base
    index = 2
    while candidate in used:
        suffix = f"_{index}"
        candidate = f"{base[: 64 - len(suffix)]}{suffix}"
        index += 1
    used.add(candidate)
    return candidate
