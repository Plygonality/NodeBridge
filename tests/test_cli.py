"""CLI inspect / validate / report tests."""

from __future__ import annotations

from pathlib import Path

from nodebridge.cli.main import main
from nodebridge.ir.serializer import dump
from tests.helpers import make_transform_graph


def test_cli_inspect(tmp_path: Path, capsys: object) -> None:
    path = tmp_path / "graph.nodebridge.json"
    dump(make_transform_graph().graph, path)
    assert main(["inspect", str(path)]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "transform_geometry" in output
    assert "geometry.transform" in output


def test_cli_validate_ok(tmp_path: Path, capsys: object) -> None:
    path = tmp_path / "graph.nodebridge.json"
    dump(make_transform_graph().graph, path)
    assert main(["validate", str(path)]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert output.startswith("OK")


def test_cli_report(tmp_path: Path, capsys: object) -> None:
    path = tmp_path / "graph.nodebridge.json"
    dump(make_transform_graph().graph, path)
    assert main(["report", str(path), "--target", "houdini"]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "NodeBridge Translation Report" in output


def test_cli_translate_not_implemented(tmp_path: Path) -> None:
    path = tmp_path / "graph.nodebridge.json"
    dump(make_transform_graph().graph, path)
    assert main(["translate", str(path), "--target", "houdini"]) == 2


def test_cli_version(capsys: object) -> None:
    assert main(["--version"]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "NodeBridge 0.1.0" in output


def test_module_entrypoint_version() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "nodebridge", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "NodeBridge 0.1.0" in result.stdout
