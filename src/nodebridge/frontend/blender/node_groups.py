"""Nested Blender node groups become semantic subgraphs."""

from __future__ import annotations

from nodebridge.frontend.blender.lower import finish, lower_tree
from nodebridge.ir.graph import GraphNode, NodeTree
from nodebridge.ir.operations import field_port, geometry_port
from nodebridge.ir.semantic import Operation, OperationKind
from nodebridge.ir.types import DataType

_GEOMETRY = {DataType.GEOMETRY, DataType.MESH, DataType.CURVE, DataType.POINTS, DataType.INSTANCES}


def lower_group(node: GraphNode, tree: NodeTree):
    """Lower a group node. The nested tree was parsed with the parent."""

    if node.nested is None:
        operation = Operation(
            id=node.id,
            kind=OperationKind.UNSUPPORTED,
            name=node.label or node.name,
            parameters={
                "source_type": node.node_type,
                "reason": "Node group has no internal tree.",
            },
            notes=["Node group has no internal tree."],
        )
        return finish(node, operation, {}, {})

    subgraph = lower_tree(node.nested)
    inputs = {}
    outputs = {}
    input_names = {}
    output_names = {}
    for socket in node.inputs:
        port = _port(socket.identifier, socket.data_type, socket.is_field)
        inputs[socket.identifier] = port
        input_names[socket.identifier] = socket.identifier
    for socket in node.outputs:
        port = _port(socket.identifier, socket.data_type, socket.is_field)
        outputs[socket.identifier] = port
        output_names[socket.identifier] = socket.identifier
    operation = Operation(
        id=node.id,
        kind=OperationKind.SUBGRAPH,
        name=node.label or node.name or subgraph.name,
        inputs=inputs,
        outputs=outputs,
        subgraph=subgraph,
        parameters={"group": subgraph.name},
    )
    return finish(node, operation, input_names, output_names)


def _port(identifier: str, data_type: DataType, is_field: bool):
    if data_type in _GEOMETRY and not is_field:
        return geometry_port(identifier, data_type)
    return field_port(identifier, data_type)
