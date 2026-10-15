"""NodeBridge Houdini SOP network.

Source: geometry_nodes / ScatterBuildings
Target: Houdini
Confidence: 2 exact, 6 equivalent, 0 approximate, 0 unsupported.

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
    name = 'NB_scatterbuildings' if parent.node('NB_scatterbuildings') is None else 'NB_scatterbuildings_' + str(sum(1 for item in parent.children() if item.name().startswith('NB_scatterbuildings')) + 1)
    container = parent.createNode('geo', name)
    for child in list(container.children()):
        child.destroy()
    container.setComment('NodeBridge 0.3.0\\nSource: ScatterBuildings')
    container.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    templates = container.parmTemplateGroup()
    if templates.find('source_object') is None:
        templates.append(hou.StringParmTemplate('source_object', 'Source Object', 1, default_value=('',)))
    if templates.find('density') is None:
        templates.append(hou.FloatParmTemplate('density', 'Density', 1, default_value=(25.0,)))
    container.setParmTemplateGroup(templates)
    # operation: random_scale kind=random confidence=equivalent
    # source: FunctionNodeRandomValue
    # Random values use NodeBridge's hash when deterministic randomness is on, otherwise Houdini rand(). Neither is Blender's sequence.
    # operation: random_rotation kind=random confidence=equivalent
    # source: FunctionNodeRandomValue
    # Random values use NodeBridge's hash when deterministic randomness is on, otherwise Houdini rand(). Neither is Blender's sequence.
    # operation: group_input kind=group_input confidence=equivalent
    # source: NodeGroupInput
    # A geometry group input becomes an Object Merge. Assign Source Object on the container.
    geometry_input_1 = container.createNode('object_merge', 'geometry_input')
    geometry_input_1.parm('objpath1').setExpression('chs("../source_object")')
    geometry_input_1.setComment('Assign source_object to the SOP that should feed this network.')
    geometry_input_1.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    geometry_input_1.moveToGoodPosition()
    # operation: instance_cube kind=primitive confidence=exact
    # source: GeometryNodeMeshCube
    # Mesh primitives become the matching Houdini generator SOP. Size and radius are converted into Houdini axes.
    cube_2 = container.createNode('box', 'instance_cube')
    cube_2.parmTuple('size').set((1.0, 1.0, 1.0))
    cube_2.moveToGoodPosition()
    # operation: building_scatter kind=scatter confidence=equivalent
    # source: GeometryNodeDistributePointsOnFaces
    # Distribute Points on Faces becomes a Scatter SOP in density mode. Houdini's random distribution is not Blender's, so the same seed does not reproduce the same points.
    scatter_3 = container.createNode('scatter::2.0', 'building_scatter')
    scatter_3.setInput(0, geometry_input_1)
    scatter_3.parm('forcetotal').set(0)
    scatter_3.parm('seed').set(3)
    scatter_3.parm('densityscale').setExpression('ch("../density")')
    scatter_3.setComment("Distribute Points on Faces becomes a Scatter SOP in density mode. Houdini's random distribution is not Blender's, so the same seed does not reproduce the same points.")
    scatter_3.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    scatter_3.moveToGoodPosition()
    # operation: instance_on_points kind=instance confidence=equivalent
    # source: GeometryNodeInstanceOnPoints
    # Instance on Points becomes Copy to Points. The first input is the instance geometry and the second input is the points. Scale and rotation are point attributes.
    variation_4 = container.createNode('attribwrangle', 'instance_variation')
    variation_4.setInput(0, scatter_3)
    variation_4.parm('class').set(2)
    variation_4.parm('snippet').set(
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
        @pscale = lerp(0.400000, 1.200000, nb_rand(int(7.000000), @ptnum));
        // Random euler components are remapped onto Houdini axes, then interpolated.
        vector4 nb_euler_to_orient(float x; float y; float z) {
            float cx = cos(x * 0.5);
            float sx = sin(x * 0.5);
            float cy = cos(y * 0.5);
            float sy = sin(y * 0.5);
            float cz = cos(z * 0.5);
            float sz = sin(z * 0.5);
            return set(
                sx * cy * cz - cx * sy * sz,
                cx * sy * cz + sx * cy * sz,
                cx * cy * sz - sx * sy * cz,
                cx * cy * cz + sx * sy * sz
            );
        }
        float _rx = lerp(0.000000, 0.000000, nb_rand(int(11.000000) + 11, @ptnum));
        float _ry = lerp(0.000000, 6.283180, nb_rand(int(11.000000) + 29, @ptnum));
        float _rz = lerp(0.000000, 0.000000, nb_rand(int(11.000000) + 47, @ptnum));
        @orient = nb_euler_to_orient(_rx, _ry, _rz);
        """
    )
    variation_4.setComment("Equivalent: random values use the selected NodeBridge or Houdini random, not Blender's sequence.")
    variation_4.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    variation_4.moveToGoodPosition()
    # operation: instance_on_points kind=instance confidence=equivalent
    # source: GeometryNodeInstanceOnPoints
    # Instance on Points becomes Copy to Points. The first input is the instance geometry and the second input is the points. Scale and rotation are point attributes.
    instance_5 = container.createNode('copytopoints::2.0', 'instance_on_points')
    instance_5.setInput(0, cube_2)
    instance_5.setInput(1, variation_4)
    instance_5.setComment('Input 0 is the geometry to copy. Input 1 is the points.')
    instance_5.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    instance_5.moveToGoodPosition()
    # operation: realize kind=realize_instances confidence=equivalent
    # source: GeometryNodeRealizeInstances
    # Realize Instances becomes Unpack. Copy to Points has already applied instance transforms.
    realize_6 = container.createNode('unpack', 'realize')
    realize_6.setInput(0, instance_5)
    realize_6.moveToGoodPosition()
    # operation: group_output kind=group_output confidence=exact
    # source: NodeGroupOutput
    # The group output is a null SOP with the display and render flags set.
    out_7 = container.createNode('null', 'OUT')
    out_7.setInput(0, realize_6)
    out_7.setDisplayFlag(True)
    out_7.setRenderFlag(True)
    out_7.moveToGoodPosition()
    container.layoutChildren()
    return container


if __name__ == '__main__':
    build()
