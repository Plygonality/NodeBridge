"""Checks that run before and after code generation.

Unsupported operations stay in the graph and in the script. Validation
reports them. It does not delete them.
"""

from __future__ import annotations

import ast
import re

from nodebridge.ir.semantic import SemanticGraph
from nodebridge.ir.types import TypeCompatibility, TypeRef, compatibility
from nodebridge.translation.confidence import TranslationRecord

_NODE_NAME = re.compile(r"createNode\([^,\n]+,\s*'([^']*)'\)")


def validate_semantic(graph: SemanticGraph) -> list[str]:
    """Return problems in a semantic graph. An empty list means the graph is usable."""

    issues: list[str] = []
    seen: set[str] = set()
    for operation in graph.operations:
        if operation.id in seen:
            issues.append(f"Duplicate operation id {operation.id}.")
        seen.add(operation.id)
        if operation.subgraph is not None:
            issues.extend(f"{operation.id}: {issue}" for issue in validate_semantic(operation.subgraph))
    for edge in graph.edges:
        source = graph.try_get(edge.from_operation)
        destination = graph.try_get(edge.to_operation)
        if source is None or destination is None:
            issues.append(f"Edge {edge.id} references a missing operation.")
            continue
        source_port = source.outputs.get(edge.from_port)
        dest_port = destination.inputs.get(edge.to_port)
        if source_port is None or dest_port is None:
            continue
        result = compatibility(
            TypeRef(source_port.data_type, source_port.field),
            TypeRef(dest_port.data_type, dest_port.field),
        )
        if result is TypeCompatibility.INCOMPATIBLE:
            issues.append(
                f"Incompatible connection {source.name}.{edge.from_port} ({source_port.data_type.value}) "
                f"-> {destination.name}.{edge.to_port} ({dest_port.data_type.value})."
            )
    return issues


def validate_script(code: str, records: list[TranslationRecord], target: str) -> list[str]:
    """Check that the generated script is structured and accounts for every operation."""

    issues: list[str] = []
    if "def build(" not in code:
        issues.append("Generated script has no build() function.")
    if target == "houdini" and "import hou" not in code:
        issues.append("Houdini script does not import hou.")
    if target == "unreal" and "import unreal" not in code:
        issues.append("Unreal script does not import unreal.")
    if code.count("\n") < 8:
        issues.append("Generated script is too short to be a readable network.")
    try:
        ast.parse(code)
    except SyntaxError as exc:
        issues.append(f"Generated script is not valid Python: {exc}.")
    for record in records:
        marker = f"# operation: {record.operation_id}"
        if marker not in code:
            issues.append(f"Operation {record.operation_id} ({record.operation}) does not appear in the script.")
    if target == "houdini" and "createNode('geo'" in code and "createNode('file'" in code:
        issues.append("SOP script contains a File SOP. NodeBridge should rebuild the network, not import baked geometry.")
    for name in _NODE_NAME.findall(code):
        if not name or any(character.isspace() for character in name):
            issues.append(f"Generated node name {name!r} is not a single identifier.")
    return issues
