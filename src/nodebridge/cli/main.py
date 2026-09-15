"""Command-line interface for inspecting and validating IR documents."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nodebridge.ir.deserializer import load
from nodebridge.ir.validation import validate_graph
from nodebridge.ir.versioning import IR_VERSION, PACKAGE_VERSION
from nodebridge.translators.compatibility import analyse_compatibility


def build_parser() -> argparse.ArgumentParser:
    """Construct the ``nodebridge`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="nodebridge",
        description="Inspect and validate NodeBridge IR documents.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print package and IR versions and exit.",
    )
    sub = parser.add_subparsers(dest="command")

    inspect = sub.add_parser("inspect", help="Summarize an IR document.")
    inspect.add_argument("path", type=Path)

    validate = sub.add_parser("validate", help="Validate an IR document.")
    validate.add_argument("path", type=Path)

    report = sub.add_parser(
        "report",
        help="Classify operations against a target (no code generation).",
    )
    report.add_argument("path", type=Path)
    report.add_argument("--target", default="houdini")

    translate = sub.add_parser(
        "translate",
        help="Generate target code (not implemented in Milestone 1).",
    )
    translate.add_argument("path", type=Path)
    translate.add_argument("--target", required=True)
    translate.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version or args.command is None:
        print(f"NodeBridge {PACKAGE_VERSION} (IR version {IR_VERSION})")
        if args.command is None and not args.version:
            parser.print_help()
            return 0
        return 0

    path: Path = args.path
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 2

    try:
        document = load(path)
    except Exception as exc:  # noqa: BLE001 — CLI boundary
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "inspect":
        return _inspect(document)
    if args.command == "validate":
        return _validate(document)
    if args.command == "report":
        return _report(document, args.target)
    if args.command == "translate":
        print(
            "error: translate is not implemented in Milestone 1. "
            "Use inspect, validate, or report.",
            file=sys.stderr,
        )
        return 2
    parser.print_help()
    return 2


def _inspect(document: object) -> int:
    from nodebridge.ir.schema import IRDocument

    assert isinstance(document, IRDocument)
    graph = document.graph
    print(f"NodeBridge IR {document.ir_version} (package {document.nodebridge_version})")
    print(f"Source: {document.source.application or '(unknown)'}")
    print(f"Graph: {graph.name} ({graph.id})")
    print(f"System: {graph.system.value}")
    print(f"Nodes: {len(graph.nodes)}")
    print(f"Connections: {len(graph.connections)}")
    print(f"Nested graphs: {len(graph.graphs)}")
    print("Operations:")
    for node_id in sorted(graph.nodes):
        node = graph.nodes[node_id]
        print(f"  {node.id}: {node.operation}")
    return 0


def _validate(document: object) -> int:
    from nodebridge.ir.schema import IRDocument

    assert isinstance(document, IRDocument)
    result = validate_graph(document.graph)
    if result.ok:
        print("OK")
        for item in result.diagnostics:
            print(f"{item.severity.value}: {item.code}: {item.message}")
        return 0
    print("INVALID")
    for item in result.diagnostics:
        print(f"{item.severity.value}: {item.code}: {item.message}")
    return 1


def _report(document: object, target: str) -> int:
    from nodebridge.ir.schema import IRDocument

    assert isinstance(document, IRDocument)
    report = analyse_compatibility(document.graph, target)
    sys.stdout.write(report.format_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
