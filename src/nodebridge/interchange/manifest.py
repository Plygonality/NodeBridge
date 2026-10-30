"""Versioned NodeBridge bundle manifest.

``format_version`` is the manifest schema. It is not the application
version and not the Graph IR ``FORMAT_VERSION``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

BUNDLE_FORMAT = "nodebridge.bundle"
BUNDLE_FORMAT_VERSION = 1

# Always recorded. These are limits of the representation, not defects.
STANDARD_LIMITATIONS = (
    "The USD scene is an evaluated export. It is not the executable Blender node tree and cannot rebuild that tree by itself.",
    "Graph IR and Semantic IR sidecars are the lossless record of what NodeBridge serialized. USD geometry is not a substitute for them.",
    "Prim mapping is asset-level. Blender's evaluated USD export does not provide per-face Geometry Nodes provenance.",
    "Instancing, shader networks, custom attributes, and animation may be baked, partially represented, or omitted by the exporter.",
    "Translation confidence remains EXACT, EQUIVALENT, APPROXIMATE, or UNSUPPORTED in the translation report. A stage that opens is not an exact translation.",
    "A bounding-box or topology comparison is measurable evidence. It does not prove that two procedural graphs behave the same.",
    "Houdini MaterialX network code, a portable .mtlx document, and a USD UsdShade network are different artifacts. This bundle does not convert one into another by renaming.",
)


@dataclass
class Artifact:
    path: str
    sha256: str
    role: str = ""
    byte_size: int = 0

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"path": self.path, "sha256": self.sha256, "bytes": self.byte_size}
        if self.role:
            data["role"] = self.role
        return data

    @classmethod
    def from_dict(cls, data: dict) -> Artifact:
        if not isinstance(data, dict) or "path" not in data or "sha256" not in data:
            raise ValueError("artifact entries require path and sha256")
        return cls(path=str(data["path"]), sha256=str(data["sha256"]), role=str(data.get("role", "")), byte_size=int(data.get("bytes", 0)))


@dataclass
class BundleManifest:
    nodebridge_version: str
    publisher: str
    publication_id: str
    source: dict[str, Any]
    scene: dict[str, Any]
    targets: dict[str, Any] = field(default_factory=dict)
    artifacts: list[Artifact] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    export_settings: dict[str, Any] = field(default_factory=dict)
    format: str = BUNDLE_FORMAT
    format_version: int = BUNDLE_FORMAT_VERSION

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "format": self.format,
            "format_version": self.format_version,
            "nodebridge_version": self.nodebridge_version,
            "publisher": self.publisher,
            "publication_id": self.publication_id,
            "source": self.source,
            "scene": self.scene,
            "targets": self.targets,
            "artifacts": [item.as_dict() for item in sorted(self.artifacts, key=lambda item: item.path)],
            "provenance": self.provenance,
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }
        if self.export_settings:
            data["export_settings"] = self.export_settings
        return data

    @classmethod
    def from_dict(cls, data: dict) -> BundleManifest:
        if not isinstance(data, dict):
            raise ValueError("manifest must be a JSON object")
        if data.get("format") != BUNDLE_FORMAT:
            raise ValueError(f"not a NodeBridge bundle manifest (format={data.get('format')!r})")
        if data.get("format_version") != BUNDLE_FORMAT_VERSION:
            raise ValueError(f"unsupported bundle format_version {data.get('format_version')!r}")
        for key in ("nodebridge_version", "publisher", "publication_id", "source", "scene"):
            if key not in data:
                raise ValueError(f"manifest is missing {key}")
        source = data["source"]
        scene = data["scene"]
        if not isinstance(source, dict) or not isinstance(scene, dict):
            raise ValueError("manifest source and scene must be objects")
        for key in ("dcc", "graph_path", "semantic_path", "generator_id"):
            if not source.get(key):
                raise ValueError(f"manifest source is missing {key}")
        if not scene.get("usd_path"):
            raise ValueError("manifest scene is missing usd_path")
        artifacts = [Artifact.from_dict(item) for item in data.get("artifacts", [])]
        warnings = data.get("warnings", [])
        limitations = data.get("limitations", [])
        if not isinstance(warnings, list) or not isinstance(limitations, list):
            raise ValueError("manifest warnings and limitations must be arrays")
        provenance = data.get("provenance", {})
        targets = data.get("targets", {})
        export_settings = data.get("export_settings", {})
        if not isinstance(provenance, dict) or not isinstance(targets, dict) or not isinstance(export_settings, dict):
            raise ValueError("manifest provenance, targets, and export_settings must be objects")
        return cls(
            nodebridge_version=str(data["nodebridge_version"]),
            publisher=str(data["publisher"]),
            publication_id=str(data["publication_id"]),
            source=source,
            scene=scene,
            targets=targets,
            artifacts=artifacts,
            provenance=provenance,
            warnings=[str(item) for item in warnings],
            limitations=[str(item) for item in limitations],
            export_settings=export_settings,
        )


def dumps_manifest(manifest: BundleManifest) -> str:
    import json

    return json.dumps(manifest.as_dict(), indent=2, sort_keys=True) + "\n"


def loads_manifest(text: str) -> BundleManifest:
    import json

    return BundleManifest.from_dict(json.loads(text))
