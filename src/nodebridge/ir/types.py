"""NodeBridge data types and conversion rules.

Types are DCC independent. ``TypeRef`` adds *field-ness*: a Geometry Nodes
socket can carry a single value or a field evaluated per element.
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
    ROTATION = "rotation"
    MATRIX = "matrix"
    STRING = "string"
    MENU = "menu"
    GEOMETRY = "geometry"
    MESH = "mesh"
    CURVE = "curve"
    POINTS = "points"
    INSTANCES = "instances"
    MATERIAL = "material"
    TEXTURE = "texture"
    IMAGE = "image"
    SHADER = "shader"
    OBJECT = "object"
    COLLECTION = "collection"
    FIELD = "field"
    ANY = "any"


GEOMETRY_TYPES = frozenset({DataType.GEOMETRY, DataType.MESH, DataType.CURVE, DataType.POINTS, DataType.INSTANCES})
NUMERIC_TYPES = frozenset(
    {DataType.BOOL, DataType.INT, DataType.FLOAT, DataType.VECTOR2, DataType.VECTOR3, DataType.VECTOR4, DataType.COLOR, DataType.ROTATION}
)
REFERENCE_TYPES = frozenset({DataType.MATERIAL, DataType.TEXTURE, DataType.IMAGE, DataType.OBJECT, DataType.COLLECTION})

COMPONENT_COUNT = {
    DataType.BOOL: 1,
    DataType.INT: 1,
    DataType.FLOAT: 1,
    DataType.VECTOR2: 2,
    DataType.VECTOR3: 3,
    DataType.VECTOR4: 4,
    DataType.COLOR: 4,
    DataType.ROTATION: 3,
}


class Conversion(str, Enum):
    IDENTITY = "identity"
    IMPLICIT = "implicit"  # lossless or conventional (float -> vector broadcast)
    LOSSY = "lossy"  # allowed, but information is lost (vector -> float average)
    INVALID = "invalid"


@dataclass(frozen=True)
class TypeRef:
    base: DataType
    field: bool = False

    def __str__(self) -> str:
        return f"field<{self.base.value}>" if self.field else self.base.value

    def as_dict(self) -> dict:
        return {"base": self.base.value, "field": self.field}

    @classmethod
    def from_dict(cls, data: dict | str) -> "TypeRef":
        if isinstance(data, str):
            return cls(DataType(data))
        return cls(DataType(data["base"]), bool(data.get("field", False)))


_LOSSLESS: dict[DataType, set[DataType]] = {
    DataType.BOOL: {DataType.INT, DataType.FLOAT, DataType.VECTOR3, DataType.COLOR},
    DataType.INT: {DataType.FLOAT, DataType.VECTOR3, DataType.COLOR},
    DataType.FLOAT: {DataType.VECTOR2, DataType.VECTOR3, DataType.VECTOR4, DataType.COLOR, DataType.ROTATION},
    DataType.VECTOR3: {DataType.COLOR, DataType.ROTATION, DataType.VECTOR4},
    DataType.ROTATION: {DataType.VECTOR3},
    DataType.COLOR: {DataType.VECTOR4},
}
_LOSSY: dict[DataType, set[DataType]] = {
    DataType.FLOAT: {DataType.INT, DataType.BOOL},
    DataType.INT: {DataType.BOOL},
    DataType.VECTOR3: {DataType.FLOAT, DataType.INT, DataType.BOOL, DataType.VECTOR2},
    DataType.VECTOR2: {DataType.FLOAT, DataType.VECTOR3},
    DataType.COLOR: {DataType.FLOAT, DataType.INT, DataType.BOOL, DataType.VECTOR3},
    DataType.VECTOR4: {DataType.VECTOR3, DataType.COLOR, DataType.FLOAT},
}


def conversion(source: DataType, target: DataType) -> Conversion:
    """Classify a connection between two base types (Blender-compatible rules)."""
    if source == target or DataType.ANY in (source, target):
        return Conversion.IDENTITY
    if source in GEOMETRY_TYPES and target in GEOMETRY_TYPES:
        if target == DataType.GEOMETRY:
            return Conversion.IDENTITY
        if source == DataType.GEOMETRY:
            return Conversion.IMPLICIT
        return Conversion.INVALID
    if target == DataType.FIELD and source in NUMERIC_TYPES:
        return Conversion.IMPLICIT
    if target in _LOSSLESS.get(source, set()):
        return Conversion.IMPLICIT
    if target in _LOSSY.get(source, set()):
        return Conversion.LOSSY
    return Conversion.INVALID


def connection(source: TypeRef, target: TypeRef, *, target_accepts_field: bool = True) -> Conversion:
    """Classify a link including field-ness.

    A field may only flow into a socket that accepts fields; a single value
    may always flow into a field socket.
    """
    if source.field and not target_accepts_field:
        return Conversion.INVALID
    return conversion(source.base, target.base)


def convert_value(value, source: DataType, target: DataType):
    """Convert a constant the way Blender's implicit conversions do."""
    if source == target or value is None:
        return value
    if target in (DataType.FLOAT,):
        if isinstance(value, (list, tuple)):
            items = list(value)[:3]
            return sum(float(v) for v in items) / max(len(items), 1)
        return float(value)
    if target == DataType.INT:
        if isinstance(value, (list, tuple)):
            value = convert_value(value, source, DataType.FLOAT)
        return int(round(float(value)))
    if target == DataType.BOOL:
        if isinstance(value, (list, tuple)):
            return any(float(v) != 0.0 for v in value)
        return bool(value)
    if target in (DataType.VECTOR3, DataType.ROTATION):
        if isinstance(value, (list, tuple)):
            items = [float(v) for v in value]
            return (items + [0.0, 0.0, 0.0])[:3]
        return [float(value)] * 3
    if target in (DataType.COLOR, DataType.VECTOR4):
        if isinstance(value, (list, tuple)):
            items = [float(v) for v in value]
            return (items + [0.0, 0.0, 0.0, 1.0][len(items):])[:4]
        return [float(value)] * 3 + [1.0]
    if target == DataType.VECTOR2:
        if isinstance(value, (list, tuple)):
            return [float(value[0]), float(value[1])]
        return [float(value)] * 2
    return value


