"""Type system expansions and socket mapping."""

from __future__ import annotations

from nodebridge.adapters.blender.sockets import map_blender_socket_type
from nodebridge.core.types import DataType, TypeCompatibility, TypeRef, compare_types


def test_new_types_exist() -> None:
    assert DataType.TRANSFORM.value == "transform"
    assert DataType.OBJECT.value == "object"
    assert DataType.OPAQUE.value == "opaque"
    assert DataType.POINTS.value == "points"


def test_points_and_instances_are_equivalent_to_siblings() -> None:
    assert (
        compare_types(TypeRef.of(DataType.POINTS), TypeRef.of(DataType.POINT_CLOUD))
        is TypeCompatibility.EQUIVALENT
    )
    assert (
        compare_types(TypeRef.of(DataType.INSTANCES), TypeRef.of(DataType.INSTANCE))
        is TypeCompatibility.EQUIVALENT
    )
    assert (
        compare_types(TypeRef.of(DataType.MATRIX), TypeRef.of(DataType.TRANSFORM))
        is TypeCompatibility.CONVERTIBLE
    )


def test_blender_socket_mapping() -> None:
    assert map_blender_socket_type("NodeSocketGeometry").builtin is DataType.GEOMETRY
    assert map_blender_socket_type("NodeSocketVector").builtin is DataType.VECTOR3
    assert map_blender_socket_type("NodeSocketNope").builtin is DataType.UNKNOWN
