"""Lower graph IR into the semantic IR.

Several source nodes stay several semantic operations here. Pattern fusion
that combines them lives in :mod:`nodebridge.compiler.rules`.
"""

from __future__ import annotations

from nodebridge.core.graph import GraphSystem
from nodebridge.hosts.blender.mappings import resolve_blender_node
from nodebridge.hosts.extract import extract_native
from nodebridge.hosts.native import NativeGraph, NativeLink, NativeNode, NativeSocket
from nodebridge.ir.graph_ir import NodeTree
from nodebridge.ir.schema import IRDocument

_SYSTEMS = {
    "geometry_nodes": ("geometry_nodes", GraphSystem.GEOMETRY),
    "geometry": ("geometry_nodes", GraphSystem.GEOMETRY),
    "shader": ("shader", GraphSystem.SHADER),
    "shader_nodes": ("shader", GraphSystem.SHADER),
    "compositor": ("compositor", GraphSystem.COMPOSITOR),
    "compositor_nodes": ("compositor", GraphSystem.COMPOSITOR),
}


def semanticize(tree: NodeTree) -> IRDocument:
    """Convert a :class:`NodeTree` into a semantic :class:`IRDocument`."""
    graph_system, _enum = _SYSTEMS.get(tree.system, ("geometry_nodes", GraphSystem.GEOMETRY))
    native = _to_native(tree)
    document = extract_native(
        native,
        resolve=resolve_blender_node,
        application="blender",
        graph_system=graph_system,
    )
    for group in tree.groups.values():
        child = semanticize(group)
        child.graph.id = group.id
        document.graph.add_graph(child.graph)
    return document


def _to_native(tree: NodeTree) -> NativeGraph:
    nodes: list[NativeNode] = []
    for node in tree.nodes.values():
        parameters = {item.name: item.value for item in node.parameters}
        if node.nested_tree_id:
            parameters["nested_graph_id"] = node.nested_tree_id
        nodes.append(
            NativeNode(
                id=node.id,
                type=node.type_name,
                name=node.label or node.name or node.type_name,
                inputs=[
                    NativeSocket(name=socket.name, data_type=socket.data_type, default=socket.default)
                    for socket in node.inputs
                ],
                outputs=[
                    NativeSocket(name=socket.name, data_type=socket.data_type, default=socket.default)
                    for socket in node.outputs
                ],
                parameters=parameters,
                position=node.location,
                metadata={"muted": node.muted, **node.metadata},
            )
        )
    return NativeGraph(
        host="blender",
        system=tree.system,
        name=tree.name,
        nodes=nodes,
        links=[
            NativeLink(
                source_node=edge.source_node,
                source_socket=edge.source_socket,
                target_node=edge.target_node,
                target_socket=edge.target_socket,
            )
            for edge in tree.edges
        ],
        interface_inputs=[
            NativeSocket(name=socket.name, data_type=socket.data_type, default=socket.default)
            for socket in tree.interface_inputs
        ],
        interface_outputs=[
            NativeSocket(name=socket.name, data_type=socket.data_type, default=socket.default)
            for socket in tree.interface_outputs
        ],
        metadata=dict(tree.metadata),
    )
