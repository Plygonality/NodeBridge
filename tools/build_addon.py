"""Build the installable Blender extension zip without needing Blender.

    python tools/build_addon.py            -> dist/nodebridge-<version>.zip
    python tools/build_addon.py --check    -> fail if release/nodebridge-<version>.zip is stale

The layout matches ``blender --command extension build`` (manifest at
the zip root), which is what Blender 4.2+ "Install from Disk" expects.

Entry timestamps and modes are fixed. A rebuild then depends only on
file contents, so ``release/nodebridge-<version>.zip`` can match the
zip CI builds for the ``nodebridge-addon`` artifact.
"""

from __future__ import annotations

import pathlib
import re
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "nodebridge"
EXCLUDE_DIRS = {"__pycache__"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}
# ZIP epoch is the format's minimum timestamp. A checkout mtime would make
# the archive differ on every machine.
ZIP_DATE = (1980, 1, 1, 0, 0, 0)
# Regular file, mode 0644, stored in the Unix external attribute field.
ZIP_UNIX_ATTR = (0o100644 & 0xFFFF) << 16


def version() -> str:
    match = re.search(r'^version\s*=\s*"([^"]+)"', (PACKAGE / "blender_manifest.toml").read_text(encoding="utf-8"), re.M)
    if not match:
        raise SystemExit("version not found in blender_manifest.toml")
    return match.group(1)


def selected_files() -> list[tuple[pathlib.Path, str]]:
    """Package files written into the zip, in archive order.

    Excluded, matching ``blender_manifest.toml`` ``paths_exclude_pattern``
    plus ``.pyo``: ``__pycache__`` directories, ``.pyc`` and ``.pyo`` files,
    and names that start with ``.``.
    """
    chosen: list[tuple[pathlib.Path, str]] = []
    for path in PACKAGE.rglob("*"):
        relative = path.relative_to(PACKAGE)
        if path.is_dir() or EXCLUDE_DIRS & set(relative.parts) or path.suffix in EXCLUDE_SUFFIXES or relative.name.startswith("."):
            continue
        chosen.append((path, relative.as_posix()))
    chosen.sort(key=lambda item: item[1])
    return chosen


def build(output_dir: pathlib.Path) -> pathlib.Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"nodebridge-{version()}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, name in selected_files():
            info = zipfile.ZipInfo(name, ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = ZIP_UNIX_ATTR
            info.create_system = 3
            archive.writestr(info, path.read_bytes())
    return target


def release_path() -> pathlib.Path:
    return ROOT / "release" / f"nodebridge-{version()}.zip"


def _members(path: pathlib.Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {info.filename: archive.read(info.filename) for info in archive.infolist()}


def check() -> int:
    """Compare the checked-in zip to the source files and to a fresh build."""
    expected = {name: path.read_bytes() for path, name in selected_files()}
    committed = release_path()
    if not committed.is_file():
        print(f"missing {committed.relative_to(ROOT)}", file=sys.stderr)
        return 1
    packed = _members(committed)
    with tempfile.TemporaryDirectory() as tmp:
        built = _members(build(pathlib.Path(tmp)))
    mismatches = []
    for name in sorted(set(expected) | set(packed) | set(built)):
        if expected.get(name) != packed.get(name) or expected.get(name) != built.get(name):
            mismatches.append(name)
    if mismatches:
        print(f"{committed.relative_to(ROOT)} does not match src/nodebridge ({len(mismatches)} paths):", file=sys.stderr)
        for name in mismatches:
            print(f"  {name}", file=sys.stderr)
        return 1
    print(f"{committed.relative_to(ROOT)} matches src/nodebridge ({len(expected)} files)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        raise SystemExit(check())
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist"
    print(build(out))
