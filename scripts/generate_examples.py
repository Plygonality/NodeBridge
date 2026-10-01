"""Write example graph IR, scripts, and reports."""

from __future__ import annotations

from pathlib import Path

from nodebridge.compiler import compile_source
from nodebridge.examples.graphs import EXAMPLES
from nodebridge.frontend.blender import BlenderFrontend
from nodebridge.ir.serialization import dumps

ROOT = Path(__file__).resolve().parents[1] / "examples"


def main() -> None:
    for name, factory in EXAMPLES.items():
        source = factory()
        folder = ROOT / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "graph.json").write_text(dumps(BlenderFrontend().parse(source)) + "\n", encoding="utf-8")
        for target in ("houdini", "unreal"):
            result = compile_source(source, target)
            (folder / f"{target}.py").write_text(result.code, encoding="utf-8")
            (folder / f"{target}_report.txt").write_text(result.report.text, encoding="utf-8")


if __name__ == "__main__":
    main()
