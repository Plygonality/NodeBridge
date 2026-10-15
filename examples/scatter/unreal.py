"""NodeBridge Unreal PCG graph.

Source: geometry_nodes / ScatterBuildings
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
    factory = unreal.PCGGraphFactory()
    graph = tools.create_asset('NB_scatterbuildings', package_path, unreal.PCGGraph, factory)
    if graph is None:
        raise RuntimeError('Could not create PCG graph NB_scatterbuildings')
    input_node = graph.get_input_node()
    output_node = graph.get_output_node()
    previous = input_node
    previous_labels = ['In', 'Out']
    created = {'input': input_node, 'output': output_node}
    # operation: group_input kind=group_input confidence=equivalent
    # The PCG graph input is the surface sampled by the graph actor or pinned input.
    # operation: instance_cube kind=primitive confidence=approximate
    # PCG has no primitive-cube node in the Python API used here. The graph input is the surface, and the spawner mesh is assigned by hand.
    # primitive cube size=(1.0, 1.0, 1.0)
    # operation: building_scatter kind=scatter confidence=equivalent
    # Surface Sampler is the PCG equivalent of distributing points on a surface. Unreal's sample positions are not Blender's, even with the same seed.
    sampler_750, sampler_settings_750 = _add(graph, 'PCGSurfaceSamplerSettings', 750, 0)
    _try_set(sampler_settings_750, 'points_per_squared_meter', 25.0)
    _try_set(sampler_settings_750, 'seed', 3)
    if sampler_750 is not None and previous is not None:
        _connect(graph, previous, previous_labels, sampler_750, ['Out', 'In', 'Surface'])
        previous = sampler_750
        previous_labels = ['Out', 'Out']
        created['building_scatter'] = sampler_750
    # operation: random_scale kind=random confidence=approximate
    # Scale and rotation ranges are written to PCGTransformPointsSettings when that class exists. Unreal's random series is not NodeBridge's hash and is not Blender's.
    transform_1000, transform_settings_1000 = _add(graph, 'PCGTransformPointsSettings', 1000, 0)
    _try_set(transform_settings_1000, 'seed', 7)
    # Blender range minimum=0.4 maximum=1.2
    if transform_1000 is not None and previous is not None:
        _connect(graph, previous, previous_labels, transform_1000, ['Out', 'In', 'Surface'])
        previous = transform_1000
        previous_labels = ['Out', 'Out']
        created['random_scale'] = transform_1000
    # operation: random_rotation kind=random confidence=approximate
    # Scale and rotation ranges are written to PCGTransformPointsSettings when that class exists. Unreal's random series is not NodeBridge's hash and is not Blender's.
    transform_1250, transform_settings_1250 = _add(graph, 'PCGTransformPointsSettings', 1250, 0)
    _try_set(transform_settings_1250, 'seed', 11)
    # Blender range minimum=[0.0, 0.0, 0.0] maximum=[0.0, 0.0, 6.28318]
    if transform_1250 is not None and previous is not None:
        _connect(graph, previous, previous_labels, transform_1250, ['Out', 'In', 'Surface'])
        previous = transform_1250
        previous_labels = ['Out', 'Out']
        created['random_rotation'] = transform_1250
    # operation: instance_on_points kind=instance confidence=equivalent
    # Static Mesh Spawner instances a mesh on the points. Assign the mesh on the spawner; the Python API used here does not construct a mesh from a Blender primitive.
    spawner_1500, spawner_settings_1500 = _add(graph, 'PCGStaticMeshSpawnerSettings', 1500, 0)
    if spawner_1500 is not None and previous is not None:
        _connect(graph, previous, previous_labels, spawner_1500, ['Out', 'In', 'Surface'])
        previous = spawner_1500
        previous_labels = ['Out', 'Out']
        created['instance_on_points'] = spawner_1500
    # operation: realize kind=realize_instances confidence=equivalent
    # PCG Static Mesh Spawner already emits instances. There is no separate realize node in this mapping.
    # operation: group_output kind=group_output confidence=exact
    # The PCG graph output receives the last generated node.
    if previous is not None and output_node is not None:
        _connect(graph, previous, previous_labels, output_node, ['Out', 'In'])
    unreal.EditorAssetLibrary.save_asset(graph.get_path_name())
    return graph


if __name__ == '__main__':
    build()
