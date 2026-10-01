"""NodeBridge Houdini material.

Source: Shader / WeatheredMetal
Target: Houdini Material Builder

Paste into the Houdini Python Source Editor and run.
Noise and color-ramp patterns are approximate, not pixel-identical.
"""

import hou

def _set(node, name, value):
    parm = node.parm(name)
    if parm is not None:
        parm.set(value)

def _set_tuple(node, name, value):
    parm = node.parmTuple(name)
    if parm is not None:
        parm.set(value)

def _wire(destination, input_name, source):
    try:
        destination.setNamedInput(input_name, source, 0)
    except hou.OperationFailed:
        destination.setComment((destination.comment() or '') + f"\nConnect {source.name()} to {input_name}.")

def build(parent=None):
    matnet = parent or hou.node('/mat')
    if matnet is None:
        raise hou.Error('NodeBridge could not find /mat.')
    builder = matnet.createNode('materialbuilder', 'NB_weatheredmetal')
    principled = None
    for child in builder.children():
        if 'principledshader' in child.type().name():
            principled = child
            break
    if principled is None:
        principled = builder.createNode('principledshader::2.0', 'principled')
    # operation: texture_coordinate kind=attribute_read confidence=approximate
    # Texture Coordinate (attribute_read) has no dedicated material-builder node in this translator.
    noise_vop = builder.createNode('noise', 'noise')
    _set(noise_vop, 'scale', 5.0)
    _wire(principled, 'basecolor', noise_vop)
    # Color ramp stops from Blender: [{'position': 0.0, 'color': [0.05, 0.05, 0.05, 1.0]}, {'position': 1.0, 'color': [0.8, 0.45, 0.2, 1.0]}]
    ramp = builder.createNode('ramp', 'color_ramp')
    _wire(ramp, 'input', noise_vop)
    # operation: roughness_range kind=map_range confidence=approximate
    # Roughness Range (map_range) has no dedicated material-builder node in this translator.
    # operation: bump kind=shader_operation confidence=approximate
    # Bump (shader_operation) has no dedicated material-builder node in this translator.
    _set_tuple(principled, 'basecolor', (0.8, 0.8, 0.8))
    _set(principled, 'rough', 0.5)
    _set(principled, 'metallic', 0.0)
    surface = None
    for child in builder.children():
        if 'output' in child.type().name() or child.name() == 'surface_output':
            surface = child
            break
    if surface is not None:
        _wire(surface, 'surface', principled)
    builder.layoutChildren()
    return builder

    # operation: noise_texture kind=noise confidence=approximate
    # Houdini noise does not reproduce Blender's noise texture.
    # operation: color_ramp kind=color_operation confidence=approximate
    # Color ramp stops are recorded in a comment. The ramp VOP uses its default keys unless you edit them.
    # operation: principled_bsdf kind=shader_operation confidence=equivalent
    # Principled BSDF parameters are written onto the principled shader inside the material builder.
    # operation: material_output kind=shader_operation confidence=exact
    # Material Output connects the principled shader to the surface output.

if __name__ == '__main__':
    build()
