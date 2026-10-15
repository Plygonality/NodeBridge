"""NodeBridge data types and connection compatibility.

Types describe procedural values, not Blender socket identifiers. A Blender
``NodeSocketGeometry`` is metadata on the graph IR. The semantic type is
``Geometry``, ``Mesh``, ``Curve``, ``Points``, or ``Instances``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DataType(str, Enum):
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    VECTOR2 = "vector2"
    VECTOR3 = "vector3"
    VECTOR4 = "vector4"
    COLOR = "color"
    MATRIX = "matrix"
    STRING = "string"
    GEOMETRY = "geometry"
    MESH = "mesh"
    CURVE = "curve"
    POINTS = "points"
    INSTANCES = "instances"
    MATERIAL = "material"
    TEXTURE = "texture"
    OBJECT_REFERENCE = "object_reference"
    COLLECTION_REFERENCE = "collection_reference"
    FIELD = "field"
    ANY = "any"


GEOMETRY_TYPES = {
    DataType.GEOMETRY,
    DataType.MESH,
    DataType.CURVE,
    DataType.POINTS,
    DataType.INSTANCES,
}

SCALAR_TYPES = {DataType.BOOL, DataType.INT, DataType.FLOAT}


class TypeCompatibility(str, Enum):
    EXACT = "exact"
    SAFE = "safe"
    LOSSY = "lossy"
    INCOMPATIBLE = "incompatible"


@dataclass(frozen=True)
class TypeRef:
    """A concrete type, optionally evaluated as a field over a domain."""

    base: DataType
    field: bool = False

    def __str__(self) -> str:
        if self.field and self.base is not DataType.FIELD:
            return f"field<{self.base.value}>"
        return self.base.value


def compatibility(source: DataType | TypeRef, target: DataType | TypeRef) -> TypeCompatibility:
    """How safely a value of ``source`` can feed an input of ``target``."""

    src = source if isinstance(source, TypeRef) else TypeRef(source)
    dst = target if isinstance(target, TypeRef) else TypeRef(target)
    if dst.base is DataType.ANY or src.base is DataType.ANY:
        return TypeCompatibility.EXACT if src.base is dst.base else TypeCompatibility.SAFE
    if src.field and not dst.field and dst.base not in GEOMETRY_TYPES:
        return TypeCompatibility.INCOMPATIBLE
    base = _base_compatibility(src.base, dst.base)
    if base is TypeCompatibility.INCOMPATIBLE:
        return base
    if src.field and dst.field:
        return base
    if not src.field and dst.field and base is not TypeCompatibility.INCOMPATIBLE:
        return TypeCompatibility.SAFE if base is TypeCompatibility.EXACT else base
    return base


def _base_compatibility(source: DataType, target: DataType) -> TypeCompatibility:
    if source is target:
        return TypeCompatibility.EXACT
    if source is DataType.INT and target is DataType.FLOAT:
        return TypeCompatibility.SAFE
    if source is DataType.FLOAT and target is DataType.INT:
        return TypeCompatibility.LOSSY
    if source is DataType.BOOL and target in {DataType.INT, DataType.FLOAT}:
        return TypeCompatibility.SAFE
    if source is DataType.INT and target is DataType.BOOL:
        return TypeCompatibility.LOSSY
    if source is DataType.COLOR and target is DataType.VECTOR3:
        return TypeCompatibility.LOSSY
    if source is DataType.VECTOR3 and target is DataType.COLOR:
        return TypeCompatibility.SAFE
    if source is DataType.VECTOR3 and target is DataType.VECTOR4:
        return TypeCompatibility.SAFE
    if source is DataType.VECTOR4 and target is DataType.VECTOR3:
        return TypeCompatibility.LOSSY
    if source is DataType.VECTOR2 and target is DataType.VECTOR3:
        return TypeCompatibility.SAFE
    if source is DataType.FLOAT and target is DataType.VECTOR3:
        return TypeCompatibility.SAFE
    if target is DataType.GEOMETRY and source in GEOMETRY_TYPES:
        return TypeCompatibility.SAFE
    if source is DataType.GEOMETRY and target in GEOMETRY_TYPES - {DataType.GEOMETRY}:
        return TypeCompatibility.LOSSY
    if source in GEOMETRY_TYPES and target in GEOMETRY_TYPES:
        return TypeCompatibility.INCOMPATIBLE
    return TypeCompatibility.INCOMPATIBLE


def is_compatible(source: DataType | TypeRef, target: DataType | TypeRef) -> bool:
    return compatibility(source, target) is not TypeCompatibility.INCOMPATIBLE


_BLENDER_SOCKETS = {
    "NodeSocketBool": DataType.BOOL,
    "NodeSocketInt": DataType.INT,
    "NodeSocketIntUnsigned": DataType.INT,
    "NodeSocketFloat": DataType.FLOAT,
    "NodeSocketFloatFactor": DataType.FLOAT,
    "NodeSocketFloatAngle": DataType.FLOAT,
    "NodeSocketFloatDistance": DataType.FLOAT,
    "NodeSocketVector": DataType.VECTOR3,
    "NodeSocketVectorEuler": DataType.VECTOR3,
    "NodeSocketVectorXYZ": DataType.VECTOR3,
    "NodeSocketVectorTranslation": DataType.VECTOR3,
    "NodeSocketRotation": DataType.VECTOR3,
    "NodeSocketColor": DataType.COLOR,
    "NodeSocketString": DataType.STRING,
    "NodeSocketGeometry": DataType.GEOMETRY,
    "NodeSocketMatrix": DataType.MATRIX,
    "NodeSocketMaterial": DataType.MATERIAL,
    "NodeSocketTexture": DataType.TEXTURE,
    "NodeSocketImage": DataType.TEXTURE,
    "NodeSocketObject": DataType.OBJECT_REFERENCE,
    "NodeSocketCollection": DataType.COLLECTION_REFERENCE,
    "NodeSocketShader": DataType.ANY,
    "NodeSocketVirtual": DataType.ANY,
}


def data_type_from_blender_socket(socket_type: str) -> DataType:
    """Map a Blender socket idname to a NodeBridge type."""

    if socket_type in _BLENDER_SOCKETS:
        return _BLENDER_SOCKETS[socket_type]
    lowered = socket_type.lower()
    if "float" in lowered or "factor" in lowered or "angle" in lowered:
        return DataType.FLOAT
    if "int" in lowered:
        return DataType.INT
    if "bool" in lowered:
        return DataType.BOOL
    if "color" in lowered:
        return DataType.COLOR
    if "vector" in lowered or "rotation" in lowered:
        return DataType.VECTOR3
    if "geometry" in lowered or "mesh" in lowered:
        return DataType.GEOMETRY
    if "material" in lowered:
        return DataType.MATERIAL
    if "image" in lowered or "texture" in lowered:
        return DataType.TEXTURE
    if "string" in lowered:
        return DataType.STRING
    if "object" in lowered:
        return DataType.OBJECT_REFERENCE
    if "collection" in lowered:
        return DataType.COLLECTION_REFERENCE
    return DataType.ANY
