"""Zip the NodeBridge package so Blender can install it from disk.

The zip contains a top-level ``nodebridge`` folder with ``bl_info`` in
``__init__.py``. Run from the repository root:

    python3 scripts/package_addon.py
"""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "nodebridge"
OUTPUT = ROOT / "dist" / "nodebridge.zip"
SKIP = {"__pycache__", ".pytest_cache"}


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in PACKAGE.rglob("*"):
            if not path.is_file() or any(part in SKIP for part in path.parts) or path.suffix == ".pyc":
                continue
            archive.write(path, Path("nodebridge") / path.relative_to(PACKAGE))
    print(OUTPUT)


if __name__ == "__main__":
    main()
