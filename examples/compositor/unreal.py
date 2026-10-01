"""NodeBridge Unreal compositor fallback.

Source: Compositor / GradeAndGlare
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
    # Glare, vignette masks, and most filters have no honest Unreal material equivalent here.
    # Color operations are written into a material the user can assign to a post-process volume.
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    material = tools.create_asset('NB_gradeandglare', package_path, unreal.Material, unreal.MaterialFactoryNew())
    if material is None:
        raise RuntimeError('Could not create compositor fallback material')
    library = unreal.MaterialEditingLibrary
    # operation: render_layers kind=compositor_operation confidence=unsupported
    # No Unreal compositor equivalent is implemented for render_layer.
    # operation: glare kind=compositor_operation confidence=unsupported
    # No Unreal compositor equivalent is implemented for glare.
    # operation: color_correction kind=compositor_operation confidence=approximate
    # brightness is approximated by a post-process material constant. It is not the Blender compositor.
    color = library.create_material_expression(material, unreal.MaterialExpressionConstant3Vector, -300, 0)
    color.set_editor_property('constant', unreal.LinearColor(1.0, 1.0, 1.0, 1.0))
    library.connect_material_property(color, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    # operation: vignette kind=compositor_operation confidence=unsupported
    # No Unreal compositor equivalent is implemented for ellipse_mask.
    # operation: vignette_mix kind=compositor_operation confidence=approximate
    # mix is approximated by a post-process material constant. It is not the Blender compositor.
    # operation: composite kind=compositor_operation confidence=unsupported
    # No Unreal compositor equivalent is implemented for composite_output.
    library.recompile_material(material)
    unreal.EditorAssetLibrary.save_asset(material.get_path_name())
    return material


if __name__ == '__main__':
    build()
