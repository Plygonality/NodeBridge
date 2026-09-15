"""Packaging helpers for later multi-file exports."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ExportPackage:
    """Collection of generated artefacts for one translation."""

    ir_path: Path | None = None
    script_path: Path | None = None
    extras: dict[str, Path] = field(default_factory=dict)
