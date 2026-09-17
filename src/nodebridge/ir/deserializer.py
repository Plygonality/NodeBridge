"""JSON deserialization for IR documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TextIO

from nodebridge.core.exceptions import SerializationError, VersionError
from nodebridge.core.graph import GraphInterface, GraphSystem, IRGraph
from nodebridge.core.link import IRConnection
from nodebridge.core.metadata import Metadata, Provenance, SourceMapping, TranslationEvent, UIHints
from nodebridge.core.node import IRNode, IRParameter
from nodebridge.core.socket import FieldKind, GeometryDomain, IRSocket, SocketDirection
from nodebridge.core.types import TypeRef
from nodebridge.ir.schema import IRDocument
from nodebridge.ir.versioning import (
    DEFAULT_MIGRATIONS,
    SUPPORTED_IR_VERSIONS,
    ensure_supported,
    parse_ir_version,
)


def loads(text: str) -> IRDocument:
    """Parse a JSON string into an :class:`IRDocument`."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SerializationError(f"Invalid JSON: {exc}") from exc
    return deserialize_document(payload)


def load(source: str | Path | TextIO) -> IRDocument:
    """Read JSON from a path or file object."""
    if isinstance(source, (str, Path)):
        text = Path(source).read_text(encoding="utf-8")
    else:
        text = source.read()
    return loads(text)


def deserialize_document(data: dict[str, Any]) -> IRDocument:
    """Build an :class:`IRDocument` from a parsed JSON object."""
    if not isinstance(data, dict):
        raise SerializationError("IR document must be a JSON object")
    required = {"nodebridge_version", "ir_version", "graph"}
    missing = required - set(data)
    if missing:
        raise SerializationError(
            f"IR document is missing required fields: {sorted(missing)}"
        )

    ir_version = parse_ir_version(data.get("ir_version"))
    if ir_version not in SUPPORTED_IR_VERSIONS:
        try:
            data = DEFAULT_MIGRATIONS.upgrade(data)
            ir_version = parse_ir_version(data.get("ir_version"))
        except VersionError:
            ensure_supported(ir_version)

    source = _provenance_from_dict(data.get("source") or {})
    graph = _graph_from_dict(data["graph"])
    if not graph.provenance.application and source.application:
        graph.provenance = source
    return IRDocument(
        graph=graph,
        source=source,
        nodebridge_version=str(data.get("nodebridge_version", "")),
        ir_version=ir_version,
    )


def deserialize_graph(data: dict[str, Any]) -> IRGraph:
    """Deserialize a bare graph object or a full document."""
    if "graph" in data and "ir_version" in data:
        return deserialize_document(data).graph
    return _graph_from_dict(data)


def _graph_from_dict(data: dict[str, Any]) -> IRGraph:
    _require_fields(data, {"id", "name"}, what="graph")
    nodes = {}
    for raw_node in data.get("nodes") or []:
        node = _node_from_dict(raw_node)
        if node.id in nodes:
            raise SerializationError(f"Duplicate node id in document: {node.id}")
        nodes[node.id] = node
    connections = [
        _connection_from_dict(raw) for raw in data.get("connections") or []
    ]
    nested = {}
    for raw_graph in data.get("graphs") or []:
        child = _graph_from_dict(raw_graph)
        if child.id in nested:
            raise SerializationError(f"Duplicate nested graph id: {child.id}")
        nested[child.id] = child
    system_value = data.get("system", GraphSystem.UNKNOWN.value)
    try:
        system = GraphSystem(system_value)
    except ValueError:
        system = GraphSystem.UNKNOWN
    return IRGraph(
        id=str(data["id"]),
        name=str(data["name"]),
        system=system,
        nodes=nodes,
        connections=connections,
        graphs=nested,
        interface=_interface_from_dict(data.get("interface") or {}),
        metadata=_metadata_from_dict(data.get("metadata") or {}),
        provenance=_provenance_from_dict(data.get("provenance") or {}),
    )


def _node_from_dict(data: dict[str, Any]) -> IRNode:
    _require_fields(data, {"id", "operation"}, what="node")
    node = IRNode(
        id=str(data["id"]),
        operation=str(data["operation"]),
        metadata=_metadata_from_dict(data.get("metadata") or {}),
        nested_graph_id=_optional_str(data.get("nested_graph_id")),
    )
    for raw_socket in data.get("inputs") or []:
        node.add_socket(_socket_from_dict(raw_socket, default_direction=SocketDirection.INPUT))
    for raw_socket in data.get("outputs") or []:
        node.add_socket(
            _socket_from_dict(raw_socket, default_direction=SocketDirection.OUTPUT)
        )
    for raw_parameter in data.get("parameters") or []:
        parameter = _parameter_from_dict(raw_parameter)
        node.parameters[parameter.name] = parameter
    return node


