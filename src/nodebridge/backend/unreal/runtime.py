"""Helpers embedded in generated Unreal Editor Python.

APIs used (Unreal Python Editor Script Plugin):
``unreal.AssetToolsHelpers.get_asset_tools().create_asset``,
``unreal.EditorAssetLibrary`` (does_asset_exist, make_directory,
load_asset, save_loaded_asset), ``unreal.PCGGraph.add_node_of_type`` /
``add_edge`` / ``get_input_node`` / ``get_output_node`` (experimental,
editor-only), ``unreal.MaterialEditingLibrary``,
``unreal.EditorActorSubsystem.spawn_actor_from_class``.

``add_edge`` returns None when a pin label does not exist, so pins are
tried from a list of candidates. Anything this Unreal version does not
expose is recorded in NB_WARNINGS rather than raising.
"""

HELPERS = '''
NB_WARNINGS = []


def nb_unique_asset_name(path, name):
    candidate, index = name, 1
    while unreal.EditorAssetLibrary.does_asset_exist("%s/%s" % (path, candidate)):
        index += 1
        candidate = "%s_%d" % (name, index)
    return candidate


def nb_create_asset(name, path, asset_class, factory):
    """Create a new asset; never overwrites an existing one."""
    unreal.EditorAssetLibrary.make_directory(path)
    name = nb_unique_asset_name(path, name)
    asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, path, asset_class, factory)
    if asset is None:
        raise RuntimeError("NodeBridge could not create %s/%s" % (path, name))
    return asset


def nb_class(name):
    cls = getattr(unreal, name, None)
    if cls is None:
        NB_WARNINGS.append("unreal.%s is not available in this Unreal version" % name)
    return cls


def nb_enum(enum_name, *candidates):
    enum = getattr(unreal, enum_name, None)
    for candidate in candidates:
        if enum is not None and hasattr(enum, candidate):
            return getattr(enum, candidate)
    NB_WARNINGS.append("unreal.%s has none of %s" % (enum_name, ", ".join(candidates)))
    return None


def nb_prop(obj, name, value):
    """set_editor_property with a warning instead of an exception."""
    if obj is None or value is None:
        return False
    try:
        obj.set_editor_property(name, value)
        return True
    except Exception as exc:
        NB_WARNINGS.append("%s.%s: %s" % (type(obj).__name__, name, exc))
        return False
'''

PCG_HELPERS = '''

def nb_pcg_node(graph, settings_class_name, x, y):
    settings_class = nb_class(settings_class_name)
    if settings_class is None:
        return None, None
    node, settings = graph.add_node_of_type(settings_class)
    try:
        node.set_node_position(x, y)
    except Exception:
        pass
    return node, settings


def nb_edge(graph, source, source_pins, target, target_pins):
    """Connect two PCG nodes, trying known pin labels across UE versions."""
    if source is None or target is None:
        return False
    for source_pin in source_pins:
        for target_pin in target_pins:
            if graph.add_edge(source, source_pin, target, target_pin) is not None:
                return True
    NB_WARNINGS.append("could not connect %s -> %s (pins %s / %s)" % (source_pins, target_pins, source_pins, target_pins))
    return False


def nb_spawner_mesh(settings, mesh_path, material=None):
    """Point a Static Mesh Spawner at one mesh (UE 5.2+ descriptor API, 5.0/5.1 fallback)."""
    mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
    if mesh is None:
        NB_WARNINGS.append("static mesh %s not found; assign one on the Static Mesh Spawner" % mesh_path)
        return False
    try:
        settings.set_mesh_selector_type(unreal.PCGMeshSelectorWeighted)
    except Exception:
        nb_prop(settings, "mesh_selector_type", getattr(unreal, "PCGMeshSelectorWeighted", None))
    selector = settings.get_editor_property("mesh_selector_parameters")
    entry = unreal.PCGMeshSelectorWeightedEntry()
    try:
        descriptor = entry.get_editor_property("descriptor")
        descriptor.set_editor_property("static_mesh", mesh)
        if material is not None:
            descriptor.set_editor_property("override_materials", [material])
        entry.set_editor_property("descriptor", descriptor)
    except Exception:
        nb_prop(entry, "mesh", mesh)
    nb_prop(entry, "weight", 1)
    return nb_prop(selector, "mesh_entries", [entry])
'''

MATERIAL_HELPERS = '''

MEL = unreal.MaterialEditingLibrary


def nb_expression(material, class_name, x, y):
    cls = nb_class(class_name)
    if cls is None:
        return None
    return MEL.create_material_expression(material, cls, x, y)


def nb_link(source, source_output, target, target_input):
    if source is None or target is None:
        return False
    if not MEL.connect_material_expressions(source, source_output, target, target_input):
        NB_WARNINGS.append("could not connect %s.%s -> %s.%s" % (type(source).__name__, source_output, type(target).__name__, target_input))
        return False
    return True


def nb_output(source, source_output, material_property):
    if source is None or material_property is None:
        return False
    if not MEL.connect_material_property(source, source_output, material_property):
        NB_WARNINGS.append("could not connect %s to %s" % (type(source).__name__, material_property))
        return False
    return True
'''
