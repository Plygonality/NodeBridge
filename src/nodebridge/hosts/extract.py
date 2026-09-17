"""Generic native-graph → IR extraction.

Host frontends supply a native-type resolver. This module never imports a
DCC SDK and never defines canonical semantics — it only applies the host's
mapping table.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from nodebridge.core.graph import GraphBuilder, GraphSystem
from nodebridge.core.metadata import Provenance, TranslationEvent, UIHints
from nodebridge.core.node import IRNode
from nodebridge.core.socket import SocketDirection
from nodebridge.core.types import DataType
from nodebridge.hosts.native import NativeGraph, NativeNode
from nodebridge.ir.schema import IRDocument

Resolver = Callable[[NativeNode, NativeGraph], tuple[str, dict[str, object]]]


def extract_native(
    native: NativeGraph,
    *,
    resolve: Resolver,
    application: str,
    graph_system: str,
    default_data_type: str = "geometry",
) -> IRDocument:
    """Translate a native construction/extraction graph into canonical IR."""
    provenance = Provenance(
        application=application,
        application_version=str(native.metadata.get("application_version") or ""),
        graph_system=graph_system,
        extracted_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        extra={"native_name": native.name, "native_system": native.system},
    )
    builder = GraphBuilder(
        name=native.name or "untitled",
        system=GraphSystem.GEOMETRY,
        provenance=provenance,
    )
    native_to_ir: dict[str, IRNode] = {}
    socket_ids: dict[tuple[str, str, str], str] = {}

    for native_node in native.nodes:
        operation, extras = resolve(native_node, native)
        ir_node = builder.node(operation, node_id=_safe_id(native_node.id))
        ir_node.metadata.provenance.application = application
        ir_node.metadata.provenance.graph_system = graph_system
        ir_node.metadata.provenance.original_type = native_node.type
        ir_node.metadata.provenance.original_name = native_node.name or native_node.type
        ir_node.metadata.provenance.original_id = native_node.id
        ir_node.metadata.mapping.source_node_id = native_node.id
        ir_node.metadata.mapping.ir_node_id = ir_node.id
        if native_node.position:
            ir_node.metadata.ui = UIHints(position=native_node.position)
        ir_node.metadata.history.append(
            TranslationEvent(
                stage="extract",
                host=application,
                native_type=native_node.type,
                note="Mapped native node onto a semantic operation.",
            )
        )
        for parameter_name, parameter_value in native_node.parameters.items():
            ir_node.set_parameter(parameter_name, parameter_value)
        for extra_name, extra_value in extras.items():
            if extra_name == "parameters" and isinstance(extra_value, dict):
                for key, value in extra_value.items():
                    ir_node.set_parameter(str(key), value)
            elif extra_name == "nested_graph_id":
                ir_node.nested_graph_id = str(extra_value)
        _add_ports(builder, ir_node, native_node, socket_ids, default_data_type)
        native_to_ir[native_node.id] = ir_node

    for index, link in enumerate(native.links, start=1):
        source = native_to_ir.get(link.source_node)
        target = native_to_ir.get(link.target_node)
        if source is None or target is None:
            continue
        source_socket = socket_ids.get((link.source_node, "output", link.source_socket))
        target_socket = socket_ids.get((link.target_node, "input", link.target_socket))
        if source_socket is None:
            source_socket = _ensure_named_socket(
                builder, source, link.source_socket, SocketDirection.OUTPUT, default_data_type
            )
            socket_ids[(link.source_node, "output", link.source_socket)] = source_socket
        if target_socket is None:
            target_socket = _ensure_named_socket(
                builder, target, link.target_socket, SocketDirection.INPUT, default_data_type
            )
            socket_ids[(link.target_node, "input", link.target_socket)] = target_socket
        builder.connect(
            source,
            source_socket,
            target,
            target_socket,
            connection_id=_safe_id(f"link_{index}"),
        )

    for socket in native.interface_inputs:
        builder.expose(
            socket.name,
            _type(socket.data_type, default_data_type),
            SocketDirection.INPUT,
            default=socket.default,
        )
    for socket in native.interface_outputs:
        builder.expose(
            socket.name,
            _type(socket.data_type, default_data_type),
            SocketDirection.OUTPUT,
        )
    return IRDocument(graph=builder.graph, source=provenance)


def _add_ports(
    builder: GraphBuilder,
    ir_node: IRNode,
    native_node: NativeNode,
    socket_ids: dict[tuple[str, str, str], str],
    default_data_type: str,
) -> None:
    for native_socket in native_node.inputs:
        socket = builder.input(
            ir_node,
            _semantic_socket_name(ir_node.operation, native_socket.name, SocketDirection.INPUT),
            _type(native_socket.data_type, default_data_type),
            default=native_socket.default,
        )
        socket_ids[(native_node.id, "input", native_socket.name)] = socket.id
    for native_socket in native_node.outputs:
        socket = builder.output(
            ir_node,
            _semantic_socket_name(ir_node.operation, native_socket.name, SocketDirection.OUTPUT),
            _type(native_socket.data_type, default_data_type),
        )
        socket_ids[(native_node.id, "output", native_socket.name)] = socket.id


def _ensure_named_socket(
    builder: GraphBuilder,
    node: IRNode,
    native_name: str,
    direction: SocketDirection,
    default_data_type: str,
) -> str:
    semantic = _semantic_socket_name(node.operation, native_name, direction)
    try:
        return node.socket_by_name(semantic, direction).id
    except KeyError:
        try:
            return node.socket_by_name(native_name, direction).id
        except KeyError:
            pass
    if direction is SocketDirection.INPUT:
        return builder.input(node, semantic, default_data_type).id
    return builder.output(node, semantic, default_data_type).id


def _semantic_socket_name(
    operation: str, native_name: str, direction: SocketDirection
) -> str:
    """Map common host socket labels onto canonical IR names."""
    key = native_name.strip().lower().replace(" ", "_")
    aliases = {
        "geo": "geometry",
        "mesh": "geometry",
        "geometry": "geometry",
        "in": "geometry",
        "input": "geometry",
        "out": "geometry" if direction is SocketDirection.OUTPUT else "geometry",
        "output": "geometry",
        "points": "points",
        "point": "points",
        "instance": "instance",
        "instances": "instances",
        "scale": "scale",
        "rotation": "rotation",
        "translation": "translation",
        "location": "translation",
        "value": "value",
        "vector": "vector",
        "a": "a",
        "b": "b",
        "min": "min",
        "max": "max",
        "seed": "seed",
        "id": "id",
        "density": "density",
        "selection": "selection",
        "true": "true",
        "false": "false",
        "surface": "geometry",
        "template": "instance",
    }
    if operation == "geometry.instance":
        if key in {"points", "point", "in", "input"}:
            return "points"
        if key in {"instance", "instances", "geometry", "template", "source"}:
            return "instance"
        if key in {"scale", "pscale"}:
            return "scale"
        if key in {"out", "output", "instances"}:
            return "instances"
    if operation == "points.distribute":
        if key in {"mesh", "geometry", "surface", "in"}:
            return "geometry"
        if key in {"points", "out", "output"}:
            return "points"
        if key == "density":
            return "density"
    if operation in {"graph.input", "graph.output", "geometry.transform", "geometry.join"}:
        if key in {"geo", "mesh", "in", "out", "input", "output", "geometry"}:
            return "geometry"
    if operation.startswith("math.") or operation.startswith("random.float"):
        if key in {"value", "result", "out", "output"}:
            return "value"
    if operation.startswith("vector.") or operation == "random.vector":
        if key in {"vector", "out", "output", "result"}:
            return "vector"
        if key == "scale":
            return "scale"
    return aliases.get(key, native_name)


def _type(name: str, default: str) -> str | DataType:
    parsed = DataType.try_parse(name.lower()) if name else None
    if parsed is not None:
        return parsed
    aliases = {
        "GEOMETRY": DataType.GEOMETRY,
        "VALUE": DataType.FLOAT,
        "VECTOR": DataType.VECTOR3,
        "INT": DataType.INTEGER,
        "BOOLEAN": DataType.BOOLEAN,
        "STRING": DataType.STRING,
        "RGBA": DataType.COLOR,
        "OBJECT": DataType.OBJECT,
        "COLLECTION": DataType.COLLECTION,
        "MATERIAL": DataType.MATERIAL,
        "ROTATION": DataType.VECTOR3,
        "MATRIX": DataType.MATRIX,
    }
    return aliases.get(name.upper(), default)


def _safe_id(value: str) -> str:
    cleaned = []
    for char in value:
        if char.isalnum() or char in {"_", ".", "-"}:
            cleaned.append(char)
        else:
            cleaned.append("_")
    text = "".join(cleaned)
    if not text or not text[0].isalpha():
        text = f"n_{text}"
    return text
