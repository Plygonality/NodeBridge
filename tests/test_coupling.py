"""Architectural coupling guards.

The core package must stay importable without Blender, Houdini, or Unreal.
Application SDKs may only appear inside host runtime modules, via importlib.
"""

from __future__ import annotations

import ast
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[1] / "src" / "nodebridge"

FORBIDDEN_MODULES = {"bpy", "hou", "unreal"}

HOST_PACKAGES = {
    CORE_ROOT / "hosts" / "blender",
    CORE_ROOT / "hosts" / "houdini",
    CORE_ROOT / "hosts" / "unreal",
    CORE_ROOT / "adapters" / "blender",
    CORE_ROOT / "backends" / "houdini",
    CORE_ROOT / "backends" / "unreal",
}

CORE_LAYERS = (
    CORE_ROOT / "core",
    CORE_ROOT / "ir",
    CORE_ROOT / "compiler",
    CORE_ROOT / "cli",
    CORE_ROOT / "translators",
)


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_core_layers_do_not_import_host_sdks() -> None:
    for folder in CORE_LAYERS:
        for path in _iter_python_files(folder):
            imported = _imported_modules(path)
            leaked = imported & FORBIDDEN_MODULES
            assert not leaked, f"{path} imports {sorted(leaked)}"


def test_entire_package_has_no_static_host_sdk_imports() -> None:
    for path in _iter_python_files(CORE_ROOT):
        imported = _imported_modules(path)
        leaked = imported & FORBIDDEN_MODULES
        assert not leaked, f"{path} imports {sorted(leaked)}"


def test_importing_nodebridge_does_not_require_host_sdks() -> None:
    import nodebridge
    from nodebridge.adapters.blender import BlenderExtractor
    from nodebridge.backends.houdini import HoudiniBackend
    from nodebridge.backends.unreal import UnrealBackend
    from nodebridge.hosts import list_hosts

    assert nodebridge.__version__ == "0.2.0"
    assert BlenderExtractor.application == "blender"
    assert HoudiniBackend.name == "houdini"
    assert UnrealBackend.name == "unreal"
    assert set(list_hosts()) == {"blender", "houdini", "unreal"}
    assert "bpy" not in dir(nodebridge)
    assert "hou" not in dir(nodebridge)


def test_host_packages_exist_as_isolated_layers() -> None:
    for folder in HOST_PACKAGES:
        assert folder.is_dir(), f"missing isolation package: {folder}"
