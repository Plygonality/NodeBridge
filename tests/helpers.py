"""Shared graph fixtures for Milestone 1 tests."""

from __future__ import annotations

from nodebridge.core.graph import GraphBuilder, GraphSystem
from nodebridge.core.metadata import Provenance, UIHints
from nodebridge.core.socket import SocketDirection
from nodebridge.core.types import DataType


def make_math_add_graph() -> GraphBuilder:
    """Two constants added together. Used as the smallest IR fixture."""
    builder = GraphBuilder(
        name="math_add",
        system=GraphSystem.GEOMETRY,
        provenance=Provenance(application="blender", graph_system="geometry"),
    )
    add = builder.node("math.add", node_id="node_add")
    builder.input(add, "a", DataType.FLOAT, default=1.0, socket_id="sock_a")
    builder.input(add, "b", DataType.FLOAT, default=2.0, socket_id="sock_b")
    builder.output(add, "value", DataType.FLOAT, socket_id="sock_out")
    add.metadata.provenance.original_type = "ShaderNodeMath"
    add.metadata.provenance.original_name = "Math"
    add.metadata.ui = UIHints(position=(120.0, 40.0), label="Add")
    builder.parameter(add, "operation", "ADD", DataType.STRING)
    return builder


def make_transform_graph() -> GraphBuilder:
    """Geometry in → transform → geometry out, plus a vector add."""
    builder = GraphBuilder(
        name="transform_geometry",
        system=GraphSystem.GEOMETRY,
        provenance=Provenance(
            application="blender",
            application_version="4.2",
            graph_system="geometry",
        ),
    )
    group_in = builder.node("graph.input", node_id="node_in")
    geo_out = builder.output(group_in, "geometry", DataType.GEOMETRY, socket_id="in_geo")

    offset = builder.node("vector.add", node_id="node_offset")
    builder.input(
        offset, "a", DataType.VECTOR3, default=(0.0, 0.0, 1.0), socket_id="off_a"
    )
    builder.input(
        offset, "b", DataType.VECTOR3, default=(0.0, 0.0, 0.0), socket_id="off_b"
    )
    off_out = builder.output(offset, "vector", DataType.VECTOR3, socket_id="off_out")

    xform = builder.node("geometry.transform", node_id="node_xform")
    xform_geo = builder.input(xform, "geometry", DataType.GEOMETRY, socket_id="xf_geo")
    xform_t = builder.input(
        xform, "translation", DataType.VECTOR3, default=(0.0, 0.0, 0.0), socket_id="xf_t"
    )
    xform_out = builder.output(xform, "geometry", DataType.GEOMETRY, socket_id="xf_out")
    xform.metadata.provenance.original_type = "GeometryNodeTransform"
    xform.metadata.provenance.original_name = "Transform Geometry"
    xform.metadata.mapping.source_node_id = "bpy_node_xform"

    group_out = builder.node("graph.output", node_id="node_out")
    out_geo = builder.input(group_out, "geometry", DataType.GEOMETRY, socket_id="out_geo")

    builder.connect(group_in, geo_out, xform, xform_geo, connection_id="link_geo_in")
    builder.connect(offset, off_out, xform, xform_t, connection_id="link_offset")
    builder.connect(xform, xform_out, group_out, out_geo, connection_id="link_geo_out")

    builder.expose("geometry", DataType.GEOMETRY, SocketDirection.INPUT, socket_id="iface_in")
    builder.expose("geometry", DataType.GEOMETRY, SocketDirection.OUTPUT, socket_id="iface_out")
    return builder
