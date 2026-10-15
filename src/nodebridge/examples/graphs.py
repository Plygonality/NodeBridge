"""Duck-typed Blender node trees used by tests, the CLI, and the examples.

These objects expose the same attributes the parser reads from ``bpy``.
"""

from __future__ import annotations

from types import SimpleNamespace


def socket(identifier, data_type="NodeSocketGeometry", default=None, *, field=False, multi=False, output=False):
    return SimpleNamespace(
        identifier=identifier,
        name=identifier,
        bl_idname=data_type,
        default_value=default,
        is_field=field,
        is_multi_input=multi,
        enabled=True,
        display_shape="DIAMOND" if field else "CIRCLE",
    )


def node(bl_idname, name, inputs=(), outputs=(), **properties):
    item = SimpleNamespace(
        bl_idname=bl_idname,
        name=name,
        label="",
        inputs=list(inputs),
        outputs=list(outputs),
        mute=False,
        location=(0.0, 0.0),
        node_tree=properties.pop("node_tree", None),
        color_ramp=properties.pop("color_ramp", None),
    )
    for key, value in properties.items():
        setattr(item, key, value)
    return item


def link(from_node, from_socket, to_node, to_socket):
    return SimpleNamespace(
        from_node=from_node,
        from_socket=SimpleNamespace(identifier=from_socket, name=from_socket),
        to_node=to_node,
        to_socket=SimpleNamespace(identifier=to_socket, name=to_socket),
        is_valid=True,
    )


def tree(name, nodes, links, *, bl_idname="GeometryNodeTree", interface=()):
    return SimpleNamespace(
        name=name,
        bl_idname=bl_idname,
        nodes=list(nodes),
        links=list(links),
        interface=SimpleNamespace(items_tree=list(interface)),
    )


def interface_socket(name, identifier, data_type, default=None, direction="INPUT"):
    return SimpleNamespace(
        item_type="SOCKET",
        name=name,
        identifier=identifier,
        in_out=direction,
        socket_type=data_type,
        default_value=default,
        min_value=None,
        max_value=None,
        description="",
    )


def scatter_tree():
    """Procedural scatter: surface, points, random scale and rotation, instance."""

    group_in = node(
        "NodeGroupInput",
        "Group Input",
        outputs=[
            socket("Geometry", "NodeSocketGeometry"),
            socket("Density", "NodeSocketFloat", 25.0),
        ],
    )
    cube = node(
        "GeometryNodeMeshCube",
        "Instance Cube",
        inputs=[socket("Size", "NodeSocketVector", (1.0, 1.0, 1.0))],
        outputs=[socket("Mesh", "NodeSocketGeometry")],
    )
    scatter = node(
        "GeometryNodeDistributePointsOnFaces",
        "Building Scatter",
        inputs=[
            socket("Mesh", "NodeSocketGeometry"),
            socket("Selection", "NodeSocketBool", True, field=True),
            socket("Density", "NodeSocketFloat", 25.0, field=True),
            socket("Seed", "NodeSocketInt", 3),
        ],
        outputs=[
            socket("Points", "NodeSocketGeometry"),
            socket("Normal", "NodeSocketVector"),
            socket("Rotation", "NodeSocketVector"),
        ],
        distribute_method="RANDOM",
    )
    random_scale = node(
        "FunctionNodeRandomValue",
        "Random Scale",
        inputs=[
            socket("Min", "NodeSocketFloat", 0.4),
            socket("Max", "NodeSocketFloat", 1.2),
            socket("Seed", "NodeSocketInt", 7),
        ],
        outputs=[socket("Value", "NodeSocketFloat")],
        data_type="FLOAT",
    )
    random_rotation = node(
        "FunctionNodeRandomValue",
        "Random Rotation",
        inputs=[
            socket("Min", "NodeSocketVector", (0.0, 0.0, 0.0)),
            socket("Max", "NodeSocketVector", (0.0, 0.0, 6.28318)),
            socket("Seed", "NodeSocketInt", 11),
        ],
        outputs=[socket("Value", "NodeSocketVector")],
        data_type="FLOAT_VECTOR",
    )
    instance = node(
        "GeometryNodeInstanceOnPoints",
        "Instance on Points",
        inputs=[
            socket("Points", "NodeSocketGeometry"),
            socket("Instance", "NodeSocketGeometry"),
            socket("Rotation", "NodeSocketVector", (0.0, 0.0, 0.0), field=True),
            socket("Scale", "NodeSocketVector", (1.0, 1.0, 1.0), field=True),
        ],
        outputs=[socket("Instances", "NodeSocketGeometry")],
    )
    realize = node(
        "GeometryNodeRealizeInstances",
        "Realize",
        inputs=[socket("Geometry", "NodeSocketGeometry")],
        outputs=[socket("Geometry", "NodeSocketGeometry")],
    )
    group_out = node(
        "NodeGroupOutput",
        "Group Output",
        inputs=[socket("Geometry", "NodeSocketGeometry")],
    )
    nodes = [group_in, cube, scatter, random_scale, random_rotation, instance, realize, group_out]
    links = [
        link(group_in, "Geometry", scatter, "Mesh"),
        link(group_in, "Density", scatter, "Density"),
        link(scatter, "Points", instance, "Points"),
        link(cube, "Mesh", instance, "Instance"),
        link(random_scale, "Value", instance, "Scale"),
        link(random_rotation, "Value", instance, "Rotation"),
        link(instance, "Instances", realize, "Geometry"),
        link(realize, "Geometry", group_out, "Geometry"),
    ]
    return tree(
        "ScatterBuildings",
        nodes,
        links,
        interface=[interface_socket("Density", "Density", "NodeSocketFloat", 25.0)],
    )


