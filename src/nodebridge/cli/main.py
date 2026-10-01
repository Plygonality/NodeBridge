"""Command line compiler.

    nodebridge compile --example scatter --target houdini --output scatter.py --report scatter.txt

The CLI reads a serialized graph IR file or one of the built-in examples.
It does not start Blender.
"""

from __future__ import annotations

import argparse
import sys

from nodebridge.compiler.options import CompileOptions
from nodebridge.compiler.pipeline import compile_source, compile_tree
from nodebridge.examples.graphs import EXAMPLES
from nodebridge.ir.serialization import load
from nodebridge.translation.confidence import Strictness


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nodebridge", description="Compile a procedural graph into native DCC code.")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_parser = sub.add_parser("compile", help="Analyze a graph and write a target script")
    compile_parser.add_argument("--target", required=True, choices=["houdini", "unreal"])
    source = compile_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="Graph IR JSON produced by NodeBridge")
    source.add_argument("--example", choices=sorted(EXAMPLES))
    compile_parser.add_argument("--output", help="Write the generated script to this path")
    compile_parser.add_argument("--report", help="Write the translation report to this path")
    compile_parser.add_argument(
        "--strictness",
        choices=[item.value for item in Strictness],
        default=Strictness.ALLOW_APPROXIMATE.value,
    )
    compile_parser.add_argument("--no-deterministic-random", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "compile":
        return _compile(args)
    parser.error(f"Unknown command {args.command}")
    return 2


def _compile(args) -> int:
    options = CompileOptions(
        strictness=Strictness(args.strictness),
        deterministic_random=not args.no_deterministic_random,
    )
    if args.example:
        result = compile_source(EXAMPLES[args.example](), args.target, options)
    else:
        loaded = load(args.input)
        result = compile_tree(loaded, args.target, options)
    if args.output:
        _write(args.output, result.code)
    else:
        sys.stdout.write(result.code)
    if args.report:
        _write(args.report, result.report.text)
    if result.issues:
        sys.stderr.write(f"NodeBridge reported {len(result.issues)} issue(s). See the translation report.\n")
    return 0


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


if __name__ == "__main__":
    raise SystemExit(main())
