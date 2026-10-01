"""NodeBridge Houdini COP2 network.

Source: Compositor / GradeAndGlare
Target: Houdini

Paste into the Houdini Python Source Editor and run.
This does not recreate Blender's compositor pixel for pixel.
Glare, vignette masks, and missing COP types are labeled nulls.
"""

import hou

def _cop(parent, type_name, node_name, comment):
    category = hou.cop2NodeTypeCategory()
    if category.nodeTypes().get(type_name) is None:
        node = parent.createNode('null', node_name)
        node.setComment(comment + ' Missing COP type ' + type_name + '.')
        node.setGenericFlag(hou.nodeFlag.DisplayComment, True)
        return node
    node = parent.createNode(type_name, node_name)
    node.setComment(comment)
    node.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    return node

def build(parent=None):
    img = parent or hou.node('/img')
    if img is None:
        raise hou.Error('NodeBridge could not find /img.')
    cop = img.createNode('cop2net', 'NB_gradeandglare')
    previous = None
    # operation: render_layers kind=compositor_operation confidence=equivalent
    # The render layer or image becomes a File COP. Assign the image path after generation.
    cop_0 = _cop(cop, 'file', 'render_layers', 'The render layer or image becomes a File COP. Assign the image path after generation.')
    if previous is not None:
        cop_0.setInput(0, previous)
    previous = cop_0
    # operation: glare kind=compositor_operation confidence=unsupported
    # No reliable COP2 equivalent is implemented for glare.
    cop_1 = _cop(cop, 'null', 'glare', 'No reliable COP2 equivalent is implemented for glare.')
    if previous is not None:
        cop_1.setInput(0, previous)
    previous = cop_1
    # operation: color_correction kind=compositor_operation confidence=approximate
    # Color correction uses a COP2 color node when that type exists. The controls are not a match for Blender's compositor.
    cop_2 = _cop(cop, 'colorcorrect', 'color_correction', "Color correction uses a COP2 color node when that type exists. The controls are not a match for Blender's compositor.")
    if previous is not None:
        cop_2.setInput(0, previous)
    previous = cop_2
    # operation: vignette kind=compositor_operation confidence=unsupported
    # No reliable COP2 equivalent is implemented for ellipse_mask.
    cop_3 = _cop(cop, 'null', 'vignette', 'No reliable COP2 equivalent is implemented for ellipse_mask.')
    if previous is not None:
        cop_3.setInput(0, previous)
    previous = cop_3
    # operation: vignette_mix kind=compositor_operation confidence=approximate
    # mix is represented by a labeled COP null because no specific node is mapped.
    cop_4 = _cop(cop, 'null', 'vignette_mix', 'mix is represented by a labeled COP null because no specific node is mapped.')
    if previous is not None:
        cop_4.setInput(0, previous)
    previous = cop_4
    # operation: composite kind=compositor_operation confidence=exact
    # The compositor output is a null with the display flag set.
    cop_5 = _cop(cop, 'null', 'composite', 'The compositor output is a null with the display flag set.')
    if previous is not None:
        cop_5.setInput(0, previous)
    cop_5.setDisplayFlag(True)
    previous = cop_5
    cop.layoutChildren()
    return cop


if __name__ == '__main__':
    build()