def noise_mask_tree():
    position = node("GeometryNodeInputPosition", "Position", outputs=[socket("Position", "NodeSocketVector")])
    noise = node(
        "ShaderNodeTexNoise",
        "Noise Texture",
        inputs=[socket("Vector", "NodeSocketVector", field=True), socket("Scale", "NodeSocketFloat", 5.0)],
        outputs=[socket("Fac", "NodeSocketFloat"), socket("Color", "NodeSocketColor")],
    )
    map_range = node(
        "ShaderNodeMapRange",
        "Map Range",
        inputs=[
            socket("Value", "NodeSocketFloat", 0.0, field=True),
            socket("From Min", "NodeSocketFloat", 0.0),
            socket("From Max", "NodeSocketFloat", 1.0),
            socket("To Min", "NodeSocketFloat", 0.0),
            socket("To Max", "NodeSocketFloat", 1.0),
        ],
        outputs=[socket("Result", "NodeSocketFloat")],
    )
    compare = node(
        "FunctionNodeCompare",
        "Compare",
        inputs=[socket("A", "NodeSocketFloat", 0.0, field=True), socket("B", "NodeSocketFloat", 0.5)],
        outputs=[socket("Result", "NodeSocketBool")],
        operation="GREATER_THAN",
    )
    output = node("NodeGroupOutput", "Group Output", inputs=[socket("Value", "NodeSocketBool")])
    return tree(
        "NoiseMask",
        [position, noise, map_range, compare, output],
        [
            link(position, "Position", noise, "Vector"),
            link(noise, "Fac", map_range, "Value"),
            link(map_range, "Result", compare, "A"),
            link(compare, "Result", output, "Value"),
        ],
    )


