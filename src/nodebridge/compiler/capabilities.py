"""Capability database derived from translator metadata.

The matrix is computed from the translator registry, so adding a
translator (or a whole backend) updates every table, UI list and doc
generated from it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..ir.operations import Category, list_operations
from ..translation.confidence import UNSUPPORTED_DEFAULT, Classification
from ..translation.registry import REGISTRY


@dataclass
class CapabilityRow:
    kind: str
    category: str
    description: str
    targets: dict[str, list[tuple[str, Classification]]]  # target -> [(context, classification)]


def _ensure_backends_loaded() -> None:
    from ..backend import registry as backend_registry

    backend_registry.load_builtin_backends()


def capability(kind: str, target: str, context: str) -> Classification:
    _ensure_backends_loaded()
    item = REGISTRY.get(target, context, kind)
    return item.default_classification() if item else UNSUPPORTED_DEFAULT


def capability_matrix(targets: list[str] | None = None) -> list[CapabilityRow]:
    _ensure_backends_loaded()
    from ..backend.registry import list_backends

    backends = [b for b in list_backends() if targets is None or b.id in targets]
    rows: list[CapabilityRow] = []
    for spec in list_operations():
        if spec.category == Category.STRUCTURAL and spec.kind not in ("SUBGRAPH",):
            continue
        cells: dict[str, list[tuple[str, Classification]]] = {}
        for backend in backends:
            entries = []
            for context in sorted(set(backend.contexts.values())):
                item = REGISTRY.get(backend.id, context, spec.kind)
                if item is not None:
                    entries.append((context, item.default_classification()))
            cells[backend.id] = entries
        rows.append(CapabilityRow(spec.kind, spec.category.value, spec.description, cells))
    return rows


def format_matrix_markdown(targets: list[str] | None = None) -> str:
    rows = capability_matrix(targets)
    from ..backend.registry import list_backends

    backends = [b for b in list_backends() if targets is None or b.id in targets]
    header = "| Operation | Category | " + " | ".join(b.display_name for b in backends) + " |"
    lines = [header, "|" + " --- |" * (2 + len(backends))]
    for row in rows:
        cells = []
        for backend in backends:
            entries = row.targets.get(backend.id, [])
            if not entries:
                cells.append("unsupported")
            else:
                cells.append("<br>".join(f"{c.confidence.value.lower()} ({ctx}: {c.implementation})" for ctx, c in entries))
        lines.append(f"| `{row.kind}` | {row.category} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
