"""Regenerate expected reports, generated scripts and the support matrix.

    python tools/regenerate_examples.py

Reads ``examples/<name>/<name>.graph.json`` (exported from Blender by
``tests/blender/run_in_blender.py --export-fixtures``) and writes, per
target, ``expected_report_<target>.txt`` and ``generated_<target>.py``.
Tests compare against these files, so review the diff after changes.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nodebridge.compiler.capabilities import format_matrix_markdown  # noqa: E402
from nodebridge.compiler.pipeline import compile_document  # noqa: E402
from nodebridge.ir.serialization import loads_graph  # noqa: E402

EXAMPLES = ("scatter", "building", "shader", "compositor")
TARGETS = ("houdini", "unreal")


def main() -> None:
    for name in EXAMPLES:
        folder = ROOT / "examples" / name
        document = loads_graph((folder / f"{name}.graph.json").read_text(encoding="utf-8"))
        for target in TARGETS:
            result = compile_document(document, target)
            (folder / f"expected_report_{target}.txt").write_text(result.report.to_text(), encoding="utf-8")
            (folder / f"generated_{target}.py").write_text(result.code.code, encoding="utf-8")
            print(f"{name}/{target}: {result.report.counts}")
    matrix = ROOT / "docs" / "support_matrix.md"
    header = (
        "# Support matrix\n\n"
        "Generated from translator metadata by `tools/regenerate_examples.py` (do not edit by hand).\n"
        "Each cell shows the default confidence and implementation; some translators downgrade the\n"
        "confidence for specific configurations (see the translation report).\n\n"
    )
    matrix.write_text(header + format_matrix_markdown(), encoding="utf-8")
    print(f"wrote {matrix}")


if __name__ == "__main__":
    main()
