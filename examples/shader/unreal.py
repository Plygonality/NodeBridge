"""NodeBridge Unreal material.

Source: Shader / WeatheredMetal
Target: Unreal Editor Python

Run inside the Unreal Editor with the Python Editor Script plugin enabled.
PCG graphs also need the PCG plugin. Materials use MaterialEditingLibrary.
This builds a native asset. It does not import baked geometry.
Equivalent results are procedurally related, not numerically identical.
"""

import unreal

def _nb_i32(value):
    value &= 0xFFFFFFFF
    if value & 0x80000000:
        value -= 0x100000000
    return value

def _nb_lshr(value, bits):
    return _nb_i32(value) >> bits & ((1 << (32 - bits)) - 1)

def nb_hash(seed, element_id):
    x = _nb_i32(_nb_i32(seed) ^ _nb_i32(_nb_i32(element_id) * 747796405 + (-1403630843)))
    x = _nb_i32(_nb_i32(x ^ _nb_lshr(x, 16)) * (-2048144777))
    x = _nb_i32(_nb_i32(x ^ _nb_lshr(x, 13)) * (-1028477379))
    return _nb_i32(x ^ _nb_lshr(x, 16))

def nb_rand(seed, element_id):
    return (nb_hash(seed, element_id) & 16777215) / 16777216.0

def _try_set(settings, name, value):
    if settings is None:
        return False
    try:
        settings.set_editor_property(name, value)
        return True
    except Exception as exc:
        unreal.log_warning(f'NodeBridge: could not set {name} on {settings.get_class().get_name()}: {exc}')
        return False

def _pin_labels(node, which):
    labels = []
    try:
        pins = node.get_editor_property(which)
    except Exception:
        return labels
    for pin in pins:
        try:
            props = pin.get_editor_property('properties')
            labels.append(str(props.get_editor_property('label')))
        except Exception:
            continue
    return labels

def _connect(graph, source, source_labels, target, target_labels):
    if source is None or target is None:
        unreal.log_warning('NodeBridge: skipped a connection because a node was missing.')
        return False
    outputs = _pin_labels(source, 'output_pins')
    inputs = _pin_labels(target, 'input_pins')
    source_label = next((label for label in source_labels if label in outputs), outputs[0] if outputs else None)
    target_label = next((label for label in target_labels if label in inputs), inputs[0] if inputs else None)
    if source_label is None or target_label is None:
        unreal.log_warning(
            f'NodeBridge: could not connect {source_labels} -> {target_labels}. '
            f'outputs={outputs} inputs={inputs}'
        )
        return False
    graph.add_edge(source, source_label, target, target_label)
    return True

def _add(graph, class_name, x, y):
    settings_cls = getattr(unreal, class_name, None)
    if settings_cls is None:
        unreal.log_error(f'NodeBridge: {class_name} is not available in this Unreal Python build.')
        return None, None
    node, settings = graph.add_node_of_type(settings_cls)
    node.set_node_position(x, y)
    return node, settings

def build(package_path='/Game/NodeBridge'):
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    factory = unreal.MaterialFactoryNew()
    material = tools.create_asset('NB_weatheredmetal', package_path, unreal.Material, factory)
    if material is None:
        raise RuntimeError('Could not create material NB_weatheredmetal')
    library = unreal.MaterialEditingLibrary
    # operation: texture_coordinate kind=attribute_read confidence=approximate
    # Texture Coordinate has no dedicated material expression in this translator.
    # operation: noise_texture kind=noise confidence=approximate
    noise_expr = library.create_material_expression(material, unreal.MaterialExpressionNoise, -700, 0)
    _try_set(noise_expr, 'scale', 5.0)
    library.connect_material_property(noise_expr, '', unreal.MaterialProperty.MP_BASE_COLOR)
    # operation: color_ramp kind=color_operation confidence=approximate
    # Color ramp stops: [{'position': 0.0, 'color': [0.05, 0.05, 0.05, 1.0]}, {'position': 1.0, 'color': [0.8, 0.45, 0.2, 1.0]}]
    lerp_expr = library.create_material_expression(material, unreal.MaterialExpressionLinearInterpolate, -500, 200)
    # operation: roughness_range kind=map_range confidence=approximate
    # Roughness Range has no dedicated material expression in this translator.
    # operation: bump kind=shader_operation confidence=approximate
    # Bump has no dedicated material expression in this translator.
    # operation: principled_bsdf kind=shader_operation confidence=equivalent
    color_expr = library.create_material_expression(material, unreal.MaterialExpressionConstant3Vector, -400, 0)
    color_expr.set_editor_property('constant', unreal.LinearColor(0.8, 0.8, 0.8, 1.0))
    library.connect_material_property(color_expr, '', unreal.MaterialProperty.MP_BASE_COLOR)
    rough_expr = library.create_material_expression(material, unreal.MaterialExpressionScalarParameter, -400, 180)
    rough_expr.set_editor_property('parameter_name', 'Roughness')
    rough_expr.set_editor_property('default_value', 0.5)
    library.connect_material_property(rough_expr, '', unreal.MaterialProperty.MP_ROUGHNESS)
    metal_expr = library.create_material_expression(material, unreal.MaterialExpressionScalarParameter, -400, 320)
    metal_expr.set_editor_property('parameter_name', 'Metallic')
    metal_expr.set_editor_property('default_value', 0.0)
    library.connect_material_property(metal_expr, '', unreal.MaterialProperty.MP_METALLIC)
    # operation: material_output kind=shader_operation confidence=exact
    # Material Output is the material root. Expressions above are connected to material properties.
    library.recompile_material(material)
    unreal.EditorAssetLibrary.save_asset(material.get_path_name())
    return material


if __name__ == '__main__':
    build()
