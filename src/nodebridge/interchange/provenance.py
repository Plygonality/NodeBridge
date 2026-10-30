"""Stable logical identities and content hashes.

Logical ids name a generator, a nested group, or a semantic operation.
They are derived from normalized source names, not from display names alone,
process ids, or random UUIDs. A content revision is a separate SHA-256 of
the serialized Graph IR bytes. Renaming an object or a nested group changes
the logical id. Editing node settings changes the revision and leaves the
logical id in place.

Identity grammar (``nodebridge:`` namespace):

    nodebridge:/dcc=<dcc>/scene=<scene>/object=<object>/modifier=<modifier>/tree=<tree>

``scene``, ``object`` and ``modifier`` are omitted when empty. ``dcc`` and
``tree`` are required. Components are Unicode NFC, trimmed, with internal
whitespace collapsed. ``/`` and ``\\`` inside a component become ``_`` so
the slash-separated structure stays unambiguous. Two generators that share
a tree name and differ by object or modifier therefore differ. A nested
group appends ``/group/<tree>``. An operation appends ``/op/<id>`` on the
generator or group that owns it.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

from ..ir.semantic import SemanticGraph

_COMPONENT = re.compile(r"[\x00-\x1f]")


def normalize_component(value: str) -> str:
    text = unicodedata.normalize("NFC", str(value)).strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("/", "_").replace("\\", "_")
    text = _COMPONENT.sub("", text)
    return text


def generator_id(*, dcc: str, tree: str, object_name: str = "", modifier: str = "", scene: str = "") -> str:
    """Stable logical id for one source generator. Independent of file bytes."""
    dcc_n = normalize_component(dcc).casefold()
    tree_n = normalize_component(tree)
    if not dcc_n or not tree_n:
        raise ValueError("generator identity requires a dcc and a tree name")
    parts = [f"dcc={dcc_n}"]
    for key, raw in (("scene", scene), ("object", object_name), ("modifier", modifier)):
        item = normalize_component(raw)
        if item:
            parts.append(f"{key}={item}")
    parts.append(f"tree={tree_n}")
    return "nodebridge:/" + "/".join(parts)


def group_id(generator: str, group_tree: str) -> str:
    """Logical id of a nested group under ``generator``. Distinct from the root tree."""
    name = normalize_component(group_tree)
    if not name:
        raise ValueError("group identity requires a group tree name")
    return f"{generator}/group/{name}"


def operation_id(owner: str, op_id: str) -> str:
    """Logical id of one semantic operation. Not a USD prim path."""
    name = normalize_component(op_id)
    if not name:
        raise ValueError("operation identity requires an operation id")
    return f"{owner}/op/{name}"


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def publication_id(artifacts: list[tuple[str, str]]) -> str:
    """Hash of ``path<TAB>sha256`` lines. Does not include ``manifest.json``."""
    lines = [f"{path}\t{digest}" for path, digest in sorted(artifacts)]
    return content_hash(("\n".join(lines) + "\n").encode("utf-8"))


def semantic_operation_records(generator: str, graph: SemanticGraph, groups: dict[str, str]) -> list[dict]:
    """Semantic operation ids in deterministic order.

    These identify operations in the sidecar. They are not per-prim mappings.
    """
    rows: list[dict] = []

    def walk(current: SemanticGraph, owner: str) -> None:
        try:
            ops = current.topological_order()
        except ValueError:
            ops = [current.ops[key] for key in sorted(current.ops)]
        for op in ops:
            rows.append(
                {
                    "operation_id": operation_id(owner, op.id),
                    "kind": op.kind,
                    "name": op.name,
                    "graph": current.name,
                    "source_nodes": list(op.source.nodes),
                }
            )
        for name in sorted(current.subgraphs):
            child = current.subgraphs[name]
            walk(child, groups.get(name, group_id(owner, name)))

    walk(graph, generator)
    return rows
