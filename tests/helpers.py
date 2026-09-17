"""Shared graph fixtures for tests."""

from __future__ import annotations

from nodebridge.core.graph import GraphBuilder, GraphSystem
from nodebridge.core.metadata import Provenance, UIHints
from nodebridge.core.socket import SocketDirection
from nodebridge.core.types import DataType
from nodebridge.hosts.native import NativeGraph, NativeLink, NativeNode, NativeSocket


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


def make_scatter_ir_graph(*, application: str = "blender", graph_system: str = "geometry_nodes") -> GraphBuilder:
    """Mesh → distribute points → random scale → instance → realize."""
    builder = GraphBuilder(
        name="scatter",
        system=GraphSystem.GEOMETRY,
        provenance=Provenance(application=application, graph_system=graph_system),
    )
    group_in = builder.node("graph.input", node_id="node_in")
    geo_out = builder.output(group_in, "geometry", DataType.GEOMETRY, socket_id="in_geo")

    distribute = builder.node("points.distribute", node_id="node_dist")
    dist_in = builder.input(distribute, "geometry", DataType.GEOMETRY, socket_id="dist_in")
    dist_out = builder.output(distribute, "points", DataType.POINTS, socket_id="dist_out")
    builder.parameter(distribute, "density", 10.0, DataType.FLOAT)

    random = builder.node("random.vector", node_id="node_rand")
    builder.input(random, "min", DataType.VECTOR3, default=(0.5, 0.5, 0.5), socket_id="rand_min")
    builder.input(random, "max", DataType.VECTOR3, default=(1.5, 1.5, 1.5), socket_id="rand_max")
    rand_out = builder.output(random, "vector", DataType.VECTOR3, socket_id="rand_out")

    cube = builder.node("geometry.primitive", node_id="node_cube")
    builder.parameter(cube, "primitive", "cube", DataType.STRING)
    cube_out = builder.output(cube, "geometry", DataType.GEOMETRY, socket_id="cube_out")

    instance = builder.node("geometry.instance", node_id="node_inst")
    inst_pts = builder.input(instance, "points", DataType.POINTS, socket_id="inst_pts")
    inst_geo = builder.input(instance, "instance", DataType.GEOMETRY, socket_id="inst_geo")
    inst_scale = builder.input(instance, "scale", DataType.VECTOR3, socket_id="inst_scale")
    inst_out = builder.output(instance, "instances", DataType.INSTANCES, socket_id="inst_out")

    realize = builder.node("geometry.realize_instances", node_id="node_real")
    real_in = builder.input(realize, "geometry", DataType.GEOMETRY, socket_id="real_in")
    real_out = builder.output(realize, "geometry", DataType.GEOMETRY, socket_id="real_out")

    group_out = builder.node("graph.output", node_id="node_out")
    out_geo = builder.input(group_out, "geometry", DataType.GEOMETRY, socket_id="out_geo")

    builder.connect(group_in, geo_out, distribute, dist_in, connection_id="link_in")
    builder.connect(distribute, dist_out, instance, inst_pts, connection_id="link_pts")
    builder.connect(cube, cube_out, instance, inst_geo, connection_id="link_cube")
    builder.connect(random, rand_out, instance, inst_scale, connection_id="link_scale")
    builder.connect(instance, inst_out, realize, real_in, connection_id="link_inst")
    builder.connect(realize, real_out, group_out, out_geo, connection_id="link_out")
    return builder


