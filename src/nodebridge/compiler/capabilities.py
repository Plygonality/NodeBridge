"""Capability data for source node types and target operations.

The UI and the documentation render this data. They do not own a second table.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from nodebridge.backend.houdini.mappings import load as load_houdini
from nodebridge.backend.unreal.backend import UnrealBackend
from nodebridge.frontend.blender.lower import LOWERERS, _EXPLICIT_UNSUPPORTED, ensure_lowerers
from nodebridge.ir.semantic import OperationKind
from nodebridge.translation.registry import REGISTRY


@dataclass(frozen=True)
class Capability:
    """One semantic operation across the current frontends and backends."""

    operation: str
    blender: str
    houdini: str
    unreal: str
    houdini_implementation: str
    unreal_implementation: str


def blender_node_types() -> list[str]:
    """Blender node idnames the parser can lower into semantic operations."""

    ensure_lowerers()
    hidden = set(_EXPLICIT_UNSUPPORTED)
    return sorted(node_type for node_type in LOWERERS if node_type not in hidden)


def capability_matrix() -> list[Capability]:
    """One row per semantic operation kind."""

    load_houdini()
    produced = _blender_operation_names()
    unreal = UnrealBackend()
    rows = []
    for kind in OperationKind:
        houdini = REGISTRY.get(kind, "houdini")
        unreal_class = unreal.classify(kind)
        rows.append(
            Capability(
                operation=kind.value,
                blender="yes" if kind.value in produced or kind.name in produced else "no",
                houdini=houdini.confidence.value if houdini is not None else "no",
                unreal=unreal_class.confidence.value,
                houdini_implementation=houdini.implementation if houdini is not None else "",
                unreal_implementation=unreal_class.implementation,
            )
        )
    return rows


def render_markdown() -> str:
    """Markdown table of the current capability matrix."""

    lines = [
        "| Operation | Blender | Houdini | Unreal |",
        "| --- | --- | --- | --- |",
    ]
    for row in capability_matrix():
        lines.append(f"| {row.operation} | {row.blender} | {row.houdini} | {row.unreal} |")
    return "\n".join(lines) + "\n"


@lru_cache(maxsize=1)
def _blender_operation_names() -> frozenset[str]:
    """Operation kinds named by the Blender lowerers."""

    package = Path(__file__).resolve().parents[1]
    paths = list((package / "frontend" / "blender").glob("*.py"))
    paths.append(package / "compiler" / "rewrite.py")
    found: set[str] = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "OperationKind":
                member = getattr(OperationKind, node.attr, None)
                if isinstance(member, OperationKind):
                    found.add(member.value)
                    found.add(member.name)
    found.add(OperationKind.UNSUPPORTED.value)
    return frozenset(found)
