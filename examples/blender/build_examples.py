"""Build the four NodeBridge example systems in the current Blender file.

Run from Blender's Text Editor (Run Script), or headless:

    blender --background --factory-startup --python examples/blender/build_examples.py -- --save examples.blend

Creates:
  * "ScatterRocks"      Geometry Nodes scatter system on a ground plane
  * "BuildingGenerator" Geometry Nodes building system (uses the "FloorSlab" group)
  * "ProceduralRock"    procedural material (noise, color ramp, roughness, bump)
  * a compositor setup  render layer, glare, color balance, vignette, composite
"""

import math
import sys

import bpy


def _link(tree, from_node, from_socket, to_node, to_socket):
    out = from_node.outputs[from_socket] if isinstance(from_socket, (int, str)) else from_socket
    inp = to_node.inputs[to_socket] if isinstance(to_socket, (int, str)) else to_socket
    return tree.links.new(out, inp)


def _new_tree(name, kind="GeometryNodeTree"):
    old = bpy.data.node_groups.get(name)
    if old is not None:
        bpy.data.node_groups.remove(old)
    return bpy.data.node_groups.new(name, kind)


def _socket(tree, name, in_out, socket_type, default=None, min_value=None, max_value=None, subtype=None):
    item = tree.interface.new_socket(name, in_out=in_out, socket_type=socket_type)
    if subtype is not None:
        item.subtype = subtype
    if default is not None:
        item.default_value = default
    if min_value is not None:
        item.min_value = min_value
    if max_value is not None:
        item.max_value = max_value
    return item


def _random_input(node, data_type, name):
    """Random Value has one socket per data type; pick the enabled one."""
    return next(s for s in node.inputs if s.name == name and s.enabled)


def _random_output(node):
    return next(s for s in node.outputs if s.enabled)


def _material(name, color):
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.diffuse_color = color
    return material


def _object_with_modifier(name, mesh_factory, tree):
    obj = bpy.data.objects.get(name)
    if obj is None:
        obj = bpy.data.objects.new(name, mesh_factory())
        bpy.context.scene.collection.objects.link(obj)
    for modifier in list(obj.modifiers):
        obj.modifiers.remove(modifier)
    modifier = obj.modifiers.new("NodeBridge Example", "NODES")
    modifier.node_group = tree
    return obj, modifier


def _plane_mesh(size=20.0):
    mesh = bpy.data.meshes.new("GroundMesh")
    h = size / 2
    mesh.from_pydata([(-h, -h, 0), (h, -h, 0), (h, h, 0), (-h, h, 0)], [], [(0, 1, 2, 3)])
    return mesh


