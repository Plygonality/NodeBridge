"""OpenUSD integration tests. Skipped when pxr is not installed.

These tests build small stages with the official pxr API. They do not
claim a live Houdini, Unreal, or Blender session.
"""

import json
import shutil
from pathlib import Path

import pytest

from nodebridge.cli import main
from nodebridge.compiler.pipeline import analyze, generate
from nodebridge.interchange.bundle import PackageInputs, publish_package
from nodebridge.interchange.compare import Verdict
from nodebridge.interchange.usd.inspect import inspect_stage
from nodebridge.interchange.validate import validate_bundle
from nodebridge.ir.serialization import dumps_semantic, loads_graph

pxr = pytest.importorskip("pxr")

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "examples" / "building" / "building.graph.json"


def _sidecars(tmp_path: Path):
    document = loads_graph(GRAPH.read_text(encoding="utf-8"))
    result = analyze(document, "houdini")
    generate(result)
    semantic = tmp_path / "semantic.json"
    report = tmp_path / "report.json"
    script = tmp_path / "houdini.py"
    semantic.write_text(dumps_semantic(result.semantic), encoding="utf-8")
    report.write_text(json.dumps(result.report.as_dict()), encoding="utf-8")
    script.write_text(result.code.code, encoding="utf-8")
    return semantic, report, script


def _cube(path: Path, *, translate=(0, 0, 0), size=2.0, default_name="World"):
    stage = pxr.Usd.Stage.CreateNew(str(path))
    pxr.UsdGeom.SetStageUpAxis(stage, pxr.UsdGeom.Tokens.z)
    pxr.UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    root = pxr.UsdGeom.Xform.Define(stage, f"/{default_name}")
    pxr.Usd.ModelAPI(root.GetPrim()).SetKind(pxr.Kind.Tokens.component)
    stage.SetDefaultPrim(root.GetPrim())
    if translate != (0, 0, 0):
        root.AddTranslateOp().Set(translate)
    cube = pxr.UsdGeom.Cube.Define(stage, f"/{default_name}/Body")
    cube.CreateSizeAttr(size)
    stage.GetRootLayer().Save()
    return path


def _mesh(path: Path, points, counts, indices):
    stage = pxr.Usd.Stage.CreateNew(str(path))
    pxr.UsdGeom.SetStageUpAxis(stage, pxr.UsdGeom.Tokens.z)
    pxr.UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    root = pxr.UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(root.GetPrim())
    mesh = pxr.UsdGeom.Mesh.Define(stage, "/World/Body")
    mesh.CreatePointsAttr(points)
    mesh.CreateFaceVertexCountsAttr(counts)
    mesh.CreateFaceVertexIndicesAttr(indices)
    mesh.CreateSubdivisionSchemeAttr("none")
    stage.GetRootLayer().Save()
    return path


def test_inspect_cube_reports_units_bounds_and_counts(tmp_path):
    path = _cube(tmp_path / "cube.usdc")
    summary = inspect_stage(path)
    assert summary.status == "open"
    assert summary.default_prim == "/World"
    assert summary.up_axis == "Z"
    assert summary.up_axis_authored
    assert summary.meters_per_unit == pytest.approx(1.0)
    assert summary.mesh_count == 1
    assert summary.xform_count == 1
    assert summary.missing == []
    assert summary.bounds_min == pytest.approx((-1, -1, -1))
    assert summary.bounds_max == pytest.approx((1, 1, 1))
    kinds = {prim.path: prim.usd_kind for prim in summary.prims}
    assert kinds["/World"] == "component"


def test_layered_bundle_survives_a_move_and_records_provenance(tmp_path):
    semantic, report, script = _sidecars(tmp_path)
    scene = _cube(tmp_path / "evaluated.usdc")
    output = tmp_path / "Building.nodebridge"
    manifest = publish_package(
        PackageInputs(
            scene=scene,
            graph=GRAPH,
            semantic=semantic,
            output=output,
            report_json=report,
            scripts={"houdini": script},
            layered=True,
            procedural=True,
            publisher="cli",
        )
    )
    report_validation = validate_bundle(output)
    assert report_validation.ok, report_validation.errors
    assert (output / "scene.usda").is_file()
    assert (output / "geometry" / "evaluated.usdc").is_file()
    assert manifest.scene["composition"] == "layered"
    moved = tmp_path / "relocated" / "Building.nodebridge"
    shutil.copytree(output, moved)
    summary = inspect_stage(moved / "scene.usda")
    assert summary.status == "open", summary.error
    assert summary.missing == []
    assert any(reference.endswith("evaluated.usdc") for reference in summary.references)
    assert summary.mesh_count == 1
    tagged = [prim for prim in summary.prims if prim.generator_id]
    assert tagged and tagged[0].generator_id == manifest.source["generator_id"]
    procedural = [prim for prim in summary.prims if prim.type_name == "GenerativeProcedural"]
    assert procedural, "experimental UsdProc marker should be present"
    text = (moved / "scene.usda").read_text(encoding="utf-8")
    assert "nodebridge" in text
    assert str(tmp_path) not in text


