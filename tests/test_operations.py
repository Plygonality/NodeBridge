"""Operation registry tests."""

from __future__ import annotations

import pytest

from nodebridge.core.operations import (
    DEFAULT_OPERATION_REGISTRY,
    OperationRef,
    OperationRegistry,
    OperationSpec,
)


def test_seed_operations_are_registered() -> None:
    assert DEFAULT_OPERATION_REGISTRY.contains("math.add")
    assert DEFAULT_OPERATION_REGISTRY.contains("geometry.transform")
    assert DEFAULT_OPERATION_REGISTRY.contains("geometry.modify_position")
    assert DEFAULT_OPERATION_REGISTRY.contains("points.distribute")
    assert DEFAULT_OPERATION_REGISTRY.contains("surface_sample")
    assert DEFAULT_OPERATION_REGISTRY.contains("random.vector")
    assert DEFAULT_OPERATION_REGISTRY.contains("math.clamp")
    assert not DEFAULT_OPERATION_REGISTRY.contains("geometry.foobar")


def test_registry_grows_without_editing_defaults() -> None:
    registry = OperationRegistry(seed=())
    registry.register(OperationSpec("custom.foo", "custom", "Example"))
    registry.register(
        OperationSpec("custom.bar", "custom", aliases=("legacy.bar",))
    )
    assert registry.canonicalize("legacy.bar") == "custom.bar"
    assert registry.get("legacy.bar") is not None
    with pytest.raises(ValueError):
        registry.register(OperationSpec("custom.foo", "custom"))


def test_operation_ref_resolve() -> None:
    known = OperationRef.resolve("vector.dot")
    assert known.registered
    unknown = OperationRef.resolve("not.a.thing")
    assert not unknown.registered
    assert unknown.name == "not.a.thing"