def build_scatter():
    tree = _new_tree("ScatterRocks")
    _socket(tree, "Geometry", "INPUT", "NodeSocketGeometry")
    _socket(tree, "Density", "INPUT", "NodeSocketFloat", 4.0, 0.0, 100.0)
    _socket(tree, "Seed", "INPUT", "NodeSocketInt", 7)
    _socket(tree, "Scale Min", "INPUT", "NodeSocketFloat", 0.6, 0.0, 10.0)
    _socket(tree, "Scale Max", "INPUT", "NodeSocketFloat", 1.4, 0.0, 10.0)
    _socket(tree, "Coverage", "INPUT", "NodeSocketFloat", 0.45, 0.0, 1.0, subtype="FACTOR")
    _socket(tree, "Geometry", "OUTPUT", "NodeSocketGeometry")
    n = tree.nodes
    gin = n.new("NodeGroupInput")
    gout = n.new("NodeGroupOutput")

    distribute = n.new("GeometryNodeDistributePointsOnFaces")
    distribute.name = distribute.label = "Scatter Rocks"
    _link(tree, gin, "Geometry", distribute, "Mesh")
    _link(tree, gin, "Density", distribute, "Density")
    _link(tree, gin, "Seed", distribute, "Seed")

    noise = n.new("ShaderNodeTexNoise")
    noise.name = noise.label = "Coverage Noise"
    noise.inputs["Scale"].default_value = 0.35
    noise.inputs["Detail"].default_value = 3.0
    map_range = n.new("ShaderNodeMapRange")
    map_range.name = "Coverage Remap"
    map_range.inputs["From Min"].default_value = 0.3
    map_range.inputs["From Max"].default_value = 0.7
    compare = n.new("FunctionNodeCompare")
    compare.name = "Coverage Threshold"
    compare.operation = "LESS_THAN"
    _link(tree, noise, "Fac", map_range, "Value")
    _link(tree, map_range, "Result", compare, "A")
    _link(tree, gin, "Coverage", compare, "B")
    delete = n.new("GeometryNodeDeleteGeometry")
    delete.name = delete.label = "Remove Sparse Areas"
    delete.domain = "POINT"
    _link(tree, distribute, "Points", delete, "Geometry")
    _link(tree, compare, "Result", delete, "Selection")

    rock = n.new("GeometryNodeMeshIcoSphere")
    rock.name = rock.label = "Rock Shape"
    rock.inputs["Radius"].default_value = 0.25
    rock.inputs["Subdivisions"].default_value = 2
    lift = n.new("GeometryNodeTransform")
    lift.name = "Sink Rock"
    lift.inputs["Translation"].default_value = (0.0, 0.0, -0.05)
    lift.inputs["Scale"].default_value = (1.0, 1.0, 0.6)
    _link(tree, rock, "Mesh", lift, "Geometry")
    material = n.new("GeometryNodeSetMaterial")
    material.name = "Rock Material"
    material.inputs["Material"].default_value = _material("ProceduralRock", (0.4, 0.35, 0.3, 1.0))
    _link(tree, lift, "Geometry", material, "Geometry")

    scale = n.new("FunctionNodeRandomValue")
    scale.name = scale.label = "Random Scale"
    scale.data_type = "FLOAT"
    _link(tree, gin, "Scale Min", scale, _random_input(scale, "FLOAT", "Min"))
    _link(tree, gin, "Scale Max", scale, _random_input(scale, "FLOAT", "Max"))
    _link(tree, gin, "Seed", scale, "Seed")

    instance = n.new("GeometryNodeInstanceOnPoints")
    instance.name = instance.label = "Place Rocks"
    _link(tree, delete, "Geometry", instance, "Points")
    _link(tree, material, "Geometry", instance, "Instance")
    tree.links.new(_random_output(scale), instance.inputs["Scale"])

    rotation = n.new("FunctionNodeRandomValue")
    rotation.name = rotation.label = "Random Rotation"
    rotation.data_type = "FLOAT_VECTOR"
    _random_input(rotation, "FLOAT_VECTOR", "Max").default_value = (0.0, 0.0, 2 * math.pi)
    rotation.inputs["Seed"].default_value = 3
    rotate = n.new("GeometryNodeRotateInstances")
    rotate.name = rotate.label = "Random Yaw"
    _link(tree, instance, "Instances", rotate, "Instances")
    tree.links.new(_random_output(rotation), rotate.inputs["Rotation"])

    realize = n.new("GeometryNodeRealizeInstances")
    _link(tree, rotate, "Instances", realize, "Geometry")
    join = n.new("GeometryNodeJoinGeometry")
    _link(tree, realize, "Geometry", join, "Geometry")
    _link(tree, gin, "Geometry", join, "Geometry")
    _link(tree, join, "Geometry", gout, "Geometry")

    obj, modifier = _object_with_modifier("Ground", _plane_mesh, tree)
    return tree, obj


