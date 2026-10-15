from types import SimpleNamespace

from nodebridge.addon.context import resolve_source
from nodebridge.addon.settings import options_from_settings
from nodebridge.translation.confidence import Strictness


def test_geometry_editor_wins_over_the_modifier():
    tree = SimpleNamespace(name="BuildingGenerator", bl_idname="GeometryNodeTree")
    modifier = SimpleNamespace(type="NODES", name="GeometryNodes", node_group=SimpleNamespace(name="Other"))
    context = SimpleNamespace(
        space_data=SimpleNamespace(type="NODE_EDITOR", tree_type="GeometryNodeTree", edit_tree=tree, node_tree=tree),
        object=SimpleNamespace(name="Wall", modifiers=[modifier], active_material=None),
        scene=SimpleNamespace(),
    )
    selection = resolve_source(context, "auto")
    assert selection.system == "geometry_nodes"
    assert selection.detail == "BuildingGenerator"
    assert selection.source is tree


def test_modifier_is_used_outside_the_node_editor():
    group = SimpleNamespace(name="Scatter")
    modifier = SimpleNamespace(type="NODES", name="GeometryNodes", node_group=group)
    context = SimpleNamespace(
        space_data=SimpleNamespace(type="VIEW_3D"),
        object=SimpleNamespace(name="Tree", modifiers=[modifier], active_material=None),
        scene=SimpleNamespace(),
    )
    selection = resolve_source(context, "auto")
    assert selection.source is modifier
    assert selection.detail == "Tree / Scatter"


def test_shader_and_compositor_contexts():
    shader = SimpleNamespace(name="Metal")
    material = SimpleNamespace(name="Metal", node_tree=shader)
    context = SimpleNamespace(
        space_data=SimpleNamespace(type="NODE_EDITOR", tree_type="ShaderNodeTree", edit_tree=shader),
        object=SimpleNamespace(name="Sphere", modifiers=[], active_material=material),
        scene=SimpleNamespace(name="Scene", compositing_node_group=SimpleNamespace(name="Comp")),
    )
    assert resolve_source(context, "shader").source is shader
    assert resolve_source(context, "compositor").detail == "Comp"


def test_missing_tree_explains_what_to_open():
    context = SimpleNamespace(space_data=None, object=None, scene=SimpleNamespace())
    selection = resolve_source(context, "auto")
    assert selection.source is None
    assert "Geometry Nodes" in selection.detail


def test_panel_settings_map_onto_compile_options():
    settings = SimpleNamespace(
        strictness="exact_only",
        include_comments=False,
        preserve_names=True,
        organized_layout=True,
        embed_metadata=False,
        deterministic_random=True,
        debug_output=True,
    )
    options = options_from_settings(settings)
    assert options.strictness is Strictness.EXACT_ONLY
    assert options.include_comments is False
    assert options.fallback is None
