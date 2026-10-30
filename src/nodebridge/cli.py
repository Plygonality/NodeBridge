"""Command-line access to the compiler (no Blender required).

    nodebridge analyze  examples/scatter/scatter.graph.json --target houdini
    nodebridge generate examples/scatter/scatter.graph.json --target unreal -o scatter_unreal.py
    nodebridge capabilities --markdown
    nodebridge usd validate BUNDLE
    nodebridge usd inspect SCENE.usd --json
    nodebridge usd package --scene SCENE.usdc --graph SOURCE.graph.json \\
        --semantic GENERATOR.semantic.json --output DIRECTORY
    nodebridge usd compare SOURCE.usd TARGET.usd --json

Graph IR documents (``*.graph.json``) are exported from Blender with the
add-on's *Debug Output* option or ``tests/blender/run_in_blender.py``.
``usd package`` copies an existing USD file. It does not evaluate Geometry Nodes.
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
    _add_usd_parser(sub)
    return parser


def _add_usd_parser(sub: argparse._SubParsersAction) -> None:
    usd = sub.add_parser("usd", help="inspect, validate, package, or compare OpenUSD bundles")
    usd_sub = usd.add_subparsers(dest="usd_command", required=True)
    inspect = usd_sub.add_parser("inspect", help="summarize a USD file, or a bundle directory")
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--json", action="store_true")
    validate = usd_sub.add_parser("validate", help="check a bundle manifest or a USD stage")
    validate.add_argument("path", type=Path)
    validate.add_argument("--json", action="store_true")
    validate.add_argument("--strict", action="store_true", help="fail when the bundle or stage has warnings")
    package = usd_sub.add_parser("package", help="package an existing USD file with Graph IR and Semantic IR sidecars")
    package.add_argument("--scene", required=True, type=Path, help="evaluated USD file; this command does not run Geometry Nodes")
    package.add_argument("--graph", required=True, type=Path)
    package.add_argument("--semantic", required=True, type=Path)
    package.add_argument("--output", required=True, type=Path, help="bundle directory to create")
    package.add_argument("--report", type=Path, help="translation report JSON")
    package.add_argument("--report-text", type=Path, help="translation report text")
    package.add_argument("--script", action="append", default=[], help="TARGET=PATH, for example houdini=building.py")
    package.add_argument("--layered", action="store_true", help="write scene.usda referencing the geometry layer; requires pxr")
    package.add_argument("--replace", action="store_true", help="replace an existing NodeBridge bundle at the output path")
    package.add_argument("--up-axis", choices=["Y", "Z"])
    package.add_argument("--meters-per-unit", type=float)
    package.add_argument("--no-annotate", action="store_true", help="do not write a provenance overlay when pxr is available")
    package.add_argument("--procedural", action="store_true", help="experimental UsdProc marker on a layered stage; not evaluated by generic DCCs")
    package.add_argument("--json", action="store_true")
    compare = usd_sub.add_parser("compare", help="compare two USD stages; requires pxr")
    compare.add_argument("source", type=Path)
    compare.add_argument("target", type=Path)
    compare.add_argument("--json", action="store_true")
    compare.add_argument("--tolerance", type=float, default=1e-4, help="difference tolerance in meters when metersPerUnit is known")


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except (ValueError, KeyError, json.JSONDecodeError, FileNotFoundError) as exc:
        print(f"nodebridge: {exc}", file=sys.stderr)
        return 2


def _main(argv: list[str] | None = None) -> int:
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
    if args.command == "usd":
        from .interchange.commands import run_usd

        return run_usd(args)
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
        if result.diagnostics.errors:
            for item in result.diagnostics.errors:
                print(f"nodebridge: {item.message}", file=sys.stderr)
        else:
            print("nothing to generate", file=sys.stderr)
        return 1
    if args.output:
        args.output.write_text(result.code.code, encoding="utf-8")
        print(f"wrote {args.output} ({result.code.code.count(chr(10))} lines); {result.code.run_instructions}", file=sys.stderr)
    else:
        sys.stdout.write(result.code.code)
    if args.json:
        print(json.dumps(result.report.as_dict(), indent=2, default=str), file=sys.stderr)
    return 1 if result.diagnostics.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
