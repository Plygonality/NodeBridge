"""JSON serialization for IR documents.

Conversion lives here so core types stay format-agnostic. Output is
deterministic: object keys are sorted and collections are ordered by ID.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TextIO

from nodebridge.core.graph import GraphInterface, GraphSystem, IRGraph
from nodebridge.core.link import IRConnection
from nodebridge.core.metadata import Metadata, Provenance, SourceMapping, UIHints
from nodebridge.core.node import IRNode, IRParameter
from nodebridge.core.socket import IRSocket
from nodebridge.core.types import TypeRef
from nodebridge.core.values import JSONValue, normalize_value
from nodebridge.ir.schema import IRDocument
from nodebridge.ir.versioning import IR_VERSION, PACKAGE_VERSION


def serialize_document(document: IRDocument) -> dict[str, Any]:
    """Return a JSON-ready dict for *document*."""
    source = document.source
    if not source.application:
        source = document.graph.provenance
    return {
        "nodebridge_version": document.nodebridge_version or PACKAGE_VERSION,
        "ir_version": document.ir_version or IR_VERSION,
        "source": _provenance_to_dict(source),
        "graph": _graph_to_dict(document.graph),
    }


def serialize_graph(graph: IRGraph, *, source: Provenance | None = None) -> dict[str, Any]:
    """Wrap *graph* in a document dict."""
    document = IRDocument(graph=graph, source=source or graph.provenance)
    return serialize_document(document)


def dumps(document: IRDocument | IRGraph, *, indent: int = 2) -> str:
    """Serialize *document* to a formatted JSON string."""
    payload = (
        serialize_graph(document)
        if isinstance(document, IRGraph)
        else serialize_document(document)
    )
    return json.dumps(payload, indent=indent, sort_keys=True) + "\n"


def dump(document: IRDocument | IRGraph, destination: str | Path | TextIO) -> None:
    """Write JSON to a path or file object."""
    text = dumps(document)
    if isinstance(destination, (str, Path)):
        Path(destination).write_text(text, encoding="utf-8")
        return
    destination.write(text)


def _graph_to_dict(graph: IRGraph) -> dict[str, Any]:
    return {
        "id": graph.id,
        "name": graph.name,
        "system": graph.system.value if isinstance(graph.system, GraphSystem) else graph.system,
        "nodes": [_node_to_dict(graph.nodes[node_id]) for node_id in sorted(graph.nodes)],
        "connections": [
            _connection_to_dict(connection)
            for connection in sorted(graph.connections, key=lambda item: item.id)
        ],
        "graphs": [
            _graph_to_dict(graph.graphs[graph_id]) for graph_id in sorted(graph.graphs)
        ],
        "interface": _interface_to_dict(graph.interface),
        "metadata": _metadata_to_dict(graph.metadata),
        "provenance": _provenance_to_dict(graph.provenance),
    }


def _node_to_dict(node: IRNode) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": node.id,
        "operation": node.operation,
        "inputs": [
            _socket_to_dict(node.inputs[socket_id]) for socket_id in sorted(node.inputs)
        ],
        "outputs": [
            _socket_to_dict(node.outputs[socket_id]) for socket_id in sorted(node.outputs)
        ],
        "parameters": [
            _parameter_to_dict(node.parameters[name])
            for name in sorted(node.parameters)
        ],
        "metadata": _metadata_to_dict(node.metadata),
    }
    if node.nested_graph_id is not None:
        payload["nested_graph_id"] = node.nested_graph_id
    return payload


def _socket_to_dict(socket: IRSocket) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": socket.id,
        "name": socket.name,
        "data_type": _type_to_value(socket.data_type),
        "direction": socket.direction.value,
        "default": normalize_value(socket.default),
        "field_kind": socket.field_kind.value,
        "metadata": _metadata_to_dict(socket.metadata),
    }
    if socket.domain is not None:
        payload["domain"] = socket.domain.value
    return payload


def _parameter_to_dict(parameter: IRParameter) -> dict[str, Any]:
    return {
        "name": parameter.name,
        "data_type": _type_to_value(parameter.data_type),
        "value": normalize_value(parameter.value),
        "metadata": dict(parameter.metadata),
    }


def _connection_to_dict(connection: IRConnection) -> dict[str, Any]:
    return {
        "id": connection.id,
        "source_node": connection.source_node,
        "source_socket": connection.source_socket,
        "target_node": connection.target_node,
        "target_socket": connection.target_socket,
        "metadata": _metadata_to_dict(connection.metadata),
    }


def _interface_to_dict(interface: GraphInterface) -> dict[str, Any]:
    return {
        "inputs": [
            _socket_to_dict(interface.inputs[socket_id])
            for socket_id in sorted(interface.inputs)
        ],
        "outputs": [
            _socket_to_dict(interface.outputs[socket_id])
            for socket_id in sorted(interface.outputs)
        ],
    }


def _metadata_to_dict(metadata: Metadata) -> dict[str, Any]:
    return {
        "provenance": _provenance_to_dict(metadata.provenance),
        "ui": _ui_to_dict(metadata.ui),
        "mapping": _mapping_to_dict(metadata.mapping),
        "extra": dict(metadata.extra),
    }


def _provenance_to_dict(provenance: Provenance) -> dict[str, Any]:
    return {
        "application": provenance.application,
        "application_version": provenance.application_version,
        "graph_system": provenance.graph_system,
        "original_type": provenance.original_type,
        "original_name": provenance.original_name,
        "original_label": provenance.original_label,
        "original_id": provenance.original_id,
        "extra": dict(provenance.extra),
    }


def _ui_to_dict(ui: UIHints) -> dict[str, Any]:
    return {
        "position": list(ui.position) if ui.position is not None else None,
        "width": ui.width,
        "label": ui.label,
        "muted": ui.muted,
        "frame_id": ui.frame_id,
        "collapsed": ui.collapsed,
        "color": list(ui.color) if ui.color is not None else None,
    }


def _mapping_to_dict(mapping: SourceMapping) -> dict[str, Any]:
    return {
        "source_node_id": mapping.source_node_id,
        "ir_node_id": mapping.ir_node_id,
        "target_nodes": list(mapping.target_nodes),
        "extra": dict(mapping.extra),
    }


def _type_to_value(type_ref: TypeRef) -> str:
    return type_ref.name


def empty_extra() -> dict[str, JSONValue]:
    """Placeholder used by tests when comparing serialized extras."""
    return {}
