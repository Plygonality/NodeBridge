"""Product tests for the compiler slice: graph IR, rewrites, and generated code."""

from __future__ import annotations

import ast

from nodebridge.addon.workflow import TranslateOptions, analyze_source, generate_source
from nodebridge.common.coordinates import convert_position
from nodebridge.common.random import random_unit
from nodebridge.common.units import convert_angle, convert_length
from nodebridge.compiler.dependencies import analyze_dependencies
from nodebridge.compiler.rules import SpatialNoiseMaskPass
from nodebridge.core.graph import IRGraph
from nodebridge.core.link import IRConnection
from nodebridge.core.node import IRNode
from nodebridge.core.socket import IRSocket
from nodebridge.core.types import DataType
from nodebridge.frontend.blender.context import infer_source
from nodebridge.ir.graph_ir import NodeTree


class Socket:
    def __init__(self, name, data_type="GEOMETRY", default=None):
        self.name = name
        self.type = data_type
        self.bl_idname = data_type
        self.default_value = default


class Node:
    def __init__(self, name, bl_idname, inputs=None, outputs=None, **params):
        self.name = name
        self.bl_idname = bl_idname
        self.label = params.pop("label", name)
        self.inputs = inputs or []
        self.outputs = outputs or []
        self.location = (10.0, 20.0)
        self.mute = False
        self.node_tree = params.pop("node_tree", None)
        for key, value in params.items():
            setattr(self, key, value)


class Link:
    def __init__(self, source, source_socket, target, target_socket):
        self.from_node = source
        self.from_socket = source_socket
        self.to_node = target
        self.to_socket = target_socket


class Tree:
    def __init__(self, name, nodes, links, bl_idname="GeometryNodeTree", interface=None):
        self.name = name
        self.bl_idname = bl_idname
        self.nodes = nodes
        self.links = links
        self.interface = interface


def _scatter_tree():
    cube = Node("Cube", "GeometryNodeMeshCube", outputs=[Socket("Mesh")])
    scatter = Node(
        "Scatter Buildings",
        "GeometryNodeDistributePointsOnFaces",
        inputs=[Socket("Mesh"), Socket("Density", "FLOAT", 12.5), Socket("Seed", "INT", 3)],
        outputs=[Socket("Points")],
    )
    instance = Node(
        "Instance",
        "GeometryNodeInstanceOnPoints",
        inputs=[Socket("Points"), Socket("Instance"), Socket("Scale", "VECTOR", [1.0, 1.0, 1.0])],
        outputs=[Socket("Instances")],
    )
    realize = Node(
        "Realize",
        "GeometryNodeRealizeInstances",
        inputs=[Socket("Geometry")],
        outputs=[Socket("Geometry")],
    )
    output = Node("Group Output", "NodeGroupOutput", inputs=[Socket("Geometry")])
    links = [
        Link(cube, cube.outputs[0], scatter, scatter.inputs[0]),
        Link(scatter, scatter.outputs[0], instance, instance.inputs[0]),
        Link(cube, cube.outputs[0], instance, instance.inputs[1]),
        Link(instance, instance.outputs[0], realize, realize.inputs[0]),
        Link(realize, realize.outputs[0], output, output.inputs[0]),
    ]
    return Tree("BuildingGenerator", [cube, scatter, instance, realize, output], links)


def test_scatter_generates_houdini_sop_network() -> None:
    result = generate_source(_scatter_tree(), system="geometry_nodes", options=TranslateOptions())
    ast.parse(result.code)
    assert "import hou" in result.code
    assert "parent.createNode('geo', name)" in result.code
    assert "name = 'buildinggenerator'" in result.code
    assert "_create(geo, 'box', 'cube')" in result.code
    assert "_create(geo, 'scatter', 'scatter_buildings')" in result.code
    assert "_create(geo, 'copytopoints', 'instance')" in result.code
    assert "setDisplayFlag(True)" in result.code
    assert "setRenderFlag(True)" in result.code
    assert "moveToGoodPosition()" in result.code
    assert "layoutChildren()" in result.code
    assert "npts" in result.code
    assert result.counts["unsupported"] == 0
    assert result.counts["equivalent"] >= 1
    assert "EXACT:" in result.report
    assert "semantically equivalent" in result.report
    assert "for child in geo.children()" not in result.code or "list(geo.children())" in result.code