def _socket_from_dict(
    data: dict[str, Any],
    *,
    default_direction: SocketDirection,
) -> IRSocket:
    _require_fields(data, {"id", "name", "data_type"}, what="socket")
    direction_value = data.get("direction", default_direction.value)
    domain_value = data.get("domain")
    return IRSocket(
        id=str(data["id"]),
        name=str(data["name"]),
        data_type=TypeRef.of(str(data["data_type"])),
        direction=SocketDirection(direction_value),
        default=data.get("default"),
        field_kind=FieldKind(data.get("field_kind", FieldKind.VALUE.value)),
        domain=GeometryDomain(domain_value) if domain_value else None,
        metadata=_metadata_from_dict(data.get("metadata") or {}),
    )


def _parameter_from_dict(data: dict[str, Any]) -> IRParameter:
    _require_fields(data, {"name", "data_type"}, what="parameter")
    return IRParameter(
        name=str(data["name"]),
        data_type=TypeRef.of(str(data["data_type"])),
        value=data.get("value"),
        metadata=dict(data.get("metadata") or {}),
    )


def _connection_from_dict(data: dict[str, Any]) -> IRConnection:
    _require_fields(
        data,
        {"id", "source_node", "source_socket", "target_node", "target_socket"},
        what="connection",
    )
    return IRConnection(
        id=str(data["id"]),
        source_node=str(data["source_node"]),
        source_socket=str(data["source_socket"]),
        target_node=str(data["target_node"]),
        target_socket=str(data["target_socket"]),
        metadata=_metadata_from_dict(data.get("metadata") or {}),
    )


def _interface_from_dict(data: dict[str, Any]) -> GraphInterface:
    interface = GraphInterface()
    for raw in data.get("inputs") or []:
        interface.add(_socket_from_dict(raw, default_direction=SocketDirection.INPUT))
    for raw in data.get("outputs") or []:
        interface.add(_socket_from_dict(raw, default_direction=SocketDirection.OUTPUT))
    return interface


def _metadata_from_dict(data: dict[str, Any]) -> Metadata:
    history = [
        TranslationEvent.from_dict(item)
        for item in data.get("history") or []
        if isinstance(item, dict)
    ]
    return Metadata(
        provenance=_provenance_from_dict(data.get("provenance") or {}),
        ui=_ui_from_dict(data.get("ui") or {}),
        mapping=_mapping_from_dict(data.get("mapping") or {}),
        extra=dict(data.get("extra") or {}),
        history=history,
    )


def _provenance_from_dict(data: dict[str, Any]) -> Provenance:
    return Provenance(
        application=str(data.get("application") or ""),
        application_version=str(data.get("application_version") or ""),
        graph_system=str(data.get("graph_system") or ""),
        original_type=str(data.get("original_type") or ""),
        original_name=str(data.get("original_name") or ""),
        original_label=str(data.get("original_label") or ""),
        original_id=str(data.get("original_id") or ""),
        extracted_at=str(data.get("extracted_at") or ""),
        extra=dict(data.get("extra") or {}),
    )


def _ui_from_dict(data: dict[str, Any]) -> UIHints:
    position = data.get("position")
    color = data.get("color")
    return UIHints(
        position=_as_float_pair(position),
        width=data.get("width"),
        label=str(data.get("label") or ""),
        muted=bool(data.get("muted", False)),
        frame_id=_optional_str(data.get("frame_id")),
        collapsed=bool(data.get("collapsed", False)),
        color=_as_float_triple(color),
    )


def _mapping_from_dict(data: dict[str, Any]) -> SourceMapping:
    return SourceMapping(
        source_node_id=str(data.get("source_node_id") or ""),
        ir_node_id=str(data.get("ir_node_id") or ""),
        target_nodes=[str(item) for item in data.get("target_nodes") or []],
        extra=dict(data.get("extra") or {}),
    )


def _require_fields(data: dict[str, Any], fields: set[str], *, what: str) -> None:
    if not isinstance(data, dict):
        raise SerializationError(f"{what} must be a JSON object")
    missing = fields - set(data)
    if missing:
        raise SerializationError(f"{what} is missing required fields: {sorted(missing)}")


def _optional_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _as_float_pair(value: Any) -> tuple[float, float] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise SerializationError("UI position must be a two-number array")
    return (float(value[0]), float(value[1]))


def _as_float_triple(value: Any) -> tuple[float, float, float] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise SerializationError("UI color must be a three-number array")
    return (float(value[0]), float(value[1]), float(value[2]))
