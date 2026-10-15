"""Unreal Editor Python generation, executed against the recording fake ``unreal``."""

import ast

from helpers import compile_example, run_script


def test_scatter_builds_a_wired_pcg_graph():
    result = compile_example("scatter", "unreal")
    fake = run_script(result.code.code, "unreal")
    state = fake.STATE
    assert "/Game/NodeBridge/PCG_ScatterRocks" in state["assets"]
    chain = [edge[2] for edge in state["edges"]]
    assert chain == [
        "PCGSurfaceSamplerSettings",
        "PCGSpatialNoiseSettings",
        "PCGDensityFilterSettings",
        "PCGTransformPointsSettings",
        "PCGTransformPointsSettings",
        "PCGTransformPointsSettings",
        "PCGStaticMeshSpawnerSettings",
        "PCGMergeSettings",
        "_output",
    ]
    assert state["edges"][0][:2] == ("_input", "Input"), "falls back across pin labels"
    assert state["warnings"] == []


def test_pcg_settings_use_controls_and_converted_rotations():
    code = compile_example("scatter", "unreal").code.code
    assert "DENSITY = 4.0" in code and '"points_per_squared_meter", DENSITY' in code
    assert "unreal.Vector(SCALE_MIN, SCALE_MIN, SCALE_MIN)" in code
    assert "yaw=-360.0" in code, "Blender +Z rotation range maps to negative yaw"
    assert '"/Engine/BasicShapes/Sphere.Sphere"' in code
    assert "unreal.Vector(0.5, 0.5, 0.3)" in code, "ico sphere radius 0.25 and Z scale 0.6 become the mesh size"
    assert "0.3 + (COVERAGE - 0.0) / 1.0 * 0.4" in code, "threshold mapped back through Map Range"


def test_scatter_material_is_created_and_assigned():
    result = compile_example("scatter", "unreal")
    fake = run_script(result.code.code, "unreal")
    assert "/Game/NodeBridge/M_ProceduralRock" in fake.STATE["assets"]
    assert "materials.get('ProceduralRock')" in result.code.code


def test_building_reports_pcg_limits_honestly():
    result = compile_example("building", "unreal")
    unsupported = {e.kind for e in result.report.entries if e.classification.confidence.value == "UNSUPPORTED"}
    assert {"EXTRUDE", "PRIMITIVE"} <= unsupported
    fake = run_script(result.code.code, "unreal")
    assert any("Building Mass" in w for w in fake.STATE["warnings"])


def test_shader_becomes_material_with_parameters():
    result = compile_example("shader", "unreal")
    fake = run_script(result.code.code, "unreal")
    expressions = fake.STATE["expressions"]
    assert "MaterialExpressionScalarParameter" in expressions, "labeled Value node is a material parameter"
    assert expressions.count("MaterialExpressionLinearInterpolate") >= 3
    assert {"MaterialExpressionNoise", "MaterialExpressionDDX", "MaterialExpressionLocalPosition"} <= set(expressions)
    properties = {prop for _, prop in fake.STATE["outputs"]}
    assert {"MP_BASE_COLOR", "MP_ROUGHNESS", "MP_NORMAL"} <= properties
    assert "'Roughness Scale'" in result.code.code


def test_compositor_becomes_post_process_volume():
    result = compile_example("compositor", "unreal")
    fake = run_script(result.code.code, "unreal")
    assert len(fake.STATE["actors"]) == 1
    settings = fake.STATE["actors"][0].get_editor_property("settings")
    assert settings._props["override_bloom_intensity"] is True
    assert settings._props["vignette_intensity"] == 0.6
    assert "override_color_gain" in settings._props


def test_unreal_scripts_parse_and_are_self_describing():
    for name in ("scatter", "building", "shader", "compositor"):
        code = compile_example(name, "unreal").code.code
        ast.parse(code)
        assert code.startswith('"""NodeBridge: generated Unreal Editor Python.') and "import unreal" in code
        assert "create_asset(name, path" in code or name == "compositor"