def test_exact_only_keeps_unsupported_visible() -> None:
    options = TranslateOptions(strictness="exact_only")
    result = generate_source(_scatter_tree(), system="geometry_nodes", options=options)
    ast.parse(result.code)
    assert "_create(geo, 'scatter'" not in result.code
    assert "EQUIVALENT" in result.code
    assert "Scatter Buildings" in result.report or "points.distribute" in result.report or "GeometryNodeDistributePointsOnFaces" in result.report


def test_nested_group_is_preserved() -> None:
    inner_in = Node("Group Input", "NodeGroupInput", outputs=[Socket("Geometry")])
    inner_out = Node("Group Output", "NodeGroupOutput", inputs=[Socket("Geometry")])
    inner = Tree("Floor", [inner_in, inner_out], [Link(inner_in, inner_in.outputs[0], inner_out, inner_out.inputs[0])])
    group = Node("Floor Group", "GeometryNodeGroup", inputs=[Socket("Geometry")], outputs=[Socket("Geometry")], node_tree=inner)
    output = Node("Group Output", "NodeGroupOutput", inputs=[Socket("Geometry")])
    tree = Tree("Building", [group, output], [Link(group, group.outputs[0], output, output.inputs[0])])
    result = analyze_source(tree, system="geometry_nodes", options=TranslateOptions())
    assert result.tree is not None
    assert result.tree.groups
    assert result.document is not None
    assert result.document.graph.graphs


def test_shader_and_compositor_targets() -> None:
    noise = Node("Noise", "ShaderNodeTexNoise", outputs=[Socket("Fac", "VALUE")])
    bsdf = Node(
        "Principled",
        "ShaderNodeBsdfPrincipled",
        inputs=[Socket("Base Color", "RGBA"), Socket("Roughness", "VALUE")],
        outputs=[Socket("BSDF", "SHADER")],
    )
    output = Node("Material Output", "ShaderNodeOutputMaterial", inputs=[Socket("Surface", "SHADER")])
    shader = Tree(
        "Facade",
        [noise, bsdf, output],
        [Link(noise, noise.outputs[0], bsdf, bsdf.inputs[1]), Link(bsdf, bsdf.outputs[0], output, output.inputs[0])],
        bl_idname="ShaderNodeTree",
    )
    houdini = generate_source(shader, system="shader", options=TranslateOptions())
    unreal = generate_source(shader, system="shader", options=TranslateOptions(target="unreal"))
    ast.parse(houdini.code)
    ast.parse(unreal.code)
    assert "materialbuilder" in houdini.code
    assert "mtlxstandard_surface" in houdini.code
    assert "MaterialExpressionNoise" in unreal.code
    assert "MaterialEditingLibrary" in unreal.code

    render = Node("Render Layers", "CompositorNodeRLayers", outputs=[Socket("Image", "RGBA")])
    glare = Node("Glare", "CompositorNodeGlare", inputs=[Socket("Image", "RGBA")], outputs=[Socket("Image", "RGBA")])
    color = Node(
        "Color Balance",
        "CompositorNodeColorBalance",
        inputs=[Socket("Image", "RGBA")],
        outputs=[Socket("Image", "RGBA")],
    )
    mask = Node("Ellipse Mask", "CompositorNodeEllipseMask", outputs=[Socket("Mask", "VALUE")])
    composite = Node("Composite", "CompositorNodeComposite", inputs=[Socket("Image", "RGBA")])
    comp = Tree(
        "Grade",
        [render, glare, color, mask, composite],
        [
            Link(render, render.outputs[0], glare, glare.inputs[0]),
            Link(glare, glare.outputs[0], color, color.inputs[0]),
            Link(color, color.outputs[0], composite, composite.inputs[0]),
        ],
        bl_idname="CompositorNodeTree",
    )
    cop = generate_source(comp, system="compositor", options=TranslateOptions())
    ue = generate_source(comp, system="compositor", options=TranslateOptions(target="unreal"))
    ast.parse(cop.code)
    ast.parse(ue.code)
    assert "colorcorrect" in cop.code
    assert "UNSUPPORTED" in cop.code
    assert "Ellipse Mask" in cop.code or "compositor.mask" in cop.report
    assert "UNSUPPORTED as a native graph" in ue.code
    assert "raise RuntimeError" in ue.code


