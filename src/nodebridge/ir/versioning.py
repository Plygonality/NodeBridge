"""IR document versioning and migration hooks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from nodebridge.core.exceptions import VersionError

PACKAGE_VERSION = "0.3.0"
IR_VERSION = "1"
SUPPORTED_IR_VERSIONS = frozenset({"1"})


class Migration(Protocol):
    """Upgrade a serialized document from one IR version to the next."""

    from_version: str
    to_version: str

    def apply(self, data: dict[str, Any]) -> dict[str, Any]:
        """Return a document dict at :attr:`to_version`."""
        ...


@dataclass(frozen=True)
class IdentityMigration:
    """No-op migration used as a placeholder for future upgrades."""

    from_version: str
    to_version: str

    def apply(self, data: dict[str, Any]) -> dict[str, Any]:
        upgraded = dict(data)
        upgraded["ir_version"] = self.to_version
        return upgraded


class MigrationRegistry:
    """Chain of version-to-version document migrations."""

    def __init__(self) -> None:
        self._steps: dict[str, Migration] = {}

    def register(self, migration: Migration) -> None:
        if migration.from_version in self._steps:
            raise ValueError(
                f"Migration already registered from {migration.from_version}"
            )
        self._steps[migration.from_version] = migration

    def upgrade(self, data: dict[str, Any], *, target: str = IR_VERSION) -> dict[str, Any]:
        """Walk *data* forward until its ``ir_version`` equals *target*."""
        current = dict(data)
        seen: set[str] = set()
        while str(current.get("ir_version", "")) != target:
            version = str(current.get("ir_version", ""))
            if version in seen:
                raise VersionError(f"Migration cycle detected at IR version {version}")
            seen.add(version)
            step = self._steps.get(version)
            if step is None:
                raise VersionError(
                    f"No migration path from IR version {version!r} to {target!r}"
                )
            current = step.apply(current)
        return current


DEFAULT_MIGRATIONS = MigrationRegistry()


def parse_ir_version(value: object) -> str:
    """Normalize an IR version token to a string."""
    if value is None:
        raise VersionError("Document is missing ir_version")
    text = str(value).strip()
    if not text:
        raise VersionError("Document ir_version is empty")
    return text


def ensure_supported(
    ir_version: str,
    *,
    supported: frozenset[str] = SUPPORTED_IR_VERSIONS,
    migrate: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    data: dict[str, Any] | None = None,
) -> str:
    """Accept a known version, or migrate *data* when a hook is provided."""
    if ir_version in supported:
        return ir_version
    if migrate is not None and data is not None:
        upgraded = migrate(data)
        upgraded_version = parse_ir_version(upgraded.get("ir_version"))
        if upgraded_version in supported:
            return upgraded_version
    raise VersionError(
        f"Unsupported IR version {ir_version!r}; supported: {sorted(supported)}"
    )
