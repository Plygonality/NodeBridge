"""Blender socket-type mapping helpers."""

from nodebridge.core.types import DataType, TypeRef

_BLENDER_SOCKETS = {
    "NodeSocketFloat": DataType.FLOAT,
    "NodeSocketInt": DataType.INTEGER,
    "NodeSocketBool": DataType.BOOLEAN,
    "NodeSocketVector": DataType.VECTOR3,
    "NodeSocketColor": DataType.COLOR,
    "NodeSocketString": DataType.STRING,
    "NodeSocketGeometry": DataType.GEOMETRY,
    "NodeSocketObject": DataType.OBJECT,
    "NodeSocketCollection": DataType.COLLECTION,
    "NodeSocketMaterial": DataType.MATERIAL,
    "NodeSocketImage": DataType.IMAGE,
    "NodeSocketTexture": DataType.TEXTURE,
    "NodeSocketShader": DataType.SHADER,
    "NodeSocketMatrix": DataType.MATRIX,
    "NodeSocketRotation": DataType.VECTOR3,
}


def map_blender_socket_type(bl_idname: str) -> TypeRef:
    """Map a Blender socket bl_idname onto a host-independent TypeRef."""
    builtin = _BLENDER_SOCKETS.get(bl_idname)
    if builtin is None:
        return TypeRef.of(DataType.UNKNOWN)
    return TypeRef.of(builtin)
