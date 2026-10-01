"""Houdini code generation, executed against the recording fake ``hou``."""

import ast

from helpers import G, compile_example, geometry_passthrough, run_script, socket

from nodebridge.compiler.pipeline import compile_document
from nodebridge.translation.confidence import Strictness


def network(result):
    hou = run_script(result.code.code, "hou")
    geo = next(n for n in hou.node("/obj").children())
    return hou, geo


def by_type(parent, node_type):
    return [n for n in parent.children() if n.type_name == node_type]


def source_of(node, index=0):
    item = node.inputs.get(index)
    return item[0] if item else None


def test_scatter_builds_a_native_sop_network():
    result = compile_example("scatter", "houdini")
    assert not result.diagnostics.errors
    hou, geo = network(result)
    assert geo.type_name == "geo" and geo.name() == "nb_scatter_rocks"
    types = {n.type_name for n in geo.children()}
    assert {"scatter", "copytopoints", "unpack", "merge", "xform", "sphere", "material", "attribwrangle", "switch", "object_merge"} <= types
    copy = by_type(geo, "copytopoints")[0]
    assert copy.parm_values["pack"] == 1
    assert source_of(copy, 0).type_name == "material", "instance geometry goes into input 0"
    points = source_of(copy, 1)
    assert points.type_name == "attribwrangle" and "p@orient" in points.parm_values["snippet"]
    scale_wrangle = source_of(points, 0)
    assert "v@scale" in scale_wrangle.parm_values["snippet"] and "nb_random" in scale_wrangle.parm_values["snippet"]
    out = geo.node("OUT")
    assert out.flags == {"display": True, "render": True}
    assert source_of(out).type_name == "merge"


def test_scatter_keeps_exposed_controls_live():
    result = compile_example("scatter", "houdini")
    hou, geo = network(result)
    assert geo.spare_parm_names() == ["density", "seed", "scale_min", "scale_max", "coverage", "use_source_object"]
    scatter = by_type(geo, "scatter")[0]
    assert scatter.expressions["densityscale"] == 'ch("../density")'
    assert "int(" in scatter.expressions["seed"]
    delete = next(n for n in by_type(geo, "attribwrangle") if "removepoint" in n.parm_values.get("snippet", ""))
    assert 'chf("../coverage")' in delete.parm_values["snippet"]


def test_material_from_set_material_is_built_in_mat():
    result = compile_example("scatter", "houdini")
    hou, geo = network(result)
    surfaces = [n for n in hou.node("/mat").children() if n.type_name == "mtlxstandard_surface"]
    assert [s.name() for s in surfaces] == ["procedural_rock"]
    assert set(surfaces[0].named_inputs) >= {"base_color", "specular_roughness", "normal"}
    material_sop = by_type(geo, "material")[0]
    assert material_sop.parm_values["shop_materialpath1"] == "/mat/procedural_rock"


def test_building_uses_subnet_with_promoted_parameters():
    result = compile_example("building", "houdini")
    hou, geo = network(result)
    subnet = by_type(geo, "subnet")[0]
    assert subnet.spare_parm_names() == ["width", "depth", "thickness"]
    assert subnet.expressions["width"] == '(ch("../width") + 0.6)'
    inner = {n.type_name for n in subnet.children()}
    assert inner == {"grid", "polyextrude", "output"}
    output = by_type(subnet, "output")[0]
    assert output.flags.get("display") is True
    extrude = by_type(subnet, "polyextrude")[0]
    assert extrude.expressions["dist"] == 'ch("../thickness")'
    line = by_type(geo, "line")[0]
    assert line.expressions["dist"] == '(ch("../floors") - 1) * abs(ch("../floor_height"))'
    assert line.expressions["dir[1]"] == 'ch("../floor_height")'
    mass = next(n for n in by_type(geo, "polyextrude"))
    assert mass.expressions["dist"] == '(ch("../floors") * ch("../floor_height"))'