def build_floor_slab_group():
    tree = _new_tree("FloorSlab")
    _socket(tree, "Width", "INPUT", "NodeSocketFloat", 10.0, subtype="DISTANCE")
    _socket(tree, "Depth", "INPUT", "NodeSocketFloat", 8.0, subtype="DISTANCE")
    _socket(tree, "Thickness", "INPUT", "NodeSocketFloat", 0.25, subtype="DISTANCE")
    _socket(tree, "Slab", "OUTPUT", "NodeSocketGeometry")
    n = tree.nodes
    gin, gout = n.new("NodeGroupInput"), n.new("NodeGroupOutput")
    grid = n.new("GeometryNodeMeshGrid")
    grid.name = "Slab Outline"
    grid.inputs["Vertices X"].default_value = 2
    grid.inputs["Vertices Y"].default_value = 2
    _link(tree, gin, "Width", grid, "Size X")
    _link(tree, gin, "Depth", grid, "Size Y")
    extrude = n.new("GeometryNodeExtrudeMesh")
    extrude.name = "Slab Thickness"
    _link(tree, grid, "Mesh", extrude, "Mesh")
    _link(tree, gin, "Thickness", extrude, "Offset Scale")
    _link(tree, extrude, "Mesh", gout, "Slab")
    return tree


def build_building():
    slab_group = build_floor_slab_group()
    tree = _new_tree("BuildingGenerator")
    _socket(tree, "Geometry", "INPUT", "NodeSocketGeometry")
    _socket(tree, "Width", "INPUT", "NodeSocketFloat", 10.0, 1.0, 100.0, subtype="DISTANCE")
    _socket(tree, "Depth", "INPUT", "NodeSocketFloat", 8.0, 1.0, 100.0, subtype="DISTANCE")
    _socket(tree, "Floors", "INPUT", "NodeSocketInt", 6, 1, 60)
    _socket(tree, "Floor Height", "INPUT", "NodeSocketFloat", 3.0, 2.0, 10.0, subtype="DISTANCE")
    _socket(tree, "Window Density", "INPUT", "NodeSocketFloat", 0.35, 0.0, 5.0)
    _socket(tree, "Seed", "INPUT", "NodeSocketInt", 1)
    _socket(tree, "Geometry", "OUTPUT", "NodeSocketGeometry")
    n = tree.nodes
    gin, gout = n.new("NodeGroupInput"), n.new("NodeGroupOutput")

    footprint = n.new("GeometryNodeMeshGrid")
    footprint.name = footprint.label = "Footprint"
    footprint.inputs["Vertices X"].default_value = 2
    footprint.inputs["Vertices Y"].default_value = 2
    _link(tree, gin, "Width", footprint, "Size X")
    _link(tree, gin, "Depth", footprint, "Size Y")
    height = n.new("ShaderNodeMath")
    height.name = height.label = "Building Height"
    height.operation = "MULTIPLY"
    _link(tree, gin, "Floors", height, 0)
    _link(tree, gin, "Floor Height", height, 1)
    mass = n.new("GeometryNodeExtrudeMesh")
    mass.name = mass.label = "Building Mass"
    _link(tree, footprint, "Mesh", mass, "Mesh")
    _link(tree, height, "Value", mass, "Offset Scale")

    offset = n.new("ShaderNodeCombineXYZ")
    offset.name = "Floor Offset"
    _link(tree, gin, "Floor Height", offset, "Z")
    levels = n.new("GeometryNodeMeshLine")
    levels.name = levels.label = "Floor Levels"
    _link(tree, gin, "Floors", levels, "Count")
    _link(tree, offset, "Vector", levels, "Offset")
    margin_w = n.new("ShaderNodeMath")
    margin_w.name = "Slab Width"
    margin_w.inputs[1].default_value = 0.6
    _link(tree, gin, "Width", margin_w, 0)
    margin_d = n.new("ShaderNodeMath")
    margin_d.name = "Slab Depth"
    margin_d.inputs[1].default_value = 0.6
    _link(tree, gin, "Depth", margin_d, 0)
    slab = n.new("GeometryNodeGroup")
    slab.node_tree = slab_group
    slab.name = slab.label = "Floor Slab"
    _link(tree, margin_w, "Value", slab, "Width")
    _link(tree, margin_d, "Value", slab, "Depth")
    floors = n.new("GeometryNodeInstanceOnPoints")
    floors.name = floors.label = "Stack Floors"
    _link(tree, levels, "Mesh", floors, "Points")
    _link(tree, slab, "Slab", floors, "Instance")
    floors_real = n.new("GeometryNodeRealizeInstances")
    floors_real.name = "Realize Floors"
    _link(tree, floors, "Instances", floors_real, "Geometry")

    normal = n.new("GeometryNodeInputNormal")
    split = n.new("ShaderNodeSeparateXYZ")
    _link(tree, normal, "Normal", split, "Vector")
    vertical = n.new("ShaderNodeMath")
    vertical.name = "Facade Facing"
    vertical.operation = "ABSOLUTE"
    _link(tree, split, "Z", vertical, 0)
    is_wall = n.new("FunctionNodeCompare")
    is_wall.name = is_wall.label = "Is Wall"
    is_wall.operation = "LESS_THAN"
    is_wall.inputs["B"].default_value = 0.1
    _link(tree, vertical, "Value", is_wall, "A")
    windows_pts = n.new("GeometryNodeDistributePointsOnFaces")
    windows_pts.name = windows_pts.label = "Window Positions"
    _link(tree, mass, "Mesh", windows_pts, "Mesh")
    _link(tree, is_wall, "Result", windows_pts, "Selection")
    _link(tree, gin, "Window Density", windows_pts, "Density")
    _link(tree, gin, "Seed", windows_pts, "Seed")
    window = n.new("GeometryNodeMeshCube")
    window.name = window.label = "Window Panel"
    window.inputs["Size"].default_value = (0.9, 0.9, 1.3)
    variation = n.new("FunctionNodeRandomValue")
    variation.name = variation.label = "Window Variation"
    _random_input(variation, "FLOAT", "Min").default_value = 0.7
    _random_input(variation, "FLOAT", "Max").default_value = 1.2
    _link(tree, gin, "Seed", variation, "Seed")
    windows = n.new("GeometryNodeInstanceOnPoints")
    windows.name = windows.label = "Place Windows"
    _link(tree, windows_pts, "Points", windows, "Points")
    _link(tree, window, "Mesh", windows, "Instance")
    tree.links.new(_random_output(variation), windows.inputs["Scale"])
    windows_real = n.new("GeometryNodeRealizeInstances")
    windows_real.name = "Realize Windows"
    _link(tree, windows, "Instances", windows_real, "Geometry")

    join = n.new("GeometryNodeJoinGeometry")
    join.name = "Assemble Building"
    for source in (windows_real, floors_real, mass):
        _link(tree, source, "Geometry" if source is not mass else "Mesh", join, "Geometry")
    concrete = n.new("GeometryNodeSetMaterial")
    concrete.name = "Concrete"
    concrete.inputs["Material"].default_value = _material("Concrete", (0.6, 0.6, 0.58, 1.0))
    _link(tree, join, "Geometry", concrete, "Geometry")
    _link(tree, concrete, "Geometry", gout, "Geometry")

    obj, modifier = _object_with_modifier("Building", lambda: bpy.data.meshes.new("BuildingMesh"), tree)
    obj.location = (30.0, 0.0, 0.0)
    return tree, obj


