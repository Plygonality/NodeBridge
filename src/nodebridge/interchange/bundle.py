"""Create a self-describing NodeBridge bundle.

Members are bundle-relative POSIX paths. Absolute paths, ``..``, and
symlinks that resolve outside the bundle are rejected. Scripts are copied
as data and never executed. The destination is swapped into place only
after every member and ``manifest.json`` have been written in a temporary
directory, so a failed publish does not leave a half-written bundle.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .. import __version__
from ..ir.serialization import loads_graph, loads_semantic
from .errors import BundleError, PathSecurityError
from .manifest import STANDARD_LIMITATIONS, Artifact, BundleManifest, dumps_manifest
from .provenance import generator_id, group_id, publication_id, semantic_operation_records, sha256_file

MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_JSON_BYTES = 32 * 1024 * 1024
_SCENE_SUFFIXES = {".usd", ".usda", ".usdc", ".usdz"}
_SCRIPT_PATHS = {"houdini": "procedural/houdini.py", "unreal": "procedural/unreal.py"}


@dataclass
class PackageInputs:
    scene: Path
    graph: Path
    semantic: Path
    output: Path
    report_json: Path | None = None
    report_text: Path | None = None
    scripts: dict[str, Path] = field(default_factory=dict)
    layered: bool = False
    replace: bool = False
    publisher: str = "cli"
    annotate: bool = True
    procedural: bool = False
    up_axis: str | None = None
    meters_per_unit: float | None = None
    export_settings: dict | None = None
    extra_warnings: list[str] | None = None
    extra_limitations: list[str] | None = None


def bundle_relative(path: str) -> str:
    """Return a canonical bundle-relative POSIX path or raise."""
    if not isinstance(path, str) or not path.strip():
        raise PathSecurityError("bundle member path is empty")
    if path.startswith(("/", "\\")) or "\\" in path or "\x00" in path:
        raise PathSecurityError(f"bundle member path must be relative: {path!r}")
    # ``C:`` and other drive-style prefixes are absolute on some hosts.
    if len(path) >= 2 and path[1] == ":":
        raise PathSecurityError(f"bundle member path must be relative: {path!r}")
    text = path[2:] if path.startswith("./") else path
    parts = tuple(part for part in text.split("/") if part != ".")
    if not parts or any(part in ("", "..") for part in parts):
        raise PathSecurityError(f"bundle member path escapes the bundle: {path!r}")
    return "/".join(parts)


def resolve_member(root: Path, relative: str) -> Path:
    """Resolve ``relative`` inside ``root``. Reject traversal and escaping symlinks."""
    rel = bundle_relative(relative)
    root_resolved = root.resolve()
    candidate = root.joinpath(*rel.split("/"))
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        # ``resolve`` follows links. The resolved path must stay under the root.
        try:
            followed = candidate.resolve()
        except OSError as exc:
            raise PathSecurityError(f"cannot resolve {relative!r}: {exc}") from exc
        if not _is_inside(root_resolved, followed):
            raise PathSecurityError(f"symlink escapes the bundle: {relative}")
        return candidate
    if not _is_inside(root_resolved, candidate.resolve()):
        raise PathSecurityError(f"path escapes the bundle: {relative}")
    return candidate


def _is_inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _check_regular_file(path: Path, *, limit: int, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    if path.is_symlink():
        # Inputs may be symlinks the user chose. Copying reads the target bytes.
        # The stored bundle member is a regular file.
        pass
    size = path.stat().st_size
    if size > limit:
        raise BundleError(f"{label} is {size} bytes, over the {limit} byte limit")
    if size == 0 and label == "scene":
        raise BundleError(f"scene file is empty: {path}")


def _dcc_from_source(source: dict) -> str:
    application = str(source.get("application", "")).casefold()
    declared = str(source.get("dcc", "")).casefold()
    if "blender" in application or declared == "blender":
        return "blender"
    if declared:
        return declared
    return "unknown"


def _script_relative(target: str) -> str:
    if target in _SCRIPT_PATHS:
        return _SCRIPT_PATHS[target]
    if not target.isidentifier() or target.startswith("_"):
        raise BundleError(f"script target must be houdini, unreal, or a plain identifier: {target!r}")
    return f"procedural/{target}.py"


def _plain(value):
    """JSON-safe copy of a parameter value. Unknown objects become strings."""
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _json_object(path: Path, *, label: str) -> dict | None:
    _check_regular_file(path, limit=MAX_JSON_BYTES, label=label)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _copy_member(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # ``copyfile`` follows a symlink and writes a regular file.
    shutil.copyfile(source, dest)
    os.chmod(dest, 0o644)


def _is_nodebridge_bundle(path: Path) -> bool:
    manifest = path / "manifest.json"
    if not manifest.is_file():
        return False
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and data.get("format") == "nodebridge.bundle"


def _prepare_destination(output: Path, *, replace: bool) -> None:
    if output.exists() and not output.is_dir():
        raise BundleError(f"{output} exists and is not a directory")
    if not output.exists():
        return
    contents = [item for item in output.iterdir() if item.name not in (".", "..")]
    if not contents:
        return
    if not replace:
        raise BundleError(f"{output} already exists. Pass replace to overwrite a NodeBridge bundle.")
    if not _is_nodebridge_bundle(output):
        raise BundleError(f"{output} is not a NodeBridge bundle. Refusing to replace it.")


def _read_stage_metadata(scene: Path) -> dict | None:
    from .usd.availability import pxr_available

    if not pxr_available():
        return None
    from .usd.inspect import inspect_stage

    try:
        summary = inspect_stage(scene)
    except (OSError, RuntimeError):
        return None
    if summary.status != "open":
        return None
    return {
        "up_axis": summary.up_axis,
        "meters_per_unit": summary.meters_per_unit,
        "default_prim": summary.default_prim,
        "up_axis_authored": summary.up_axis_authored,
        "meters_per_unit_authored": summary.meters_per_unit_authored,
    }


def publish_package(inputs: PackageInputs) -> BundleManifest:
    """Publish a bundle at ``inputs.output`` and return its manifest."""
    scene = Path(inputs.scene)
    graph_path = Path(inputs.graph)
    semantic_path = Path(inputs.semantic)
    output = Path(inputs.output)
    suffix = scene.suffix.lower()
    if suffix not in _SCENE_SUFFIXES:
        raise BundleError(f"scene must be a USD file ({', '.join(sorted(_SCENE_SUFFIXES))}): {scene}")
    _check_regular_file(scene, limit=MAX_MEMBER_BYTES, label="scene")
    _check_regular_file(graph_path, limit=MAX_JSON_BYTES, label="graph")
    _check_regular_file(semantic_path, limit=MAX_JSON_BYTES, label="semantic")
    try:
        document = loads_graph(graph_path.read_text(encoding="utf-8"))
        semantic = loads_semantic(semantic_path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError, ValueError, KeyError) as exc:
        raise BundleError(f"could not read Graph IR or Semantic IR as data: {exc}") from exc

    for label, path in (("report", inputs.report_json), ("report text", inputs.report_text)):
        if path is not None:
            _check_regular_file(Path(path), limit=MAX_JSON_BYTES if label == "report" else MAX_MEMBER_BYTES, label=label)
    for target, path in inputs.scripts.items():
        _script_relative(target)
        _check_regular_file(Path(path), limit=MAX_MEMBER_BYTES, label=f"{target} script")

    if inputs.layered:
        from .usd.availability import require_pxr

        require_pxr("Layered USD composition")
    if inputs.procedural and not inputs.layered:
        raise BundleError("The experimental UsdProc marker is only written into a layered bundle. Pass layered as well.")
    if inputs.up_axis is not None and inputs.up_axis not in ("Y", "Z"):
        raise BundleError("up_axis must be Y or Z")

    _prepare_destination(output, replace=inputs.replace)
    source = document.source
    dcc = _dcc_from_source(source)
    gid = generator_id(
        dcc=dcc,
        tree=document.root,
        object_name=str(source.get("object", "")),
        modifier=str(source.get("modifier", "")),
        scene=str(source.get("scene", "")),
    )
    groups = {name: group_id(gid, name) for name, tree in sorted(document.trees.items()) if name != document.root and getattr(tree, "is_group", False)}
    warnings = list(inputs.extra_warnings or [])
    limitations = list(STANDARD_LIMITATIONS)
    if inputs.extra_limitations:
        limitations.extend(inputs.extra_limitations)

    scene_member = f"scene{suffix}"
    geometry_member = f"geometry/evaluated{suffix}"
    members: list[tuple[str, Path, str]] = [
        ("procedural/source.graph.json", graph_path, "graph"),
        ("procedural/generator.semantic.json", semantic_path, "semantic"),
    ]
    if inputs.layered:
        members.append((geometry_member, scene, "geometry"))
    else:
        members.append((scene_member, scene, "scene"))
    if inputs.report_json is not None:
        members.append(("procedural/report.json", Path(inputs.report_json), "report"))
    else:
        warnings.append("No translation report was supplied. Classification counts are not in this bundle.")
    if inputs.report_text is not None:
        members.append(("procedural/report.txt", Path(inputs.report_text), "report-text"))
    targets: dict[str, dict[str, str]] = {}
    for target, path in sorted(inputs.scripts.items()):
        relative = _script_relative(target)
        members.append((relative, Path(path), "script"))
        targets[target] = {"script_path": relative}

    stage_meta = _read_stage_metadata(scene)
    up_axis = inputs.up_axis
    meters = inputs.meters_per_unit
    default_prim = ""
    up_source = "unverified"
    if stage_meta is not None:
        up_axis = stage_meta["up_axis"] or up_axis
        if stage_meta["meters_per_unit"] is not None:
            meters = stage_meta["meters_per_unit"]
        default_prim = stage_meta["default_prim"]
        up_source = "usd-stage" if stage_meta["up_axis_authored"] else "usd-default"
        if not stage_meta["up_axis_authored"]:
            warnings.append("The USD stage does not author upAxis. The composed default was recorded, not assumed from Blender.")
        if not stage_meta["meters_per_unit_authored"]:
            warnings.append("The USD stage does not author metersPerUnit. The composed default was recorded.")
    elif up_axis is not None or meters is not None:
        up_source = "export-request"
        warnings.append("Stage metadata was not read back because pxr is unavailable. upAxis and metersPerUnit are the export request, not a parsed stage.")
    else:
        warnings.append("upAxis and metersPerUnit were not provided and pxr is unavailable, so scene scale was not recorded.")

    if not inputs.layered and inputs.annotate:
        from .usd.availability import pxr_available

        if not pxr_available():
            warnings.append("Namespaced USD provenance was not authored because pxr is unavailable. manifest.json remains authoritative.")

    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=parent))
    try:
        for relative, src, _role in members:
            _copy_member(src, tmp / relative)
        provenance_overlay = ""
        if inputs.layered:
            from .usd.compose import write_layered_root

            composed = write_layered_root(
                tmp / "scene.usda",
                geometry_relative=f"./{geometry_member}",
                geometry_file=tmp / geometry_member,
                generator_id=gid,
                generator_revision="",  # filled after the graph copy is hashed; patched below
                manifest_relative="./manifest.json",
                procedural=inputs.procedural,
                semantic_relative="./procedural/generator.semantic.json",
            )
            warnings.extend(composed.warnings)
            default_prim = composed.default_prim or default_prim
            if composed.up_axis:
                up_axis = composed.up_axis
                up_source = "usd-stage"
            if composed.meters_per_unit is not None:
                meters = composed.meters_per_unit
            scene_member = "scene.usda"
        elif inputs.annotate:
            from .usd.availability import pxr_available

            if pxr_available() and default_prim:
                from .usd.compose import write_provenance_overlay

                write_provenance_overlay(
                    tmp / "procedural" / "provenance.usda",
                    scene_relative=f"../{scene_member}",
                    default_prim=default_prim,
                    generator_id=gid,
                    manifest_relative="../manifest.json",
                )
                provenance_overlay = "procedural/provenance.usda"
            elif pxr_available() and not default_prim:
                warnings.append("No default prim was found, so no provenance overlay was written. manifest.json remains authoritative.")

        graph_hash = sha256_file(tmp / "procedural" / "source.graph.json")
        semantic_hash = sha256_file(tmp / "procedural" / "generator.semantic.json")
        if inputs.layered:
            from .usd.annotate import set_generator_revision

            set_generator_revision(tmp / "scene.usda", graph_hash)
            members.append(("scene.usda", tmp / "scene.usda", "scene"))

        artifacts: list[Artifact] = []
        hashed: list[tuple[str, str]] = []
        for relative, _src, role in members:
            member = tmp.joinpath(*relative.split("/"))
            digest = sha256_file(member)
            artifacts.append(Artifact(path=relative, sha256=digest, role=role, byte_size=member.stat().st_size))
            hashed.append((relative, digest))
        if provenance_overlay:
            member = tmp.joinpath(*provenance_overlay.split("/"))
            digest = sha256_file(member)
            artifacts.append(Artifact(path=provenance_overlay, sha256=digest, role="provenance-overlay", byte_size=member.stat().st_size))
            hashed.append((provenance_overlay, digest))

        counts = None
        if inputs.report_json is not None:
            report_data = _json_object(tmp / "procedural" / "report.json", label="report")
            if report_data is not None and isinstance(report_data.get("counts"), dict):
                counts = report_data["counts"]

        parameters = {
            parameter.key: {
                "name": parameter.name,
                "value": _plain(parameter.value),
                "default": _plain(parameter.default),
                "type": parameter.data_type.value,
            }
            for parameter in semantic.parameters
        }
        prim_path = default_prim if default_prim.startswith("/") else (f"/{default_prim}" if default_prim else "")
        provenance = {
            "prim_mappings": [
                {
                    "level": "asset",
                    "prim_path": prim_path,
                    "generator_id": gid,
                    "note": "Asset-level association. Per-element Geometry Nodes provenance is not available from the evaluated USD export.",
                }
            ],
            "source_generator_parameters": parameters,
            "group_ids": groups,
            "semantic_operations": semantic_operation_records(gid, semantic, groups),
        }
        if counts is not None:
            provenance["translation_counts"] = counts

        scene_info: dict = {
            "usd_path": scene_member,
            "composition": "layered" if inputs.layered else "basic",
            "up_axis_source": up_source,
        }
        if up_axis is not None:
            scene_info["up_axis"] = up_axis
        if meters is not None:
            scene_info["meters_per_unit"] = meters
        if default_prim:
            scene_info["default_prim"] = default_prim
        if inputs.layered:
            scene_info["geometry_path"] = geometry_member
        if provenance_overlay:
            scene_info["provenance_overlay"] = provenance_overlay

        source_info = {
            "dcc": dcc,
            "graph_path": "procedural/source.graph.json",
            "semantic_path": "procedural/generator.semantic.json",
            "generator_id": gid,
            "generator_revision": graph_hash,
            "semantic_revision": semantic_hash,
            "tree": document.root,
        }
        for key, field_name in (
            ("display_name", "display_name"),
            ("object", "object"),
            ("modifier", "modifier"),
            ("scene", "scene"),
            ("application", "application"),
        ):
            if source.get(field_name) not in (None, ""):
                source_info[key] = source[field_name]
        if source.get("unit_scale") is not None:
            source_info["unit_scale"] = source["unit_scale"]

        manifest = BundleManifest(
            nodebridge_version=__version__,
            publisher=inputs.publisher,
            publication_id=publication_id(hashed),
            source=source_info,
            scene=scene_info,
            targets=targets,
            artifacts=artifacts,
            provenance=provenance,
            warnings=warnings,
            limitations=limitations,
            export_settings=dict(inputs.export_settings or {}),
        )
        manifest_path = tmp / "manifest.json"
        manifest_path.write_text(dumps_manifest(manifest), encoding="utf-8")
        os.chmod(manifest_path, 0o644)
        _swap_into_place(tmp, output)
    except BundleError:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        raise BundleError(f"bundle publish failed before a complete bundle was written: {exc}") from exc
    return manifest


def _swap_into_place(tmp: Path, output: Path) -> None:
    """Replace ``output`` with ``tmp`` without leaving ``tmp``'s contents half-copied."""
    if output.exists() and any(output.iterdir()):
        backup = output.with_name(output.name + ".replacing")
        if backup.exists():
            shutil.rmtree(backup)
        os.replace(output, backup)
        try:
            os.replace(tmp, output)
        except Exception:
            os.replace(backup, output)
            raise
        shutil.rmtree(backup, ignore_errors=True)
        return
    if output.exists():
        output.rmdir()
    os.replace(tmp, output)