def test_selection_fields_become_groups():
    result = compile_example("building", "houdini")
    hou, geo = network(result)
    scatter = by_type(geo, "scatter")[0]
    group = scatter.parm_values["group"]
    selection = source_of(scatter)
    assert selection.parm_values["class"] == 1
    snippet = selection.parm_values["snippet"]
    assert f'setprimgroup(0, "{group}"' in snippet and "prim_normal" in snippet and "abs(nb_sep" in snippet


def test_generated_scripts_are_readable_and_valid():
    for name in ("scatter", "building", "shader", "compositor"):
        result = compile_example(name, "houdini")
        code = result.code.code
        ast.parse(code)
        assert code.startswith('"""NodeBridge: generated Houdini Python.')
        assert "import hou" in code and "def build():" in code
        assert max(len(line) for line in code.splitlines() if "snippet" not in line and not line.startswith("    hou.")) < 260
        assert not [d for d in result.diagnostics.errors if d.code.startswith("script.")]


def test_vex_snippets_have_balanced_delimiters():
    for name in ("scatter", "building"):
        hou, geo = network(compile_example(name, "houdini"))
        for node in [n for n in hou.all_nodes() if n.type_name == "attribwrangle"]:
            snippet = node.parm_values["snippet"]
            for open_, close in ("()", "{}", "[]"):
                assert snippet.count(open_) == snippet.count(close), (node.name(), open_)
            code_lines = [l for l in snippet.splitlines() if l.strip() and not l.strip().startswith(("//", "#"))]
            assert all(l.rstrip().endswith((";", "{", "}")) for l in code_lines), node.name()


def test_strictness_replaces_operations_with_placeholders():
    result = compile_example("scatter", "houdini", strictness=Strictness.EXACT_ONLY)
    assert result.report.blocked
    hou, geo = network(result)
    placeholders = [n for n in geo.children() if n.name().startswith("UNSUPPORTED_")]
    assert placeholders and geo.notes
    assert any("Skipped by strictness" in note.text for note in geo.notes)


def test_unsupported_nodes_get_a_placeholder_and_a_note():
    builder = geometry_passthrough()
    builder.node("Weird", "GeometryNodeSomethingNew", inputs=[socket("Geometry", G)], outputs=[socket("Geometry", G, output=True)])
    builder.link("Group Input", "Socket_0", "Weird", "Geometry").link("Weird", "Geometry", "Group Output", "Socket_1")
    result = compile_document(builder.document(), "houdini")
    assert result.report.counts["UNSUPPORTED"] == 1
    hou, geo = network(result)
    placeholder = geo.node("UNSUPPORTED_weird")
    assert placeholder.type_name == "null" and source_of(placeholder).name() == "IN_Geometry"
    assert any("GeometryNodeSomethingNew" in note.text for note in geo.notes)


def test_options_toggle_comments_and_metadata():
    lean = compile_example("scatter", "houdini", include_comments=False, embed_metadata=False).code.code.split("def build_materials():")[1]
    rich = compile_example("scatter", "houdini").code.code.split("def build_materials():")[1]
    assert "nb_meta(" not in lean and "nb_meta(" in rich
    assert "nb_note(geo" not in lean and "nb_note(geo" in rich
    random_off = compile_example("scatter", "houdini", deterministic_random=False).code.code
    assert "nb_random(" not in random_off.split("def build():")[1]


def test_shader_and_compositor_targets():
    shader = run_script(compile_example("shader", "houdini").code.code, "hou")
    types = [n.type_name for n in shader.node("/mat").children()]
    assert types.count("mtlxmix") == 2, "three-stop ramp = two mixes"
    assert "mtlxheighttonormal" in types and "mtlxfractal3d" in types
    comp = run_script(compile_example("compositor", "houdini").code.code, "hou")
    net = comp.node("/img").children()[0]
    assert net.type_name == "img" and any(n.type_name == "colorcorrect" for n in net.children())