def build_shader():
    material = _material("ProceduralRock", (0.4, 0.35, 0.3, 1.0))
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    n = tree.nodes
    out = n.new("ShaderNodeOutputMaterial")
    bsdf = n.new("ShaderNodeBsdfPrincipled")
    _link(tree, bsdf, "BSDF", out, "Surface")
    coords = n.new("ShaderNodeTexCoord")
    mapping = n.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (2.0, 2.0, 2.0)
    _link(tree, coords, "Object", mapping, "Vector")
    noise = n.new("ShaderNodeTexNoise")
    noise.name = noise.label = "Rock Noise"
    noise.inputs["Scale"].default_value = 4.0
    noise.inputs["Detail"].default_value = 8.0
    noise.inputs["Roughness"].default_value = 0.6
    _link(tree, mapping, "Vector", noise, "Vector")
    ramp = n.new("ShaderNodeValToRGB")
    ramp.name = ramp.label = "Rock Colors"
    ramp.color_ramp.elements[0].position = 0.3
    ramp.color_ramp.elements[0].color = (0.08, 0.07, 0.06, 1.0)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (0.55, 0.5, 0.42, 1.0)
    mid = ramp.color_ramp.elements.new(0.5)
    mid.color = (0.25, 0.2, 0.15, 1.0)
    _link(tree, noise, "Fac", ramp, "Fac")
    _link(tree, ramp, "Color", bsdf, "Base Color")
    rough_scale = n.new("ShaderNodeValue")
    rough_scale.label = "Roughness Scale"
    rough_scale.outputs[0].default_value = 0.9
    rough = n.new("ShaderNodeMapRange")
    rough.name = rough.label = "Roughness Range"
    rough.inputs["To Min"].default_value = 0.45
    _link(tree, noise, "Fac", rough, "Value")
    _link(tree, rough_scale, "Value", rough, "To Max")
    _link(tree, rough, "Result", bsdf, "Roughness")
    bump = n.new("ShaderNodeBump")
    bump.name = bump.label = "Rock Bump"
    bump.inputs["Strength"].default_value = 0.35
    _link(tree, noise, "Fac", bump, "Height")
    _link(tree, bump, "Normal", bsdf, "Normal")
    ground = bpy.data.objects.get("Ground")
    if ground is not None and not ground.data.materials:
        ground.data.materials.append(material)
    return material


