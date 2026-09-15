"""Semantic operation catalog.

Operations are dotted identifiers that describe *intent*, not a node
widget in any particular application. The catalog is a registry that
grows incrementally; it is not a translation table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class OperationSpec:
    """Metadata for a registered semantic operation."""

    name: str
    category: str
    description: str = ""
    aliases: tuple[str, ...] = ()


# Seed operations used by early milestones. More are added incrementally.
SEED_OPERATIONS: tuple[OperationSpec, ...] = (
    OperationSpec("math.add", "math", "Component-wise or scalar addition."),
    OperationSpec("math.subtract", "math", "Component-wise or scalar subtraction."),
    OperationSpec("math.multiply", "math", "Component-wise or scalar multiplication."),
    OperationSpec("math.divide", "math", "Component-wise or scalar division."),
    OperationSpec("math.power", "math", "Raise a value to a power."),
    OperationSpec("vector.add", "vector", "Vector addition."),
    OperationSpec("vector.subtract", "vector", "Vector subtraction."),
    OperationSpec("vector.normalize", "vector", "Unit-length vector."),
    OperationSpec("vector.cross", "vector", "3D cross product."),
    OperationSpec("vector.dot", "vector", "Dot product."),
    OperationSpec("geometry.transform", "geometry", "Apply a transform to geometry."),
    OperationSpec("geometry.join", "geometry", "Merge multiple geometries."),
    OperationSpec("geometry.instance", "geometry", "Instance geometry on points."),
    OperationSpec(
        "geometry.realize_instances",
        "geometry",
        "Convert instances into real geometry.",
    ),
    OperationSpec(
        "geometry.modify_position",
        "geometry",
        "Write a new position field onto geometry.",
    ),
    OperationSpec("attribute.read", "attribute", "Read a named attribute as a field."),
    OperationSpec("attribute.write", "attribute", "Write a field onto an attribute."),
    OperationSpec("selection.compare", "selection", "Build a boolean selection."),
    OperationSpec("procedural.noise", "procedural", "Procedural noise field."),
    OperationSpec("procedural.voronoi", "procedural", "Voronoi / Worley field."),
    OperationSpec("texture.sample", "texture", "Sample a texture at a coordinate."),
    OperationSpec(
        "shader.principled_surface",
        "shader",
        "Physically based surface shading model.",
    ),
    OperationSpec("color.mix", "color", "Mix two colors."),
    OperationSpec("color.ramp", "color", "Map a scalar through a color ramp."),
    OperationSpec("graph.input", "graph", "Exposed graph input."),
    OperationSpec("graph.output", "graph", "Exposed graph output."),
    OperationSpec("graph.group", "graph", "Call a nested / reusable group."),
    OperationSpec("unknown", "unknown", "Unrecognized source operation."),
)


class OperationRegistry:
    """Growing catalog of semantic operations.

    Translation mappings live in the translator layer, not here. This
    registry only answers: "do we know what this operation *means*?"
    """

    def __init__(self, seed: Iterable[OperationSpec] | None = None) -> None:
        self._operations: dict[str, OperationSpec] = {}
        self._aliases: dict[str, str] = {}
        for spec in seed if seed is not None else SEED_OPERATIONS:
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