def building_tree():
    """Grid footprint, extrusion, subdivided floors, and scattered facade cubes."""

    height = node(
        "NodeGroupInput",
        "Group Input",
        outputs=[
            socket("Height", "NodeSocketFloat", 3.0),
            socket("Density", "NodeSocketFloat", 4.0),
        ],
    )
    grid = node(
        "GeometryNodeMeshGrid",
        "Footprint",
        inputs=[
            socket("Size X", "NodeSocketFloat", 8.0),
            socket("Size Y", "NodeSocketFloat", 8.0),
            socket("Vertices X", "NodeSocketInt", 4),
            socket("Vertices Y", "NodeSocketInt", 4),
        ],
        outputs=[socket("Mesh", "NodeSocketGeometry")],
    )
    extrude = node(
        "GeometryNodeExtrudeMesh",
        "Walls",
        inputs=[
            socket("Mesh", "NodeSocketGeometry"),
            socket("Offset", "NodeSocketVector", (0.0, 0.0, 1.0)),
            socket("Offset Scale", "NodeSocketFloat", 3.0, field=True),
        ],
        outputs=[socket("Mesh", "NodeSocketGeometry")],
        mode="FACES",
    )
    subdivide = node(
        "GeometryNodeSubdivideMesh",
        "Floors",
        inputs=[socket("Mesh", "NodeSocketGeometry"), socket("Level", "NodeSocketInt", 2)],
        outputs=[socket("Mesh", "NodeSocketGeometry")],
    )
    scatter = node(
        "GeometryNodeDistributePointsOnFaces",
        "Facade Points",
        inputs=[
            socket("Mesh", "NodeSocketGeometry"),
            socket("Density", "NodeSocketFloat", 4.0, field=True),
            socket("Seed", "NodeSocketInt", 5),
        ],
        outputs=[socket("Points", "NodeSocketGeometry")],
        distribute_method="RANDOM",
    )
    panel = node(
        "GeometryNodeMeshCube",
        "Facade Panel",
        inputs=[socket("Size", "NodeSocketVector", (0.6, 0.08, 0.8))],
        outputs=[socket("Mesh", "NodeSocketGeometry")],
    )
    random_scale = node(
        "FunctionNodeRandomValue",
        "Panel Scale",
        inputs=[
            socket("Min", "NodeSocketFloat", 0.7),
            socket("Max", "NodeSocketFloat", 1.3),
            socket("Seed", "NodeSocketInt", 9),
        ],
        outputs=[socket("Value", "NodeSocketFloat")],
        data_type="FLOAT",
    )
    instance = node(
        "GeometryNodeInstanceOnPoints",
        "Facade Instances",
        inputs=[
            socket("Points", "NodeSocketGeometry"),
            socket("Instance", "NodeSocketGeometry"),
            socket("Scale", "NodeSocketVector", (1.0, 1.0, 1.0), field=True),
        ],
        outputs=[socket("Instances", "NodeSocketGeometry")],
    )
    realize = node(
        "GeometryNodeRealizeInstances",
        "Realize Facade",
        inputs=[socket("Geometry", "NodeSocketGeometry")],
        outputs=[socket("Geometry", "NodeSocketGeometry")],
    )
    joined = node(
        "GeometryNodeJoinGeometry",
        "Join Building",
        inputs=[socket("Geometry", "NodeSocketGeometry", multi=True)],
        outputs=[socket("Geometry", "NodeSocketGeometry")],
    )
    output = node("NodeGroupOutput", "Group Output", inputs=[socket("Geometry", "NodeSocketGeometry")])
    nodes = [height, grid, extrude, subdivide, scatter, panel, random_scale, instance, realize, joined, output]
    links = [
        link(grid, "Mesh", extrude, "Mesh"),
        link(height, "Height", extrude, "Offset Scale"),
        link(extrude, "Mesh", subdivide, "Mesh"),
        link(subdivide, "Mesh", scatter, "Mesh"),
        link(height, "Density", scatter, "Density"),
        link(scatter, "Points", instance, "Points"),
        link(panel, "Mesh", instance, "Instance"),
        link(random_scale, "Value", instance, "Scale"),
        link(instance, "Instances", realize, "Geometry"),
        link(subdivide, "Mesh", joined, "Geometry"),
        link(realize, "Geometry", joined, "Geometry"),
        link(joined, "Geometry", output, "Geometry"),
    ]
    return tree(
        "BuildingGenerator",
        nodes,
        links,
        interface=[
            interface_socket("Height", "Height", "NodeSocketFloat", 3.0),
            interface_socket("Density", "Density", "NodeSocketFloat", 4.0),
        ],
    )


