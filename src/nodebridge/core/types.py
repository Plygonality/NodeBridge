"""Extensible data-type system for the NodeBridge IR.

Builtin types are listed in :class:`DataType`. Additional types may be
registered at runtime through :class:`TypeRegistry` without changing the
core enum. Sockets and parameters store a :class:`TypeRef`, never a
source-application type name.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from nodebridge.core.exceptions import NodeBridgeError


class DataType(str, Enum):
    """Builtin IR data types.

    These names describe *semantics*, not a particular application's socket
    widgets. Geometry subtypes (``MESH``, ``CURVE``, ...) are refinements of
    ``GEOMETRY`` and remain compatible with it.
    """

    FLOAT = "float"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    VECTOR2 = "vector2"
    VECTOR3 = "vector3"
    VECTOR4 = "vector4"
    COLOR = "color"
    STRING = "string"
    MATRIX = "matrix"
    GEOMETRY = "geometry"
    MESH = "mesh"
    CURVE = "curve"
    POINT_CLOUD = "point_cloud"
    INSTANCE = "instance"
    MATERIAL = "material"
    TEXTURE = "texture"
    IMAGE = "image"
    SHADER = "shader"
    UNKNOWN = "unknown"

    @classmethod
    def try_parse(cls, value: str) -> DataType | None:
        """Return the builtin type for *value*, or ``None`` if it is custom."""
        try:
            return cls(value)
        except ValueError:
            return None


class TypeCompatibility(str, Enum):
    """How two type references relate for connection purposes."""

    IDENTICAL = "identical"
    EQUIVALENT = "equivalent"
    CONVERTIBLE = "convertible"
    INCOMPATIBLE = "incompatible"


# Geometry refinements are still geometry. Used for EQUIVALENT compatibility.
_GEOMETRY_SUBTYPES = frozenset(
    {
        DataType.MESH,
        DataType.CURVE,
        DataType.POINT_CLOUD,
        DataType.INSTANCE,
    }
)

# Implicit numeric / vector conversions that a later rewrite pass may insert.
_CONVERTIBLE_PAIRS = frozenset(
    {
        (DataType.FLOAT, DataType.INTEGER),
        (DataType.INTEGER, DataType.FLOAT),
        (DataType.FLOAT, DataType.BOOLEAN),
        (DataType.BOOLEAN, DataType.FLOAT),
        (DataType.INTEGER, DataType.BOOLEAN),
        (DataType.BOOLEAN, DataType.INTEGER),
        (DataType.VECTOR3, DataType.COLOR),
        (DataType.COLOR, DataType.VECTOR3),
        (DataType.VECTOR4, DataType.COLOR),
        (DataType.COLOR, DataType.VECTOR4),
        (DataType.VECTOR3, DataType.VECTOR4),
        (DataType.VECTOR4, DataType.VECTOR3),
        (DataType.VECTOR2, DataType.VECTOR3),
        (DataType.VECTOR3, DataType.VECTOR2),
    }
)


@dataclass(frozen=True)
class TypeRef:
    """Reference to a builtin or custom data type.

    Custom types use a dotted name (for example ``usd.token``) and are
    treated as unknown for compatibility until a registry entry exists.
    """

    name: str
    builtin: DataType | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("TypeRef.name must be non-empty")

    @classmethod
    def of(cls, type_name: str | DataType | TypeRef) -> TypeRef:
        """Build a :class:`TypeRef` from a name, enum member, or existing ref."""
        if isinstance(type_name, TypeRef):
            return type_name
        if isinstance(type_name, DataType):
            return cls(name=type_name.value, builtin=type_name)
        builtin = DataType.try_parse(type_name)
        return cls(name=type_name, builtin=builtin)

    @property
    def is_builtin(self) -> bool:
        return self.builtin is not None

    @property
    def is_unknown(self) -> bool:
        return self.builtin is DataType.UNKNOWN or self.builtin is None

    def __str__(self) -> str:
        return self.name


def compare_types(source: TypeRef, target: TypeRef) -> TypeCompatibility:
    """Classify the compatibility of a connection from *source* to *target*."""
    if source.name == target.name:
        return TypeCompatibility.IDENTICAL

    src = source.builtin
    dst = target.builtin

    if src is DataType.UNKNOWN or dst is DataType.UNKNOWN:
        return TypeCompatibility.CONVERTIBLE

    if src is None or dst is None:
        return TypeCompatibility.INCOMPATIBLE

    if src is DataType.GEOMETRY and dst in _GEOMETRY_SUBTYPES:
        return TypeCompatibility.EQUIVALENT
    if dst is DataType.GEOMETRY and src in _GEOMETRY_SUBTYPES:
        return TypeCompatibility.EQUIVALENT
    if src in _GEOMETRY_SUBTYPES and dst in _GEOMETRY_SUBTYPES:
        return TypeCompatibility.CONVERTIBLE

    if (src, dst) in _CONVERTIBLE_PAIRS:
        return TypeCompatibility.CONVERTIBLE

    return TypeCompatibility.INCOMPATIBLE


class TypeRegistry:
    """Extensible catalog of known type names.

    Builtin types are always present. Custom types can be registered by
    adapters or backends without modifying this module.
    """

    def __init__(self) -> None:
        self._custom: dict[str, str] = {}

    def register(self, name: str, *, description: str = "") -> TypeRef:
        """Register a custom type and return its :class:`TypeRef`."""
        if not name or DataType.try_parse(name) is not None:
            raise NodeBridgeError(
                f"Cannot register {name!r}: empty or collides with a builtin type"
            )
        if name in self._custom:
            raise NodeBridgeError(f"Type already registered: {name}")
        self._custom[name] = description
        return TypeRef.of(name)

    def resolve(self, name: str | DataType | TypeRef) -> TypeRef:
        """Resolve *name* to a :class:`TypeRef`.

        Unknown names become ``UNKNOWN`` builtins with the original name
        preserved so they survive round-trips and diagnostics.
        """
        if isinstance(name, TypeRef):
            return name
        if isinstance(name, DataType):
            return TypeRef.of(name)
        builtin = DataType.try_parse(name)
        if builtin is not None:
            return TypeRef.of(builtin)
        if name in self._custom:
            return TypeRef(name=name, builtin=None)
        return TypeRef(name=name, builtin=None)

    def known_names(self) -> list[str]:
        """Return builtin names followed by registered custom names."""
        names = [member.value for member in DataType]
        names.extend(sorted(self._custom))
        return names

    def is_registered(self, name: str) -> bool:
        return DataType.try_parse(name) is not None or name in self._custom


DEFAULT_TYPE_REGISTRY = TypeRegistry()


def builtin_type_names() -> Iterable[str]:
    """Yield the names of every builtin :class:`DataType`."""
    return (member.value for member in DataType)