BLENDER_SOCKET_TYPES: dict[str, DataType] = {
    "VALUE": DataType.FLOAT,
    "INT": DataType.INT,
    "BOOLEAN": DataType.BOOL,
    "VECTOR": DataType.VECTOR3,
    "RGBA": DataType.COLOR,
    "ROTATION": DataType.ROTATION,
    "MATRIX": DataType.MATRIX,
    "STRING": DataType.STRING,
    "MENU": DataType.MENU,
    "SHADER": DataType.SHADER,
    "GEOMETRY": DataType.GEOMETRY,
    "OBJECT": DataType.OBJECT,
    "COLLECTION": DataType.COLLECTION,
    "MATERIAL": DataType.MATERIAL,
    "TEXTURE": DataType.TEXTURE,
    "IMAGE": DataType.IMAGE,
}

BLENDER_INTERFACE_TYPES: dict[str, DataType] = {
    "NodeSocketFloat": DataType.FLOAT,
    "NodeSocketInt": DataType.INT,
    "NodeSocketBool": DataType.BOOL,
    "NodeSocketVector": DataType.VECTOR3,
    "NodeSocketColor": DataType.COLOR,
    "NodeSocketRotation": DataType.ROTATION,
    "NodeSocketMatrix": DataType.MATRIX,
    "NodeSocketString": DataType.STRING,
    "NodeSocketMenu": DataType.MENU,
    "NodeSocketShader": DataType.SHADER,
    "NodeSocketGeometry": DataType.GEOMETRY,
    "NodeSocketObject": DataType.OBJECT,
    "NodeSocketCollection": DataType.COLLECTION,
    "NodeSocketMaterial": DataType.MATERIAL,
    "NodeSocketTexture": DataType.TEXTURE,
    "NodeSocketImage": DataType.IMAGE,
}


def blender_socket_type(socket_type: str) -> DataType:
    return BLENDER_SOCKET_TYPES.get(socket_type, DataType.ANY)


def blender_interface_type(bl_socket_idname: str) -> DataType:
    for prefix, data_type in BLENDER_INTERFACE_TYPES.items():
        if bl_socket_idname == prefix or bl_socket_idname.startswith(prefix):
            return data_type
    return DataType.ANY