def shader_tree():
    """Noise, a color ramp, roughness, and a normal bump into Principled BSDF."""

    texcoord = node(
        "ShaderNodeTexCoord",
        "Texture Coordinate",
        outputs=[socket("Object", "NodeSocketVector"), socket("UV", "NodeSocketVector")],
    )
    noise = node(
        "ShaderNodeTexNoise",
        "Noise Texture",
        inputs=[socket("Vector", "NodeSocketVector", field=True), socket("Scale", "NodeSocketFloat", 5.0)],
        outputs=[socket("Fac", "NodeSocketFloat"), socket("Color", "NodeSocketColor")],
    )
    ramp = node(
        "ShaderNodeValToRGB",
        "Color Ramp",
        inputs=[socket("Fac", "NodeSocketFloat", 0.0, field=True)],
        outputs=[socket("Color", "NodeSocketColor"), socket("Alpha", "NodeSocketFloat")],
        color_ramp=SimpleNamespace(
            elements=[
                SimpleNamespace(position=0.0, color=(0.05, 0.05, 0.05, 1.0)),
                SimpleNamespace(position=1.0, color=(0.8, 0.45, 0.2, 1.0)),
            ]
        ),
    )
    roughness = node(
        "ShaderNodeMapRange",
        "Roughness Range",
        inputs=[
            socket("Value", "NodeSocketFloat", 0.0, field=True),
            socket("From Min", "NodeSocketFloat", 0.0),
            socket("From Max", "NodeSocketFloat", 1.0),
            socket("To Min", "NodeSocketFloat", 0.2),
            socket("To Max", "NodeSocketFloat", 0.85),
        ],
        outputs=[socket("Result", "NodeSocketFloat")],
    )
    bump = node(
        "ShaderNodeBump",
        "Bump",
        inputs=[
            socket("Strength", "NodeSocketFloat", 0.2),
            socket("Height", "NodeSocketFloat", 0.0, field=True),
        ],
        outputs=[socket("Normal", "NodeSocketVector")],
    )
    principled = node(
        "ShaderNodeBsdfPrincipled",
        "Principled BSDF",
        inputs=[
            socket("Base Color", "NodeSocketColor", (0.8, 0.8, 0.8, 1.0)),
            socket("Roughness", "NodeSocketFloat", 0.5),
            socket("Metallic", "NodeSocketFloat", 0.0),
            socket("Normal", "NodeSocketVector"),
        ],
        outputs=[socket("BSDF", "NodeSocketShader")],
    )
    output = node(
        "ShaderNodeOutputMaterial",
        "Material Output",
        inputs=[socket("Surface", "NodeSocketShader")],
    )
    return tree(
        "WeatheredMetal",
        [texcoord, noise, ramp, roughness, bump, principled, output],
        [
            link(texcoord, "Object", noise, "Vector"),
            link(noise, "Fac", ramp, "Fac"),
            link(noise, "Fac", roughness, "Value"),
            link(noise, "Fac", bump, "Height"),
            link(ramp, "Color", principled, "Base Color"),
            link(roughness, "Result", principled, "Roughness"),
            link(bump, "Normal", principled, "Normal"),
            link(principled, "BSDF", output, "Surface"),
        ],
        bl_idname="ShaderNodeTree",
    )


def compositor_tree():
    """Render layer, glare, color correction, vignette, and a composite output."""

    render = node(
        "CompositorNodeRLayers",
        "Render Layers",
        outputs=[socket("Image", "NodeSocketColor")],
    )
    glare = node(
        "CompositorNodeGlare",
        "Glare",
        inputs=[socket("Image", "NodeSocketColor")],
        outputs=[socket("Image", "NodeSocketColor")],
    )
    color = node(
        "CompositorNodeBrightContrast",
        "Color Correction",
        inputs=[socket("Image", "NodeSocketColor")],
        outputs=[socket("Image", "NodeSocketColor")],
    )
    vignette = node(
        "CompositorNodeEllipseMask",
        "Vignette",
        inputs=[socket("Mask", "NodeSocketFloat", 1.0)],
        outputs=[socket("Mask", "NodeSocketFloat")],
    )
    mix = node(
        "CompositorNodeMixRGB",
        "Vignette Mix",
        inputs=[
            socket("Fac", "NodeSocketFloat", 1.0),
            socket("Image", "NodeSocketColor"),
        ],
        outputs=[socket("Image", "NodeSocketColor")],
        blend_type="MULTIPLY",
    )
    output = node(
        "CompositorNodeComposite",
        "Composite",
        inputs=[socket("Image", "NodeSocketColor")],
    )
    return tree(
        "GradeAndGlare",
        [render, glare, color, vignette, mix, output],
        [
            link(render, "Image", glare, "Image"),
            link(glare, "Image", color, "Image"),
            link(color, "Image", mix, "Image"),
            link(vignette, "Mask", mix, "Fac"),
            link(mix, "Image", output, "Image"),
        ],
        bl_idname="CompositorNodeTree",
    )


EXAMPLES = {
    "scatter": scatter_tree,
    "building": building_tree,
    "shader": shader_tree,
    "compositor": compositor_tree,
}
