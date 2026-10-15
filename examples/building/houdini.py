"""NodeBridge Houdini SOP network.

Source: geometry_nodes / BuildingGenerator
Target: Houdini
Confidence: 3 exact, 8 equivalent, 0 approximate, 0 unsupported.

Paste into the Houdini Python Source Editor and run.
The script creates a new geometry container and does not modify other nodes.
Equivalent and approximate operations are semantically related, not numerically identical.
"""

import hou

def build(parent=None):
    """Create a NodeBridge SOP network under parent. Existing nodes are left alone."""
    parent = parent or hou.node('/obj')
    if parent is None:
        raise hou.Error("NodeBridge could not find /obj. Pass parent= to build().")
    name = 'NB_buildinggenerator' if parent.node('NB_buildinggenerator') is None else 'NB_buildinggenerator_' + str(sum(1 for item in parent.children() if item.name().startswith('NB_buildinggenerator')) + 1)
    container = parent.createNode('geo', name)
    for child in list(container.children()):
        child.destroy()
    container.setComment('NodeBridge 0.3.0\\nSource: BuildingGenerator')
    container.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    templates = container.parmTemplateGroup()
    if templates.find('height') is None:
        templates.append(hou.FloatParmTemplate('height', 'Height', 1, default_value=(3.0,)))
    if templates.find('density') is None:
        templates.append(hou.FloatParmTemplate('density', 'Density', 1, default_value=(4.0,)))
    container.setParmTemplateGroup(templates)
    # operation: group_input kind=group_input confidence=equivalent
    # source: NodeGroupInput
    # A geometry group input becomes an Object Merge. Assign Source Object on the container.
    # operation: panel_scale kind=random confidence=equivalent
    # source: FunctionNodeRandomValue
    # Random values use NodeBridge's hash when deterministic randomness is on, otherwise Houdini rand(). Neither is Blender's sequence.
    # operation: footprint kind=primitive confidence=equivalent
    # source: GeometryNodeMeshGrid
    # A Blender grid primitive becomes a Houdini grid SOP. Topology and axis orientation can differ.
    grid_1 = container.createNode('grid', 'footprint')
    grid_1.parm('sizex').set(8.0)
    grid_1.parm('sizey').set(8.0)
    grid_1.parm('rows').set(4)
    grid_1.parm('cols').set(4)
    grid_1.moveToGoodPosition()
    # operation: facade_panel kind=primitive confidence=exact
    # source: GeometryNodeMeshCube
    # Mesh primitives become the matching Houdini generator SOP. Size and radius are converted into Houdini axes.
    cube_2 = container.createNode('box', 'facade_panel')
    cube_2.parmTuple('size').set((0.6, 0.8, 0.08))
    cube_2.moveToGoodPosition()
    # operation: walls kind=extrude confidence=equivalent
    # source: GeometryNodeExtrudeMesh
    # Extrude Mesh becomes Poly Extrude. The offset vector is reduced to a distance along the Houdini extrude.
    extrude_3 = container.createNode('polyextrude::2.0', 'walls')
    extrude_3.setInput(0, grid_1)
    extrude_3.parm('dist').set(3.0)
    extrude_3.setComment('Equivalent: distance is the length of the converted offset.')
    extrude_3.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    extrude_3.moveToGoodPosition()
    # operation: floors kind=subdivide confidence=equivalent
    # source: GeometryNodeSubdivideMesh
    # Subdivide Mesh becomes one Subdivide SOP per level, capped at six.
    subdivide_4 = container.createNode('subdivide', 'floors_1')
    subdivide_4.setInput(0, extrude_3)
    subdivide_4.moveToGoodPosition()
    # operation: floors kind=subdivide confidence=equivalent
    # source: GeometryNodeSubdivideMesh
    # Subdivide Mesh becomes one Subdivide SOP per level, capped at six.
    subdivide_5 = container.createNode('subdivide', 'floors_2')
    subdivide_5.setInput(0, subdivide_4)
    subdivide_5.moveToGoodPosition()
    # operation: facade_points kind=scatter confidence=equivalent
    # source: GeometryNodeDistributePointsOnFaces
    # Distribute Points on Faces becomes a Scatter SOP in density mode. Houdini's random distribution is not Blender's, so the same seed does not reproduce the same points.
    scatter_6 = container.createNode('scatter::2.0', 'facade_points')
    scatter_6.setInput(0, subdivide_5)
    scatter_6.parm('forcetotal').set(0)
    scatter_6.parm('seed').set(5)
    scatter_6.parm('densityscale').setExpression('ch("../density")')
    scatter_6.setComment("Distribute Points on Faces becomes a Scatter SOP in density mode. Houdini's random distribution is not Blender's, so the same seed does not reproduce the same points.")
    scatter_6.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    scatter_6.moveToGoodPosition()
    # operation: facade_instances kind=instance confidence=equivalent
    # source: GeometryNodeInstanceOnPoints
    # Instance on Points becomes Copy to Points. The first input is the instance geometry and the second input is the points. Scale and rotation are point attributes.
    variation_7 = container.createNode('attribwrangle', 'instance_variation')
    variation_7.setInput(0, scatter_6)
    variation_7.parm('class').set(2)
    variation_7.parm('snippet').set(
        """
        int nb_lshr(int value; int bits) {
            int shifted = value >> bits;
            int mask = (1 << (32 - bits)) - 1;
            return shifted & mask;
        }
        int nb_hash(int seed; int elem) {
            int x = seed ^ (elem * 747796405 + (-1403630843));
            x = (x ^ nb_lshr(x, 16)) * (-2048144777);
            x = (x ^ nb_lshr(x, 13)) * (-1028477379);
            x = x ^ nb_lshr(x, 16);
            return x;
        }
        float nb_rand(int seed; int elem) {
            return float(nb_hash(seed, elem) & 16777215) / 16777216.0;
        }
        @pscale = lerp(0.700000, 1.300000, nb_rand(int(9.000000), @ptnum));
        """
    )
    variation_7.setComment("Equivalent: random values use the selected NodeBridge or Houdini random, not Blender's sequence.")
    variation_7.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    variation_7.moveToGoodPosition()
    # operation: facade_instances kind=instance confidence=equivalent
    # source: GeometryNodeInstanceOnPoints
    # Instance on Points becomes Copy to Points. The first input is the instance geometry and the second input is the points. Scale and rotation are point attributes.
    instance_8 = container.createNode('copytopoints::2.0', 'facade_instances')
    instance_8.setInput(0, cube_2)
    instance_8.setInput(1, variation_7)
    instance_8.setComment('Input 0 is the geometry to copy. Input 1 is the points.')
    instance_8.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    instance_8.moveToGoodPosition()
    # operation: realize_facade kind=realize_instances confidence=equivalent
    # source: GeometryNodeRealizeInstances
    # Realize Instances becomes Unpack. Copy to Points has already applied instance transforms.
    realize_9 = container.createNode('unpack', 'realize_facade')
    realize_9.setInput(0, instance_8)
    realize_9.moveToGoodPosition()
    # operation: join_building kind=merge confidence=exact
    # source: GeometryNodeJoinGeometry
    # Join Geometry becomes a Merge SOP. Inputs stay in link order.
    merge_10 = container.createNode('merge', 'join_building')
    merge_10.setInput(0, subdivide_5)
    merge_10.setInput(1, realize_9)
    merge_10.moveToGoodPosition()
    # operation: group_output kind=group_output confidence=exact
    # source: NodeGroupOutput
    # The group output is a null SOP with the display and render flags set.
    out_11 = container.createNode('null', 'OUT')
    out_11.setInput(0, merge_10)
    out_11.setDisplayFlag(True)
    out_11.setRenderFlag(True)
    out_11.moveToGoodPosition()
    container.layoutChildren()
    return container


if __name__ == '__main__':
    build()
