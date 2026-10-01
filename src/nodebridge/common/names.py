"""Name sanitization for target DCC restrictions.

Meaningful source names are preserved where possible:
``"Building Scatter"`` becomes ``building_scatter`` (Houdini node) or
``BuildingScatter`` (Unreal asset).
"""

from __future__ import annotations

import keyword
import re

_SPLIT = re.compile(r"[^0-9A-Za-z]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def words(name: str) -> list[str]:
    parts: list[str] = []
    for chunk in _SPLIT.split(name or ""):
        if chunk:
            parts.extend(piece for piece in _CAMEL.split(chunk) if piece)
    return parts


def snake_case(name: str, fallback: str = "node") -> str:
    """``"Building Scatter.001"`` -> ``building_scatter_001``."""
    result = "_".join(word.lower() for word in words(name)) or fallback
    if result[0].isdigit():
        result = f"n_{result}"
    return result


def pascal_case(name: str, fallback: str = "Node") -> str:
    """``"building scatter"`` -> ``BuildingScatter``."""
    result = "".join(word[:1].upper() + word[1:] for word in words(name)) or fallback
    if result[0].isdigit():
        result = f"N{result}"
    return result


def houdini_node_name(name: str, fallback: str = "node") -> str:
    """Houdini node names allow ``[A-Za-z0-9_.-]`` and must not start with a digit."""
    return snake_case(name, fallback)[:96]


def houdini_label_name(name: str, fallback: str = "node") -> str:
    """Like :func:`houdini_node_name` but keeps the case (``OUT``, ``IN_Geometry``)."""
    result = "_".join(w for w in _SPLIT.split(name or "") if w) or fallback
    if result[0].isdigit():
        result = f"n_{result}"
    return result[:96]


def houdini_parm_name(name: str, fallback: str = "parm") -> str:
    """Spare parameter names: lowercase identifiers without dots."""
    return snake_case(name, fallback)[:64]


def unreal_asset_name(name: str, prefix: str = "", fallback: str = "Asset") -> str:
    """Unreal asset names: no spaces or ``.`` ``/`` characters."""
    base = pascal_case(name, fallback)
    return f"{prefix}{base}"[:120]


def unreal_parameter_name(name: str, fallback: str = "Parameter") -> str:
    """Material / PCG parameter names keep spaces readable but drop punctuation."""
    cleaned = " ".join(words(name))
    return cleaned or fallback


def python_identifier(name: str, fallback: str = "value") -> str:
    """Variable names used inside generated scripts."""
    result = snake_case(name, fallback)
    if keyword.iskeyword(result) or result in {"hou", "unreal", "node", "geo", "graph"}:
        result = f"{result}_"
    return result


class NameAllocator:
    """Hands out unique names within one scope."""

    def __init__(self, reserved: set[str] | None = None) -> None:
        self._used: set[str] = set(reserved or ())

    def allocate(self, base: str) -> str:
        name = base
        index = 1
        while name in self._used:
            index += 1
            name = f"{base}_{index}"
        self._used.add(name)
        return name

    def __contains__(self, name: str) -> bool:
        return name in self._used