def test_unreal_pcg_script_checks_public_api() -> None:
    result = generate_source(_scatter_tree(), system="geometry_nodes", options=TranslateOptions(target="unreal"))
    ast.parse(result.code)
    assert "PCGGraphFactory" in result.code
    assert "add_node_of_type" in result.code
    assert "unreal.PCGSurfaceSamplerSettings" in result.code
    assert "does not guess a private graph API" in result.code
    assert result.counts["unsupported"] == 0 or "UNSUPPORTED" in result.report


def test_graph_ir_roundtrip_and_cycles() -> None:
    result = analyze_source(_scatter_tree(), system="geometry_nodes", options=TranslateOptions())
    assert result.tree is not None
    restored = NodeTree.from_dict(result.tree.as_dict())
    assert restored.name == "BuildingGenerator"
    assert len(restored.nodes) == 5
    report = analyze_dependencies(restored)
    assert report.acyclic
    assert report.order[0] == "Cube"
    a = restored.nodes["Cube"]
    b = restored.nodes["Scatter_Buildings"]
    restored.edges.append(
        type(restored.edges[0])(
            id="edge_cycle",
            source_node=b.id,
            source_socket="Points",
            target_node=a.id,
            target_socket="Mesh",
        )
    )
    # Cube has no Mesh input; the edge still forms a cycle in the node graph.
    cyclic = analyze_dependencies(restored)
    assert cyclic.cycles


def test_spatial_noise_rewrite() -> None:
    graph = IRGraph(id="graph_noise", name="mask")
    noise = IRNode(id="node_noise", operation="procedural.noise")
    noise.add_socket(IRSocket.output("noise_out", "value", DataType.FLOAT))
    mapped = IRNode(id="node_map", operation="math.map_range")
    mapped.add_socket(IRSocket.input("map_in", "value", DataType.FLOAT))
    mapped.add_socket(IRSocket.output("map_out", "value", DataType.FLOAT))
    compare = IRNode(id="node_cmp", operation="selection.compare")
    compare.add_socket(IRSocket.input("cmp_in", "a", DataType.FLOAT))
    compare.add_socket(IRSocket.output("cmp_out", "result", DataType.BOOLEAN))
    graph.add_node(noise)
    graph.add_node(mapped)
    graph.add_node(compare)
    graph.add_connection(IRConnection("c1", "node_noise", "noise_out", "node_map", "map_in"))
    graph.add_connection(IRConnection("c2", "node_map", "map_out", "node_cmp", "cmp_in"))
    rewritten = SpatialNoiseMaskPass().apply(graph)
    assert {node.operation for node in rewritten.nodes.values()} == {"selection.spatial_noise"}


def test_units_coordinates_and_random_are_deterministic() -> None:
    assert convert_length(1.0, "blender", "unreal") == 100.0
    assert convert_length(100.0, "unreal", "houdini") == 1.0
    assert round(convert_angle(3.141592653589793, "blender", "houdini"), 5) == 180.0
    assert convert_position((1.0, 2.0, 3.0), "blender", "houdini") == (1.0, 3.0, -2.0)
    assert convert_position((1.0, 3.0, -2.0), "houdini", "blender") == (1.0, 2.0, 3.0)
    assert random_unit(7, 4) == random_unit(7, 4)
    assert random_unit(7, 4) != random_unit(7, 5)


def test_context_inference() -> None:
    tree = _scatter_tree()

    class Space:
        tree_type = "GeometryNodeTree"
        node_tree = tree

    class Context:
        space_data = Space()

    system, found, label = infer_source(Context())
    assert system == "geometry_nodes"
    assert found is tree
    assert label == "BuildingGenerator"

    class Modifier:
        type = "NODES"
        name = "GeometryNodes"
        node_group = tree

    class Obj:
        modifiers = [Modifier()]

    class Fallback:
        space_data = None
        active_object = Obj()

    system, found, label = infer_source(Fallback())
    assert found is tree
    assert label == "BuildingGenerator"
