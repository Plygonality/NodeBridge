from nodebridge.ir.types import (
    DataType,
    TypeCompatibility,
    TypeRef,
    compatibility,
    data_type_from_blender_socket,
    is_compatible,
)


def test_exact_and_lossy_numeric_conversions():
    assert compatibility(DataType.FLOAT, DataType.FLOAT) is TypeCompatibility.EXACT
    assert compatibility(DataType.INT, DataType.FLOAT) is TypeCompatibility.SAFE
    assert compatibility(DataType.FLOAT, DataType.INT) is TypeCompatibility.LOSSY


def test_geometry_accepts_specific_types_but_not_scalars():
    assert compatibility(DataType.MESH, DataType.GEOMETRY) is TypeCompatibility.SAFE
    assert compatibility(DataType.GEOMETRY, DataType.CURVE) is TypeCompatibility.LOSSY
    assert compatibility(DataType.GEOMETRY, DataType.FLOAT) is TypeCompatibility.INCOMPATIBLE
    assert not is_compatible(DataType.POINTS, DataType.COLOR)


def test_constant_can_feed_a_field_and_a_field_cannot_feed_a_scalar_blindly():
    assert compatibility(TypeRef(DataType.FLOAT), TypeRef(DataType.FLOAT, field=True)) is TypeCompatibility.SAFE
    assert (
        compatibility(TypeRef(DataType.FLOAT, field=True), TypeRef(DataType.FLOAT, field=False))
        is TypeCompatibility.INCOMPATIBLE
    )


def test_color_and_blender_socket_names():
    assert compatibility(DataType.VECTOR3, DataType.COLOR) is TypeCompatibility.SAFE
    assert compatibility(DataType.COLOR, DataType.VECTOR3) is TypeCompatibility.LOSSY
    assert data_type_from_blender_socket("NodeSocketGeometry") is DataType.GEOMETRY
    assert data_type_from_blender_socket("NodeSocketFloatDistance") is DataType.FLOAT
    assert data_type_from_blender_socket("NodeSocketRotation") is DataType.VECTOR3
