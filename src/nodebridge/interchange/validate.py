"""Validate a bundle without Blender or pxr.

Validation parses JSON as data, checks hashes, and refuses paths that
escape the bundle. It does not import or execute sidecar Python.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..ir.serialization import loads_graph, loads_semantic
from .bundle import MAX_JSON_BYTES, MAX_MEMBER_BYTES, resolve_member
from .errors import BundleError, PathSecurityError
from .manifest import BundleManifest, loads_manifest
from .provenance import publication_id, sha256_file

MAX_MANIFEST_BYTES = 8 * 1024 * 1024


@dataclass
class ValidationReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manifest: dict | None = None

    def as_dict(self) -> dict:
        return {"ok": self.ok, "errors": list(self.errors), "warnings": list(self.warnings)}


def validate_bundle(path: Path, *, strict: bool = False) -> ValidationReport:
    """Validate ``path`` as a NodeBridge bundle directory."""
    root = Path(path)
    errors: list[str] = []
    warnings: list[str] = []
    if not root.is_dir():
        return ValidationReport(False, [f"not a bundle directory: {root}"])
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return ValidationReport(False, ["manifest.json is missing"])
    try:
        if manifest_path.is_symlink():
            resolve_member(root, "manifest.json")
        size = manifest_path.stat().st_size
        if size > MAX_MANIFEST_BYTES:
            return ValidationReport(False, [f"manifest.json exceeds {MAX_MANIFEST_BYTES} bytes"])
        manifest = loads_manifest(manifest_path.read_text(encoding="utf-8"))
    except PathSecurityError as exc:
        return ValidationReport(False, [str(exc)])
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return ValidationReport(False, [f"manifest.json is not a valid NodeBridge manifest: {exc}"])

    warnings.extend(manifest.warnings)
    seen: set[str] = set()
    hashed: list[tuple[str, str]] = []
    for artifact in sorted(manifest.artifacts, key=lambda item: item.path):
        if artifact.path in seen:
            errors.append(f"duplicate artifact path: {artifact.path}")
            continue
        seen.add(artifact.path)
        if artifact.path == "manifest.json":
            errors.append("manifest.json must not be listed as an artifact of itself")
            continue
        limit = MAX_JSON_BYTES if artifact.path.endswith(".json") else MAX_MEMBER_BYTES
        try:
            member = resolve_member(root, artifact.path)
        except PathSecurityError as exc:
            errors.append(str(exc))
            continue
        if not member.is_file():
            errors.append(f"missing artifact: {artifact.path}")
            continue
        byte_size = member.stat().st_size
        if byte_size > limit:
            errors.append(f"{artifact.path} exceeds the {limit} byte limit")
            continue
        digest = sha256_file(member)
        if digest != artifact.sha256:
            errors.append(f"sha256 mismatch for {artifact.path}")
            continue
        if artifact.byte_size and artifact.byte_size != byte_size:
            errors.append(f"byte size mismatch for {artifact.path}")
            continue
        hashed.append((artifact.path, digest))

    expected = publication_id(hashed) if not errors else ""
    if not errors and expected != manifest.publication_id:
        errors.append("publication_id does not match the artifact hashes")

    _check_document(root, manifest.source.get("graph_path", ""), loads_graph, "Graph IR", errors)
    _check_document(root, manifest.source.get("semantic_path", ""), loads_semantic, "Semantic IR", errors)
    scene_rel = manifest.scene.get("usd_path", "")
    _check_present(root, scene_rel, "scene", errors)
    geometry = manifest.scene.get("geometry_path")
    if geometry:
        _check_present(root, str(geometry), "geometry layer", errors)
    overlay = manifest.scene.get("provenance_overlay")
    if overlay:
        _check_present(root, str(overlay), "provenance overlay", errors)
    for target, info in sorted(manifest.targets.items()):
        if isinstance(info, dict) and info.get("script_path"):
            _check_present(root, str(info["script_path"]), f"{target} script", errors)

    listed = seen | {"manifest.json"}
    try:
        for extra in _unlisted_files(root, listed):
            warnings.append(f"unlisted file: {extra}")
    except PathSecurityError as exc:
        errors.append(str(exc))

    ok = not errors and not (strict and warnings)
    return ValidationReport(ok, errors, warnings, manifest.as_dict())


def _check_document(root: Path, relative: str, loader, label: str, errors: list[str]) -> None:
    if not relative:
        errors.append(f"{label} path is missing from the manifest")
        return
    try:
        member = resolve_member(root, relative)
    except PathSecurityError as exc:
        errors.append(str(exc))
        return
    if not member.is_file():
        errors.append(f"missing {label}: {relative}")
        return
    if member.stat().st_size > MAX_JSON_BYTES:
        errors.append(f"{label} exceeds {MAX_JSON_BYTES} bytes")
        return
    try:
        loader(member.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"{label} is not valid NodeBridge data: {exc}")


def _check_present(root: Path, relative: str, label: str, errors: list[str]) -> None:
    if not relative:
        errors.append(f"{label} path is empty")
        return
    try:
        member = resolve_member(root, relative)
    except PathSecurityError as exc:
        errors.append(str(exc))
        return
    if not member.is_file():
        errors.append(f"missing {label}: {relative}")


def _unlisted_files(root: Path, listed: set[str]) -> list[str]:
    found: list[str] = []
    root_resolved = root.resolve()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            followed = path.resolve()
            if not _inside(root_resolved, followed):
                raise PathSecurityError(f"symlink escapes the bundle: {path.relative_to(root).as_posix()}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative not in listed:
            found.append(relative)
    return found


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def require_bundle(path: Path) -> BundleManifest:
    report = validate_bundle(path)
    if report.manifest is None:
        raise BundleError("; ".join(report.errors) or f"not a bundle: {path}")
    return BundleManifest.from_dict(report.manifest)
