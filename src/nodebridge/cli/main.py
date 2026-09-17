"""Command-line interface for the NodeBridge semantic compiler."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from nodebridge.compiler.pipeline import CompilationResult, compile_graph, compile_native
from nodebridge.compiler.planning import plan_translation
from nodebridge.hosts.native import NativeGraph
from nodebridge.hosts.registry import get_host, list_hosts
from nodebridge.ir.deserializer import load, loads
from nodebridge.ir.schema import IRDocument
from nodebridge.ir.serializer import dumps
from nodebridge.ir.validation import validate_graph
from nodebridge.ir.versioning import IR_VERSION, PACKAGE_VERSION


def build_parser() -> argparse.ArgumentParser:
    """Construct the ``nodebridge`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="nodebridge",
        description="Compile procedural graphs between DCC hosts via a semantic IR.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print package and IR versions and exit.",
    )
    sub = parser.add_subparsers(dest="command")

    inspect = sub.add_parser("inspect", help="Summarize an IR or native graph document.")
    inspect.add_argument("path", type=Path)

    validate = sub.add_parser("validate", help="Validate an IR document.")
    validate.add_argument("path", type=Path)

    capabilities = sub.add_parser("capabilities", help="Show host capability declarations.")
    capabilities.add_argument("host", nargs="?", default=None)

    plan = sub.add_parser("plan", help="Construct a translation plan without generating a graph.")
    plan.add_argument("path", type=Path)
    plan.add_argument("--target", required=True)
    plan.add_argument("--json", action="store_true", dest="as_json")

    report = sub.add_parser(
        "report",
        help="Classify operations against a target host.",
    )
    report.add_argument("path", type=Path)
    report.add_argument("--target", default="houdini")
    report.add_argument("--json", action="store_true", dest="as_json")

    translate = sub.add_parser(
        "translate",
        help="Compile IR or a native graph toward a target host.",
    )
    translate.add_argument("path", nargs="?", type=Path)
    translate.add_argument("--input", type=Path, dest="input_path")
    translate.add_argument("--source", default=None)
    translate.add_argument("--target", required=True)
    translate.add_argument("--output", type=Path)
    translate.add_argument("--script", type=Path)
    translate.add_argument("--json", action="store_true", dest="as_json")
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

    if args.command == "capabilities":
        return _capabilities(args.host)

    path: Path | None = getattr(args, "path", None) or getattr(args, "input_path", None)
    if path is None:
        print("error: missing input path", file=sys.stderr)
        return 2
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 2

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as extra:  # noqa: BLE001
        print(f"error: {extra}", file=sys.stderr)
        return 2

    if args.command == "inspect":
        return _inspect_payload(payload)
    if args.command == "validate":
        document = _as_document(payload)
        if document is None:
            print("error: validate requires a NodeBridge IR document", file=sys.stderr)
            return 2
        return _validate(document)
    if args.command == "plan":
        return _plan(payload, args.target, as_json=args.as_json)
    if args.command == "report":
        return _report(payload, args.target, as_json=args.as_json)
    if args.command == "translate":
        return _translate(
            payload,
            target=args.target,
            source=args.source,
            output=args.output,
            script=args.script,
            as_json=args.as_json,
        )
    parser.print_help()
    return 2


def _capabilities(host_id: str | None) -> int:
    names = list_hosts()
    if host_id is None:
        print("Hosts:")
        for name in names:
            host = get_host(name)
            systems = ", ".join(host.graph_systems)
            print(f"  {host.id}: {host.display_name} [{systems}]")
        return 0
    host = get_host(host_id)
    payload = {
        "id": host.id,
        "display_name": host.display_name,
        "versions": list(host.versions),
        "graph_systems": list(host.graph_systems),
        "capabilities": host.capabilities.as_list(),
        "frontend": True,
        "backend": True,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _inspect_payload(payload: dict[str, Any]) -> int:
    document = _as_document(payload)
    if document is not None:
        return _inspect(document)
    native = NativeGraph.from_dict(payload)
    print(f"Native graph ({native.host} {native.system})")
    print(f"Name: {native.name}")
    print(f"Nodes: {len(native.nodes)}")
    print(f"Links: {len(native.links)}")
    print("Types:")
    for node in native.nodes:
        print(f"  {node.id}: {node.type}")
    return 0


def _inspect(document: IRDocument) -> int:
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


def _validate(document: IRDocument) -> int:
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


def _plan(payload: dict[str, Any], target: str, *, as_json: bool) -> int:
    result = _compile(payload, target, generate=False)
    if as_json:
        print(json.dumps(result.plan.as_dict(), indent=2, sort_keys=True))
        return 0
    print(f"Plan: {result.source_host} → {result.target_host}")
    for item in result.plan.operations:
        print(f"  {item.node_id}: {item.operation} [{item.fidelity.value}] {item.recipe}".rstrip())
    return 0


def _report(payload: dict[str, Any], target: str, *, as_json: bool) -> int:
    result = _compile(payload, target, generate=False)
    if as_json:
        print(json.dumps(result.report.as_dict(), indent=2, sort_keys=True))
        return 0
    sys.stdout.write(result.report.format_text())
    return 0


def _translate(
    payload: dict[str, Any],
    *,
    target: str,
    source: str | None,
    output: Path | None,
    script: Path | None,
    as_json: bool,
) -> int:
    result = _compile(payload, target, source=source, generate=script is not None)
    if output is not None:
        output.write_text(
            json.dumps(result.native_graph.as_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if script is not None:
        if not result.generated_code:
            from nodebridge.compiler.lowering import generate_script

            result.generated_code = generate_script(result.normalized_graph, target)
        script.write_text(result.generated_code, encoding="utf-8")
    if as_json:
        print(json.dumps(result.report.as_dict(), indent=2, sort_keys=True))
    else:
        sys.stdout.write(result.report.format_text())
        print(f"Native nodes: {len(result.native_graph.nodes)}")
        if output is not None:
            print(f"Wrote construction plan: {output}")
        if script is not None:
            print(f"Wrote host script: {script}")
    return 0 if not result.report.errors() else 1


def _compile(
    payload: dict[str, Any],
    target: str,
    *,
    source: str | None = None,
    generate: bool = False,
) -> CompilationResult:
    if "ir_version" in payload and "graph" in payload:
        document = loads(json.dumps(payload))
        return compile_graph(document, target, source=source, generate=generate)
    native = NativeGraph.from_dict(payload)
    return compile_native(native, target, source=source or native.host, generate=generate)


def _as_document(payload: dict[str, Any]) -> IRDocument | None:
    if "ir_version" in payload and "graph" in payload:
        return loads(json.dumps(payload))
    return None


if __name__ == "__main__":
    raise SystemExit(main())
