"""Bundle manifests, provenance, and CLI behavior without requiring a live DCC.

pxr may be installed. Tests that require it to be absent monkeypatch the
availability check. Tests that need a real stage live in test_usd_pxr.py.
"""

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from nodebridge import __version__
from nodebridge.cli import main
from nodebridge.compiler.pipeline import analyze, generate
from nodebridge.interchange.bundle import PackageInputs, publish_package
from nodebridge.interchange.compare import PrimSummary, StageSummary, Verdict, compare_summaries
from nodebridge.interchange.errors import BundleError, PathSecurityError
from nodebridge.interchange.manifest import BUNDLE_FORMAT_VERSION, dumps_manifest, loads_manifest
from nodebridge.interchange.provenance import content_hash, generator_id, group_id, operation_id
from nodebridge.interchange.validate import validate_bundle
from nodebridge.ir.serialization import FORMAT_VERSION, dumps_semantic, loads_graph

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "examples" / "building" / "building.graph.json"
SCENE = ROOT / "examples" / "openusd" / "cube.usda"
SRC = ROOT / "src" / "nodebridge"


def _sidecars(tmp_path: Path):
    document = loads_graph(GRAPH.read_text(encoding="utf-8"))
    result = analyze(document, "houdini")
    generate(result)
    semantic = tmp_path / "generator.semantic.json"
    report = tmp_path / "report.json"
    report_text = tmp_path / "report.txt"
    script = tmp_path / "houdini.py"
    semantic.write_text(dumps_semantic(result.semantic), encoding="utf-8")
    report.write_text(json.dumps(result.report.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_text.write_text(result.report.to_text(), encoding="utf-8")
    script.write_text(result.code.code, encoding="utf-8")
    return semantic, report, report_text, script


def _package(tmp_path: Path, output: Path, **kwargs):
    semantic, report, report_text, script = _sidecars(tmp_path)
    return publish_package(
        PackageInputs(
            scene=SCENE,
            graph=GRAPH,
            semantic=semantic,
            output=output,
            report_json=report,
            report_text=report_text,
            scripts={"houdini": script},
            export_settings={"tool": "test"},
            **kwargs,
        )
    )


def test_ir_format_version_is_unchanged():
    assert FORMAT_VERSION == 1
    assert BUNDLE_FORMAT_VERSION == 1


def test_generator_ids_are_stable_and_distinguish_collisions():
    base = dict(dcc="Blender", tree="BuildingGenerator", object_name="Building", modifier="NodeBridge Example")
    assert generator_id(**base) == generator_id(**base)
    assert generator_id(**base) != generator_id(**dict(base, object_name="Other"))
    assert generator_id(**base) != generator_id(**dict(base, modifier="Other"))
    assert generator_id(**base) != generator_id(**dict(base, scene="Scene.001"))
    slashed = generator_id(**dict(base, object_name="A/B"))
    assert "/object=A_B/" in slashed
    root = generator_id(**base)
    assert group_id(root, "FloorSlab") != group_id(root, "Windows")
    assert group_id(root, "FloorSlab") == group_id(root, "FloorSlab")
    assert operation_id(root, "scatter") != operation_id(group_id(root, "FloorSlab"), "scatter")
    assert content_hash(b"a") != content_hash(b"b")
    # A content change does not move the logical id.
    assert generator_id(**base) == generator_id(**base)


def test_manifest_round_trip(tmp_path):
    manifest = _package(tmp_path, tmp_path / "Building.nodebridge", replace=False)
    restored = loads_manifest(dumps_manifest(manifest))
    assert restored.as_dict() == manifest.as_dict()
    assert restored.format_version == 1
    assert restored.nodebridge_version == __version__
    assert restored.source["generator_id"].startswith("nodebridge:/dcc=blender/")
    assert "FloorSlab" in restored.provenance["group_ids"]
    assert restored.targets["houdini"]["script_path"] == "procedural/houdini.py"
    assert "manifest.json" not in {item.path for item in restored.artifacts}
    report = validate_bundle(tmp_path / "Building.nodebridge")
    assert report.ok, report.errors
    # Scripts are hashed, not executed. The generated file is still just text on disk.
    script = tmp_path / "Building.nodebridge" / "procedural" / "houdini.py"
    assert "import hou" in script.read_text(encoding="utf-8")
    assert report.manifest["publication_id"] == manifest.publication_id


def test_packaging_is_deterministic(tmp_path):
    first = _package(tmp_path, tmp_path / "A.nodebridge")
    second = _package(tmp_path, tmp_path / "B.nodebridge")
    assert first.publication_id == second.publication_id
    assert dumps_manifest(first) == dumps_manifest(second)


def test_hash_mismatch_and_traversal_fail(tmp_path):
    bundle = tmp_path / "Building.nodebridge"
    _package(tmp_path, bundle)
    scene = next(bundle.glob("scene.*"))
    scene.write_bytes(scene.read_bytes() + b"\n")
    report = validate_bundle(bundle)
    assert not report.ok
    assert any("sha256" in error for error in report.errors)

    outside = tmp_path / "secret.txt"
    outside.write_text("no", encoding="utf-8")
    leaked = bundle / "procedural" / "leak.json"
    leaked.symlink_to(outside)
    escaped = validate_bundle(bundle)
    assert not escaped.ok
    assert any("symlink" in error or "sha256" in error for error in escaped.errors)

    manifest_path = bundle / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["artifacts"].append({"path": "../secret.txt", "sha256": "0" * 64, "bytes": 2})
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    traversed = validate_bundle(bundle)
    assert not traversed.ok
    assert any("relative" in error or "escapes" in error for error in traversed.errors)


def test_corrupt_manifest_and_missing_member(tmp_path):
    bundle = tmp_path / "Building.nodebridge"
    _package(tmp_path, bundle)
    (bundle / "manifest.json").write_text("{", encoding="utf-8")
    report = validate_bundle(bundle)
    assert not report.ok
    assert report.manifest is None
    (bundle / "manifest.json").write_text(json.dumps({"format": "nodebridge.bundle", "format_version": 1}), encoding="utf-8")
    incomplete = validate_bundle(bundle)
    assert not incomplete.ok


def test_refuses_to_replace_unrelated_directory(tmp_path):
    occupied = tmp_path / "notes"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(BundleError):
        _package(tmp_path, occupied, replace=True)
    assert (occupied / "keep.txt").read_text(encoding="utf-8") == "mine"


def test_partial_failure_leaves_no_bundle(tmp_path, monkeypatch):
    calls = {"n": 0}
    import shutil

    real = shutil.copyfile

    def flaky(src, dst, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated write failure")
        return real(src, dst, *args, **kwargs)

    monkeypatch.setattr("nodebridge.interchange.bundle.shutil.copyfile", flaky)
    dest = tmp_path / "Partial.nodebridge"
    with pytest.raises(BundleError):
        _package(tmp_path, dest)
    assert not dest.exists()


def test_missing_pxr_blocks_only_features_that_need_it(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("nodebridge.interchange.usd.availability.pxr_available", lambda: False)
    dest = tmp_path / "Basic.nodebridge"
    manifest = _package(tmp_path, dest, annotate=True)
    assert manifest.scene["composition"] == "basic"
    assert any("pxr" in warning for warning in manifest.warnings)
    assert validate_bundle(dest).ok
    with pytest.raises(BundleError, match="pxr"):
        _package(tmp_path, tmp_path / "Layered.nodebridge", layered=True)
    assert not (tmp_path / "Layered.nodebridge").exists()
    scene = tmp_path / "cube.usda"
    scene.write_text(SCENE.read_text(encoding="utf-8"), encoding="utf-8")
    assert main(["usd", "inspect", str(scene)]) == 1
    assert "pxr" in capsys.readouterr().err
    assert main(["usd", "validate", str(dest)]) == 0


def test_cli_package_validate_and_existing_commands(tmp_path, capsys):
    semantic, report, report_text, script = _sidecars(tmp_path)
    output = tmp_path / "FromCli.nodebridge"
    code = main(
        [
            "usd",
            "package",
            "--scene",
            str(SCENE),
            "--graph",
            str(GRAPH),
            "--semantic",
            str(semantic),
            "--report",
            str(report),
            "--report-text",
            str(report_text),
            "--script",
            f"houdini={script}",
            "--output",
            str(output),
            "--no-annotate",
        ]
    )
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert main(["usd", "validate", str(output), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert main(["usd", "inspect", str(output)]) == 0
    fixture = str(ROOT / "examples" / "scatter" / "scatter.graph.json")
    assert main(["analyze", fixture, "--target", "houdini"]) == 0
    assert "NodeBridge Translation Report" in capsys.readouterr().out


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["--version"])
    assert caught.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_compare_verdicts_do_not_treat_missing_correspondence_as_a_match():
    def stage(name, prims, mpu=1.0):
        return StageSummary(status="open", identifier=name, meters_per_unit=mpu, up_axis="Z", up_axis_authored=True, meters_per_unit_authored=True, prims=prims, prim_count=len(prims))

    cube = PrimSummary(path="/World/Body", type_name="Cube", bounds_min=(-1, -1, -1), bounds_max=(1, 1, 1), world_translation=(0, 0, 0))
    same = compare_summaries(stage("a", [cube]), stage("b", [cube]))
    assert same.verdict == Verdict.MATCH
    moved = PrimSummary(path="/World/Body", type_name="Cube", bounds_min=(0, -1, -1), bounds_max=(2, 1, 1), world_translation=(1, 0, 0))
    changed = compare_summaries(stage("a", [cube]), stage("b", [moved]))
    assert changed.verdict == Verdict.DIFFERENCE
    assert changed.transform_differences and changed.bounds_differences
    other = PrimSummary(path="/Other/Body", type_name="Cube", bounds_min=(-1, -1, -1), bounds_max=(1, 1, 1), world_translation=(0, 0, 0))
    renamed = compare_summaries(stage("a", [cube]), stage("b", [other]))
    assert renamed.verdict == Verdict.INCONCLUSIVE
    tagged_a = PrimSummary(path="/A/Body", type_name="Mesh", generator_id="nodebridge:/op", point_count=8, face_count=6, bounds_min=(0, 0, 0), bounds_max=(1, 1, 1), world_translation=(0, 0, 0))
    tagged_b = PrimSummary(path="/B/Body", type_name="Mesh", generator_id="nodebridge:/op", point_count=8, face_count=6, bounds_min=(0, 0, 0), bounds_max=(1, 1, 1), world_translation=(0, 0, 0))
    by_id = compare_summaries(stage("a", [tagged_a]), stage("b", [tagged_b]))
    assert by_id.verdict == Verdict.MATCH
    retopo = PrimSummary(path="/A/Body", type_name="Mesh", generator_id="nodebridge:/op", point_count=4, face_count=1, bounds_min=(0, 0, 0), bounds_max=(2, 1, 1), world_translation=(0, 0, 0))
    different_mesh = compare_summaries(stage("a", [tagged_a]), stage("b", [retopo]))
    assert different_mesh.verdict == Verdict.DIFFERENCE
    assert different_mesh.topology_differences
    unknown_units = compare_summaries(
        StageSummary(status="open", identifier="a", prims=[cube], prim_count=1),
        StageSummary(status="open", identifier="b", prims=[cube], prim_count=1),
    )
    assert unknown_units.verdict == Verdict.INCONCLUSIVE


def test_core_modules_do_not_import_pxr_or_execute_scripts():
    banned_roots = {"interchange/usd", "addon", "frontend/blender"}
    for path in SRC.rglob("*.py"):
        relative = path.relative_to(SRC).as_posix()
        if any(relative.startswith(prefix) for prefix in banned_roots):
            continue
        if relative == "frontend/blender/usd_export.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            assert "pxr" not in names and "bpy" not in names, relative
    for path in (SRC / "interchange").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"exec", "eval"}, path
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = ""
                if isinstance(node, ast.Import):
                    module = " ".join(alias.name for alias in node.names)
                else:
                    module = node.module or ""
                if module.split(".")[0] == "pxr":
                    assert isinstance(getattr(node, "parent_is_function", False), bool)
                    # pxr imports in interchange/usd must be inside functions.
                    assert path.relative_to(SRC).parts[1] == "usd"
                    assert _inside_function(path, node.lineno)


def _inside_function(path: Path, lineno: int) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", start)
            if start <= lineno <= end:
                return True
    return False


def test_importing_the_package_does_not_import_pxr_or_bpy(tmp_path):
    script = tmp_path / "import_check.py"
    script.write_text(
        "import sys\n"
        "import nodebridge\n"
        "import nodebridge.cli\n"
        "import nodebridge.compiler.pipeline\n"
        "import nodebridge.interchange\n"
        "import nodebridge.frontend.blender.usd_export\n"
        "assert 'pxr' not in sys.modules\n"
        "assert 'bpy' not in sys.modules\n"
        "print(nodebridge.__version__)\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    completed = subprocess.run([sys.executable, str(script)], check=False, capture_output=True, text=True, env=env)
    assert completed.returncode == 0, completed.stderr
    assert __version__ in completed.stdout


def test_bundle_relative_rejects_absolute_paths():
    from nodebridge.interchange.bundle import bundle_relative

    with pytest.raises(PathSecurityError):
        bundle_relative("/etc/passwd")
    with pytest.raises(PathSecurityError):
        bundle_relative("../secret")
    assert bundle_relative("./procedural/source.graph.json") == "procedural/source.graph.json"


def test_cli_bad_input_exits_2(tmp_path, capsys):
    missing = tmp_path / "missing.usda"
    assert main(["usd", "inspect", str(missing)]) == 2
    assert main(["usd", "package", "--scene", str(missing), "--graph", str(GRAPH), "--semantic", str(GRAPH), "--output", str(tmp_path / "out")]) == 2
    captured = capsys.readouterr()
    assert "not found" in captured.err or "nodebridge:" in captured.err
