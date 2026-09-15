"""JSON serialization round-trip and versioning tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nodebridge.core.exceptions import SerializationError, VersionError
from nodebridge.core.graph import GraphSystem
from nodebridge.core.types import DataType
from nodebridge.ir.deserializer import deserialize_document, loads
from nodebridge.ir.schema import IRDocument
from nodebridge.ir.serializer import dump, dumps, serialize_document
from nodebridge.ir.versioning import (
    DEFAULT_MIGRATIONS,
    IR_VERSION,
    PACKAGE_VERSION,
    IdentityMigration,
    MigrationRegistry,
    ensure_supported,
)
from tests.helpers import make_math_add_graph, make_transform_graph


def test_math_add_round_trip_preserves_semantics() -> None:
    original = make_math_add_graph().graph
    document = IRDocument(graph=original, source=original.provenance)
    text = dumps(document)
    restored = loads(text)
    assert restored.ir_version == IR_VERSION
    assert restored.nodebridge_version == PACKAGE_VERSION
    node = restored.graph.get_node("node_add")
    assert node.operation == "math.add"
    assert node.inputs["sock_a"].default == 1.0
    assert node.parameters["operation"].value == "ADD"
    assert node.metadata.ui.position == (120.0, 40.0)
    assert node.metadata.provenance.original_type == "ShaderNodeMath"


def test_transform_graph_round_trip_is_stable() -> None:
    original = make_transform_graph().graph
    first = dumps(original)
    second = dumps(loads(first))
    assert first == second
    restored = loads(first).graph
    assert restored.system is GraphSystem.GEOMETRY
    assert len(restored.connections) == 3
    assert restored.connections[0].source_socket
    link = next(item for item in restored.connections if item.id == "link_offset")
    assert link.source_node == "node_offset"
    assert link.target_socket == "xf_t"
    xform = restored.get_node("node_xform")
    assert xform.metadata.mapping.source_node_id == "bpy_node_xform"
    assert xform.inputs["xf_t"].data_type.builtin is DataType.VECTOR3


def test_document_envelope_fields() -> None:
    graph = make_math_add_graph().graph
    payload = serialize_document(IRDocument(graph=graph, source=graph.provenance))
    assert payload["nodebridge_version"] == PACKAGE_VERSION
    assert payload["ir_version"] == "1"
    assert payload["source"]["application"] == "blender"
    assert "graph" in payload
    assert payload["graph"]["id"] == graph.id


def test_committed_fixtures_round_trip() -> None:
    fixtures = Path(__file__).parent / "fixtures"
    for name in ("math_add.nodebridge.json", "transform_geometry.nodebridge.json"):
        text = (fixtures / name).read_text(encoding="utf-8")
        document = loads(text)
        assert dumps(document) == text
        assert document.ir_version == IR_VERSION


def test_dump_and_load_file(tmp_path: Path) -> None:
    path = tmp_path / "graph.nodebridge.json"
    graph = make_transform_graph().graph
    dump(graph, path)
    restored = loads(path.read_text(encoding="utf-8"))
    assert restored.graph.name == "transform_geometry"
    assert json.loads(path.read_text())["ir_version"] == "1"


def test_invalid_json_raises() -> None:
    with pytest.raises(SerializationError):
        loads("{not json")
    with pytest.raises(SerializationError):
        deserialize_document({"nodebridge_version": "0.1.0", "ir_version": "1"})


def test_unsupported_ir_version_raises() -> None:
    payload = serialize_document(IRDocument(graph=make_math_add_graph().graph))
    payload["ir_version"] = "99"
    with pytest.raises(VersionError):
        deserialize_document(payload)
    with pytest.raises(VersionError):
        ensure_supported("99")


def test_migration_registry_upgrades_document() -> None:
    registry = MigrationRegistry()
    registry.register(IdentityMigration(from_version="0", to_version=IR_VERSION))
    upgraded = registry.upgrade({"ir_version": "0", "graph": {}})
    assert upgraded["ir_version"] == IR_VERSION


def test_default_migrations_have_no_hidden_steps() -> None:
    with pytest.raises(VersionError):
        DEFAULT_MIGRATIONS.upgrade({"ir_version": "0"})
