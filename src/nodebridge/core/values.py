"""JSON-safe constant values attached to sockets and parameters."""

from __future__ import annotations

from typing import Any

from nodebridge.core.exceptions import SerializationError
from nodebridge.core.types import DataType, TypeRef

JSONValue = None | bool | int | float | str | list[Any] | dict[str, Any]


def normalize_value(value: Any) -> JSONValue:
    """Convert *value* to a JSON-serializable form.

    Tuples become lists. Other non-JSON types raise
    :class:`~nodebridge.core.exceptions.SerializationError`.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, tuple):
        return [normalize_value(item) for item in value]
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalize_value(item) for key, item in value.items()}
    raise SerializationError(
        f"Value is not JSON-serializable: {type(value).__name__}"
    )


def value_matches_type(value: JSONValue, type_ref: TypeRef) -> bool:
    """Return True if *value* is a plausible constant for *type_ref*.

    ``None`` is always accepted (meaning "no default"). ``UNKNOWN``,
    ``OPAQUE``, ``FIELD``, ``ATTRIBUTE``, and custom types accept any JSON
    value.
    """
    if value is None:
        return True
    builtin = type_ref.builtin
    if builtin is None or builtin in {
        DataType.UNKNOWN,
        DataType.OPAQUE,
        DataType.FIELD,
        DataType.ATTRIBUTE,
        DataType.OBJECT,
        DataType.COLLECTION,
        DataType.GEOMETRY,
        DataType.MESH,
        DataType.CURVE,
        DataType.POINT_CLOUD,
        DataType.POINTS,
        DataType.INSTANCE,
        DataType.INSTANCES,
        DataType.MATERIAL,
        DataType.TEXTURE,
        DataType.IMAGE,
        DataType.SHADER,
    }:
        return True
    if builtin is DataType.BOOLEAN:
        return isinstance(value, bool)
    if builtin is DataType.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if builtin is DataType.FLOAT:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if builtin is DataType.STRING:
        return isinstance(value, str)
    if builtin in {
        DataType.VECTOR2,
        DataType.VECTOR3,
        DataType.VECTOR4,
        DataType.COLOR,
    }:
        expected = {
            DataType.VECTOR2: 2,
            DataType.VECTOR3: 3,
            DataType.VECTOR4: 4,
            DataType.COLOR: (3, 4),
        }[builtin]
        if not isinstance(value, list):
            return False
        if isinstance(expected, tuple):
            return len(value) in expected and all(_is_number(v) for v in value)
        return len(value) == expected and all(_is_number(v) for v in value)
    if builtin in {DataType.MATRIX, DataType.TRANSFORM}:
        return isinstance(value, list)
    return True


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