def make_blender_scatter_native() -> NativeGraph:
    """Blender Geometry Nodes scattering fixture."""
    return NativeGraph(
        host="blender",
        system="geometry_nodes",
        name="scatter",
        nodes=[
            NativeNode(
                id="group_input",
                type="NodeGroupInput",
                outputs=[NativeSocket(name="Geometry", data_type="geometry")],
            ),
            NativeNode(
                id="distribute",
                type="GeometryNodeDistributePointsOnFaces",
                inputs=[
                    NativeSocket(name="Mesh", data_type="geometry"),
                    NativeSocket(name="Density", data_type="float", default=10.0),
                ],
                outputs=[NativeSocket(name="Points", data_type="points")],
                parameters={"density": 10.0, "seed": 0},
            ),
            NativeNode(
                id="random",
                type="FunctionNodeRandomValue",
                inputs=[
                    NativeSocket(name="Min", data_type="vector3", default=[0.5, 0.5, 0.5]),
                    NativeSocket(name="Max", data_type="vector3", default=[1.5, 1.5, 1.5]),
                ],
                outputs=[NativeSocket(name="Value", data_type="vector3")],
                parameters={"data_type": "FLOAT_VECTOR", "seed": 1},
            ),
            NativeNode(
                id="cube",
                type="GeometryNodeMeshCube",
                outputs=[NativeSocket(name="Mesh", data_type="geometry")],
                parameters={"size": 1.0},
            ),
            NativeNode(
                id="instance",
                type="GeometryNodeInstanceOnPoints",
                inputs=[
                    NativeSocket(name="Points", data_type="points"),
                    NativeSocket(name="Instance", data_type="geometry"),
                    NativeSocket(name="Scale", data_type="vector3"),
                ],
                outputs=[NativeSocket(name="Instances", data_type="instances")],
            ),
            NativeNode(
                id="realize",
                type="GeometryNodeRealizeInstances",
                inputs=[NativeSocket(name="Geometry", data_type="geometry")],
                outputs=[NativeSocket(name="Geometry", data_type="geometry")],
            ),
            NativeNode(
                id="group_output",
                type="NodeGroupOutput",
                inputs=[NativeSocket(name="Geometry", data_type="geometry")],
            ),
        ],
        links=[
            NativeLink("group_input", "Geometry", "distribute", "Mesh"),
            NativeLink("distribute", "Points", "instance", "Points"),
            NativeLink("cube", "Mesh", "instance", "Instance"),
            NativeLink("random", "Value", "instance", "Scale"),
            NativeLink("instance", "Instances", "realize", "Geometry"),
            NativeLink("realize", "Geometry", "group_output", "Geometry"),
        ],
    )


def make_houdini_scatter_native() -> NativeGraph:
    """Houdini SOP scattering fixture."""
    return NativeGraph(
        host="houdini",
        system="sop",
        name="scatter",
        nodes=[
            NativeNode(id="geo_in", type="null", parameters={"role": "input"}, outputs=[NativeSocket(name="output0")]),
            NativeNode(
                id="scatter",
                type="scatter",
                inputs=[NativeSocket(name="input0")],
                outputs=[NativeSocket(name="output0")],
                parameters={"npts": 100, "seed": 0},
            ),
            NativeNode(
                id="pscale",
                type="attribrandomize",
                inputs=[NativeSocket(name="input0")],
                outputs=[NativeSocket(name="output0")],
                parameters={"attrname": "pscale", "type": "vector"},
            ),
            NativeNode(
                id="box",
                type="box",
                outputs=[NativeSocket(name="output0")],
            ),
            NativeNode(
                id="copy",
                type="copytopoints",
                inputs=[NativeSocket(name="input0"), NativeSocket(name="input1")],
                outputs=[NativeSocket(name="output0")],
            ),
            NativeNode(
                id="unpack",
                type="unpack",
                inputs=[NativeSocket(name="input0")],
                outputs=[NativeSocket(name="output0")],
            ),
            NativeNode(
                id="out",
                type="null",
                parameters={"role": "output"},
                inputs=[NativeSocket(name="input0")],
            ),
        ],
        links=[
            NativeLink("geo_in", "output0", "scatter", "input0"),
            NativeLink("scatter", "output0", "pscale", "input0"),
            NativeLink("box", "output0", "copy", "input0"),
            NativeLink("pscale", "output0", "copy", "input1"),
            NativeLink("copy", "output0", "unpack", "input0"),
            NativeLink("unpack", "output0", "out", "input0"),
        ],
    )
