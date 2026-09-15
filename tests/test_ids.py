"""Identifier factory tests."""

from __future__ import annotations

import pytest

from nodebridge.core.ids import IdFactory, is_valid_id, require_id


def test_sequential_ids_are_deterministic() -> None:
    factory = IdFactory()
    assert factory.next("node") == "node_0001"
    assert factory.next("node") == "node_0002"
    assert factory.next("socket") == "socket_0001"


def test_uuid_ids_are_unique_and_valid() -> None:
    factory = IdFactory()
    first = factory.uuid("node")
    second = factory.uuid("node")
    assert first != second
    assert is_valid_id(first)
    assert first.startswith("node_")


def test_invalid_kind_and_id() -> None:
    factory = IdFactory()
    with pytest.raises(ValueError):
        factory.next("Node")
    assert not is_valid_id("")
    assert not is_valid_id("1bad")
    with pytest.raises(ValueError):
        require_id("***")