def test_material_binding_is_reported_when_the_stage_has_one(tmp_path):
    path = tmp_path / "shaded.usda"
    stage = pxr.Usd.Stage.CreateNew(str(path))
    pxr.UsdGeom.SetStageUpAxis(stage, pxr.UsdGeom.Tokens.z)
    pxr.UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    root = pxr.UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(root.GetPrim())
    mesh = pxr.UsdGeom.Mesh.Define(stage, "/World/Body")
    mesh.CreatePointsAttr([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)])
    mesh.CreateFaceVertexCountsAttr([4])
    mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    material = pxr.UsdShade.Material.Define(stage, "/World/Looks/Preview")
    pxr.UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
    stage.GetRootLayer().Save()
    summary = inspect_stage(path)
    body = next(prim for prim in summary.prims if prim.path == "/World/Body")
    assert body.material_path == "/World/Looks/Preview"
    assert summary.material_count == 1
    assert body.point_count == 4
    assert body.face_count == 1


def test_missing_reference_and_malformed_stage(tmp_path):
    broken = tmp_path / "broken.usda"
    stage = pxr.Usd.Stage.CreateNew(str(broken))
    pxr.UsdGeom.Xform.Define(stage, "/World").GetPrim().GetReferences().AddReference("./missing.usdc")
    stage.GetRootLayer().Save()
    summary = inspect_stage(broken)
    assert summary.status == "open"
    assert summary.missing
    malformed = tmp_path / "malformed.usda"
    malformed.write_text("this is not a usd stage\n", encoding="utf-8")
    failed = inspect_stage(malformed)
    assert failed.status == "error"
    assert main(["usd", "validate", str(broken)]) == 1
    assert main(["usd", "validate", str(malformed)]) == 1


def test_compare_match_transform_bounds_and_inconclusive(tmp_path, capsys):
    source = _cube(tmp_path / "source.usdc")
    identical = _cube(tmp_path / "identical.usdc")
    moved = _cube(tmp_path / "moved.usdc", translate=(2, 0, 0))
    larger = _mesh(
        tmp_path / "larger.usdc",
        points=[(0, 0, 0), (4, 0, 0), (4, 1, 0), (0, 1, 0)],
        counts=[4],
        indices=[0, 1, 2, 3],
    )
    renamed = _cube(tmp_path / "renamed.usdc", default_name="Other")
    assert main(["usd", "compare", str(source), str(identical), "--json"]) == 0
    match = json.loads(capsys.readouterr().out)
    assert match["verdict"] == Verdict.MATCH.value
    assert main(["usd", "compare", str(source), str(moved), "--json"]) == 0
    translated = json.loads(capsys.readouterr().out)
    assert translated["verdict"] == Verdict.DIFFERENCE.value
    assert translated["transform_differences"]
    assert main(["usd", "compare", str(source), str(larger), "--json"]) == 0
    geometry = json.loads(capsys.readouterr().out)
    assert geometry["verdict"] == Verdict.DIFFERENCE.value
    assert geometry["bounds_differences"] or geometry["topology_differences"]
    assert main(["usd", "compare", str(source), str(renamed), "--json"]) == 0
    unknown = json.loads(capsys.readouterr().out)
    assert unknown["verdict"] == Verdict.INCONCLUSIVE.value


def test_basic_bundle_provenance_overlay_resolves_inside_the_bundle(tmp_path):
    semantic, report, script = _sidecars(tmp_path)
    scene = _cube(tmp_path / "evaluated.usdc")
    output = tmp_path / "Basic.nodebridge"
    publish_package(
        PackageInputs(scene=scene, graph=GRAPH, semantic=semantic, output=output, report_json=report, scripts={"houdini": script}, annotate=True)
    )
    overlay = output / "procedural" / "provenance.usda"
    assert overlay.is_file()
    # The Blender-exported file is not rewritten; the crate has no NodeBridge customData key.
    crate = (output / "scene.usdc").read_bytes()
    assert b"nodebridge" not in crate
    summary = inspect_stage(overlay)
    assert summary.missing == []
    assert summary.mesh_count == 1
    assert any(prim.generator_id for prim in summary.prims)
    assert validate_bundle(output).ok