def build_compositor():
    scene = bpy.context.scene
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    n = tree.nodes
    layers = n.new("CompositorNodeRLayers")
    glare = n.new("CompositorNodeGlare")
    glare.name = glare.label = "Bloom"
    glare.glare_type = "FOG_GLOW"
    glare.quality = "HIGH"
    if "Highlights Threshold" in glare.inputs:
        glare.inputs["Highlights Threshold"].default_value = 0.8
    else:
        glare.threshold = 0.8
    _link(tree, layers, "Image", glare, "Image")
    grade = n.new("CompositorNodeColorBalance")
    grade.name = grade.label = "Grade"
    if "Color Gain" in grade.inputs:
        grade.inputs["Color Gain"].default_value = (1.05, 1.0, 0.92, 1.0)
        grade.inputs["Color Lift"].default_value = (0.98, 1.0, 1.04, 1.0)
    else:
        grade.gain = (1.05, 1.0, 0.92)
        grade.lift = (0.98, 1.0, 1.04)
    _link(tree, glare, "Image", grade, "Image")
    mask = n.new("CompositorNodeEllipseMask")
    mask.name = "Vignette Shape"
    if "Size" in mask.inputs:
        mask.inputs["Size"].default_value = (0.9, 0.75)
    else:
        mask.mask_width, mask.mask_height = 0.9, 0.75
    mask.inputs["Value"].default_value = 1.0
    soften = n.new("CompositorNodeBlur")
    soften.name = "Vignette Softness"
    if soften.inputs["Size"].type == "VECTOR":
        soften.inputs["Size"].default_value = (200.0, 200.0)
    else:
        soften.size_x = soften.size_y = 200
    _link(tree, mask, "Mask", soften, "Image")
    vignette = n.new("CompositorNodeMixRGB")
    vignette.name = vignette.label = "Vignette"
    vignette.blend_type = "MULTIPLY"
    vignette.inputs["Fac"].default_value = 0.6
    _link(tree, grade, "Image", vignette, 1)
    _link(tree, soften, "Image", vignette, 2)
    composite = n.new("CompositorNodeComposite")
    _link(tree, vignette, "Image", composite, "Image")
    return tree


def build_all():
    scatter, ground = build_scatter()
    building, building_obj = build_building()
    material = build_shader()
    compositor = build_compositor()
    return {"scatter": scatter, "building": building, "material": material, "compositor": compositor, "ground": ground, "building_object": building_obj}


if __name__ == "__main__":
    build_all()
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--save" in argv:
        bpy.ops.wm.save_as_mainfile(filepath=argv[argv.index("--save") + 1])
        print("NodeBridge examples saved to", argv[argv.index("--save") + 1])
    else:
        print("NodeBridge examples built: ScatterRocks, BuildingGenerator, ProceduralRock, compositor")
