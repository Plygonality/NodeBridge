"""Semantic operation catalog.

Operations are dotted identifiers that describe *intent*, not a node
widget in any particular application. The catalog is a registry that
grows incrementally; it is not a translation table.

Host mappings live in host plugins. This registry only answers: "do we
know what this operation *means*?"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from nodebridge.core.values import JSONValue


@dataclass(frozen=True)
class PortSpec:
    """One named input or output on a semantic operation."""

    name: str
    data_type: str
    optional: bool = False
    field: bool = False
    description: str = ""


@dataclass(frozen=True)
class ParameterSpec:
    """One named constant parameter on a semantic operation."""

    name: str
    data_type: str
    default: JSONValue = None
    description: str = ""


@dataclass(frozen=True)
class OperationSpec:
    """Metadata for a registered semantic operation."""

    name: str
    category: str
    description: str = ""
    aliases: tuple[str, ...] = ()
    inputs: tuple[PortSpec, ...] = ()
    outputs: tuple[PortSpec, ...] = ()
    parameters: tuple[ParameterSpec, ...] = ()
    deterministic: bool = True
    side_effects: bool = False
    domain: str = ""
    field_behavior: str = ""
    instance_behavior: str = ""
    required_capabilities: tuple[str, ...] = ()

    def input_names(self) -> list[str]:
        return [port.name for port in self.inputs]

    def output_names(self) -> list[str]:
        return [port.name for port in self.outputs]

    def as_dict(self) -> dict[str, object]:
        """Machine-readable operation description."""
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "aliases": list(self.aliases),
            "inputs": [
                {
                    "name": port.name,
                    "data_type": port.data_type,
                    "optional": port.optional,
                    "field": port.field,
                    "description": port.description,
                }
                for port in self.inputs
            ],
            "outputs": [
                {
                    "name": port.name,
                    "data_type": port.data_type,
                    "optional": port.optional,
                    "field": port.field,
                    "description": port.description,
                }
                for port in self.outputs
            ],
            "parameters": [
                {
                    "name": parameter.name,
                    "data_type": parameter.data_type,
                    "default": parameter.default,
                    "description": parameter.description,
                }
                for parameter in self.parameters
            ],
            "deterministic": self.deterministic,
            "side_effects": self.side_effects,
            "domain": self.domain,
            "field_behavior": self.field_behavior,
            "instance_behavior": self.instance_behavior,
            "required_capabilities": list(self.required_capabilities),
        }


class OperationRegistry:
    """Growing catalog of semantic operations.

    Translation mappings live in host plugins, not here.
    """

    def __init__(self, seed: Iterable[OperationSpec] | None = None) -> None:
        self._operations: dict[str, OperationSpec] = {}
        self._aliases: dict[str, str] = {}
        if seed is None:
            from nodebridge.core.catalog import SEED_OPERATIONS

            seed = SEED_OPERATIONS
        for spec in seed:
            self.register(spec)

    def register(self, spec: OperationSpec) -> None:
        """Add an operation. Names and aliases must be unique."""
        if spec.name in self._operations or spec.name in self._aliases:
            raise ValueError(f"Operation already registered: {spec.name}")
        self._operations[spec.name] = spec
        for alias in spec.aliases:
            if alias in self._operations or alias in self._aliases:
                raise ValueError(f"Operation alias already registered: {alias}")
            self._aliases[alias] = spec.name

    def canonicalize(self, name: str) -> str:
        """Return the canonical name for *name*, or *name* if unknown."""
        if name in self._operations:
            return name
        return self._aliases.get(name, name)

    def get(self, name: str) -> OperationSpec | None:
        """Return the spec for *name*, resolving aliases."""
        canonical = self.canonicalize(name)
        return self._operations.get(canonical)

    def contains(self, name: str) -> bool:
        """Return True if *name* is a known operation or alias."""
        return self.get(name) is not None

    def names(self) -> list[str]:
        """Sorted canonical operation names."""
        return sorted(self._operations)

    def by_category(self, category: str) -> list[OperationSpec]:
        """Operations in *category*, sorted by name."""
        return sorted(
            (spec for spec in self._operations.values() if spec.category == category),
            key=lambda spec: spec.name,
        )

    def categories(self) -> list[str]:
        """Sorted unique category names."""
        return sorted({spec.category for spec in self._operations.values()})


DEFAULT_OPERATION_REGISTRY = OperationRegistry()


@dataclass
class OperationRef:
    """An operation identifier plus optional unresolved source fallback."""

    name: str
    registered: bool = True
    extra: dict[str, str] = field(default_factory=dict)

    @classmethod
    def resolve(
        cls,
        name: str,
        registry: OperationRegistry | None = None,
    ) -> OperationRef:
        """Look *name* up in *registry* (default catalog)."""
        catalog = registry or DEFAULT_OPERATION_REGISTRY
        spec = catalog.get(name)
        if spec is None:
            return cls(name=name, registered=False)
        return cls(name=spec.name, registered=True)
