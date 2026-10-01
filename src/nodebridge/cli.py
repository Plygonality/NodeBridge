"""Command-line access to the compiler (no Blender required).

    nodebridge analyze  examples/scatter/scatter.graph.json --target houdini
    nodebridge generate examples/scatter/scatter.graph.json --target unreal -o scatter_unreal.py
    nodebridge capabilities --markdown

Graph IR documents (``*.graph.json``) are exported from Blender with the
add-on's *Debug Output* option or ``tests/blender/run_in_blender.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .compiler.pipeline import CompileOptions, analyze, generate
from .ir.serialization import loads_graph, dumps_semantic
from .translation.confidence import Strictness


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nodebridge", description="Cross-DCC procedural compiler")
    parser.add_argument("--version", action="version", version=f"NodeBridge {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("analyze", "classify a Graph IR document against a target"), ("generate", "generate target code")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("path", type=Path)
        command.add_argument("--target", required=True, choices=["houdini", "unreal"])
        command.add_argument("--strictness", default="ALLOW_APPROXIMATE", choices=[s.value for s in Strictness])
        command.add_argument("--no-comments", action="store_true")
        command.add_argument("--json", action="store_true", help="print the report as JSON")
        if name == "generate":
            command.add_argument("-o", "--output", type=Path, help="write the script here instead of stdout")
        else:
            command.add_argument("--semantic", action="store_true", help="print the Semantic IR")
    caps = sub.add_parser("capabilities", help="print the capability matrix")
    caps.add_argument("--target", action="append")
    caps.add_argument("--markdown", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "capabilities":
        from .compiler.capabilities import capability_matrix, format_matrix_markdown

        if args.markdown:
            sys.stdout.write(format_matrix_markdown(args.target))
            return 0
        for row in capability_matrix(args.target):
            cells = "; ".join(f"{target}: " + (", ".join(f"{c.confidence.value}" for _, c in entries) or "UNSUPPORTED") for target, entries in row.targets.items())
            print(f"{row.kind:<22} {cells}")
        return 0
    document = loads_graph(args.path.read_text(encoding="utf-8"))
    options = CompileOptions(strictness=Strictness(args.strictness), include_comments=not args.no_comments)
    result = analyze(document, args.target, options)
    if args.command == "analyze":
        if args.semantic:
            sys.stdout.write(dumps_semantic(result.semantic))
        elif args.json:
            print(json.dumps(result.report.as_dict(), indent=2, default=str))
        else:
            sys.stdout.write(result.report.to_text())
        return 1 if result.diagnostics.errors else 0
    generate(result)
    if result.code is None:
        print("nothing to generate", file=sys.stderr)
        return 1
    if args.output:
        args.output.write_text(result.code.code, encoding="utf-8")
        print(f"wrote {args.output} ({result.code.code.count(chr(10))} lines); {result.code.run_instructions}", file=sys.stderr)
    else:
        sys.stdout.write(result.code.code)
    if args.json:
        print(json.dumps(result.report.as_dict(), indent=2, default=str), file=sys.stderr)
    return 1 if any(d.code.startswith("script.") for d in result.diagnostics.errors) else 0


if __name__ == "__main__":
    raise SystemExit(main())
