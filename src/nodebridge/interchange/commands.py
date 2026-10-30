"""CLI handlers for ``nodebridge usd``.

Exit codes match the rest of NodeBridge: 0 success, 1 operational or
validation failure, 2 bad input. Stage inspection and layered composition
fail with an installation message when ``pxr`` is missing. They do not
traceback.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .bundle import PackageInputs, publish_package
from .compare import compare_stages
from .errors import BundleError
from .usd.availability import UsdUnavailable, pxr_available, require_pxr
from .usd.inspect import inspect_stage
from .validate import validate_bundle

_USD_SUFFIXES = {".usd", ".usda", ".usdc", ".usdz"}


def run_usd(args) -> int:
    try:
        if args.usd_command == "inspect":
            return _inspect(args)
        if args.usd_command == "validate":
            return _validate(args)
        if args.usd_command == "package":
            return _package(args)
        if args.usd_command == "compare":
            return _compare(args)
    except UsdUnavailable as exc:
        return _fail(args, str(exc), code=1)
    except BundleError as exc:
        return _fail(args, str(exc), code=1)
    except FileNotFoundError as exc:
        return _fail(args, str(exc), code=2)
    except ValueError as exc:
        return _fail(args, str(exc), code=2)
    print("nodebridge: unknown usd command", file=sys.stderr)
    return 2


def _fail(args, message: str, *, code: int) -> int:
    print(f"nodebridge: {message}", file=sys.stderr)
    if getattr(args, "json", False):
        print(json.dumps({"ok": False, "error": message}, indent=2, sort_keys=True))
    return code


def _emit(payload: dict, *, as_json: bool, text: str) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        sys.stdout.write(text)


def _inspect(args) -> int:
    path = Path(args.path)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.is_dir():
        report = validate_bundle(path, strict=False)
        payload: dict = {"bundle": report.as_dict()}
        scene = ""
        if report.manifest is not None:
            scene = str(report.manifest.get("scene", {}).get("usd_path", ""))
        stage = None
        if scene and pxr_available():
            stage = inspect_stage(path / scene)
            payload["stage"] = stage.as_dict()
        elif scene:
            payload["stage"] = None
            payload["stage_skipped"] = "pxr is not installed. Bundle inspection did not open the USD stage."
        text = _format_bundle_inspect(payload)
        _emit(payload, as_json=args.json, text=text)
        return 0 if report.ok or (report.manifest is not None and not report.errors) else 1
    if path.suffix.lower() not in _USD_SUFFIXES:
        raise ValueError(f"inspect expects a bundle directory or a USD file: {path}")
    require_pxr("USD stage inspection")
    summary = inspect_stage(path)
    _emit(summary.as_dict(), as_json=args.json, text=_format_stage(summary))
    return 0 if summary.status == "open" else 1


def _validate(args) -> int:
    path = Path(args.path)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.is_dir():
        report = validate_bundle(path, strict=args.strict)
        _emit(report.as_dict(), as_json=args.json, text=_format_validation(report))
        return 0 if report.ok else 1
    if path.suffix.lower() not in _USD_SUFFIXES:
        raise ValueError(f"validate expects a bundle directory or a USD file: {path}")
    require_pxr("USD stage validation")
    summary = inspect_stage(path)
    errors = []
    if summary.status != "open":
        errors.append(summary.error or "stage did not open")
    errors.extend(f"missing reference: {item}" for item in summary.missing)
    warnings = list(summary.warnings)
    ok = not errors and not (args.strict and warnings)
    payload = {"ok": ok, "errors": errors, "warnings": warnings, "stage": summary.as_dict()}
    text = _format_stage(summary)
    if errors:
        text += "\n".join(f"error: {item}" for item in errors) + "\n"
    _emit(payload, as_json=args.json, text=text)
    return 0 if ok else 1


def _package(args) -> int:
    scripts: dict[str, Path] = {}
    for item in args.script or []:
        if "=" not in item:
            raise ValueError(f"--script expects TARGET=PATH, got {item!r}")
        target, raw = item.split("=", 1)
        scripts[target.strip()] = Path(raw)
    manifest = publish_package(
        PackageInputs(
            scene=Path(args.scene),
            graph=Path(args.graph),
            semantic=Path(args.semantic),
            output=Path(args.output),
            report_json=Path(args.report) if args.report else None,
            report_text=Path(args.report_text) if args.report_text else None,
            scripts=scripts,
            layered=args.layered,
            replace=args.replace,
            publisher="cli",
            annotate=not args.no_annotate,
            procedural=args.procedural,
            up_axis=args.up_axis,
            meters_per_unit=args.meters_per_unit,
            export_settings={"tool": "nodebridge usd package", "layered": bool(args.layered), "procedural": bool(args.procedural)},
        )
    )
    payload = manifest.as_dict()
    lines = [
        f"wrote {args.output}",
        f"scene: {manifest.scene.get('usd_path')}",
        f"composition: {manifest.scene.get('composition')}",
        f"artifacts: {len(manifest.artifacts)}",
        f"publication: {manifest.publication_id}",
    ]
    if manifest.warnings:
        lines.append(f"warnings: {len(manifest.warnings)}")
        lines.extend(f"  {warning}" for warning in manifest.warnings)
    _emit(payload, as_json=args.json, text="\n".join(lines) + "\n")
    return 0


def _compare(args) -> int:
    source = Path(args.source)
    target = Path(args.target)
    if not source.is_file():
        raise FileNotFoundError(source)
    if not target.is_file():
        raise FileNotFoundError(target)
    result = compare_stages(source, target, tolerance=args.tolerance)
    lines = [
        f"verdict: {result.verdict.value}",
        f"matched prims: {result.matched_prim_count}",
        f"unmatched: {len(result.unmatched_prims)}",
        f"transform differences: {len(result.transform_differences)}",
        f"bounds differences: {len(result.bounds_differences)}",
        f"topology differences: {len(result.topology_differences)}",
        f"material binding differences: {len(result.material_binding_differences)}",
    ]
    lines.extend(f"  {warning}" for warning in result.warnings)
    _emit(result.as_dict(), as_json=args.json, text="\n".join(lines) + "\n")
    opened = result.source_stage and result.verdict.value in {"MATCH", "DIFFERENCE", "INCONCLUSIVE"}
    # A completed comparison is success even when the scenes differ.
    # Failure is reserved for stages that could not be opened.
    if any("did not open" in warning for warning in result.warnings):
        return 1
    return 0 if opened else 1


def _format_stage(summary) -> str:
    data = summary.as_dict()
    counts = data["counts"]
    lines = [
        f"status: {summary.status}",
        f"root layer: {summary.root_layer}",
        f"default prim: {summary.default_prim or '(none)'}",
        f"prims: {summary.prim_count}",
        f"up axis: {summary.up_axis} ({'authored' if summary.up_axis_authored else 'default'})",
        f"meters per unit: {summary.meters_per_unit}",
        f"meshes: {counts['mesh']}  xforms: {counts['xform']}  curves: {counts['curves']}  points: {counts['points']}  instances: {counts['instances']}  materials: {counts['materials']}",
        f"references: {', '.join(summary.references) or '(none)'}",
        f"missing: {', '.join(summary.missing) or '(none)'}",
    ]
    lines.extend(f"warning: {warning}" for warning in summary.warnings)
    return "\n".join(lines) + "\n"


def _format_validation(report) -> str:
    lines = ["valid" if report.ok else "invalid"]
    lines.extend(f"error: {item}" for item in report.errors)
    lines.extend(f"warning: {item}" for item in report.warnings)
    return "\n".join(lines) + "\n"


def _format_bundle_inspect(payload: dict) -> str:
    bundle = payload["bundle"]
    lines = ["bundle valid" if bundle["ok"] else "bundle invalid"]
    lines.extend(f"error: {item}" for item in bundle["errors"])
    stage = payload.get("stage")
    if stage is None and payload.get("stage_skipped"):
        lines.append(payload["stage_skipped"])
    elif isinstance(stage, dict):
        lines.append(f"stage: {stage.get('root_layer')} prims={stage.get('prim_count')} up={stage.get('up_axis')}")
    return "\n".join(lines) + "\n"
