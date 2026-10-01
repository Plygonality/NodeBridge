"""Build the installable Blender extension zip without needing Blender.

    python tools/build_addon.py            -> dist/nodebridge-<version>.zip

The layout matches ``blender --command extension build`` (manifest at
the zip root), which is what Blender 4.2+ "Install from Disk" expects.
"""

from __future__ import annotations

import pathlib
import re
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "nodebridge"
EXCLUDE_DIRS = {"__pycache__"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def version() -> str:
    match = re.search(r'^version\s*=\s*"([^"]+)"', (PACKAGE / "blender_manifest.toml").read_text(encoding="utf-8"), re.M)
    if not match:
        raise SystemExit("version not found in blender_manifest.toml")
    return match.group(1)


def build(output_dir: pathlib.Path) -> pathlib.Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"nodebridge-{version()}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(PACKAGE.rglob("*")):
            relative = path.relative_to(PACKAGE)
            if path.is_dir() or EXCLUDE_DIRS & set(relative.parts) or path.suffix in EXCLUDE_SUFFIXES or relative.name.startswith("."):
                continue
            archive.write(path, relative.as_posix())
    return target


if __name__ == "__main__":
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist"
    print(build(out))
