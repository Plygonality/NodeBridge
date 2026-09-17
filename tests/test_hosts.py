"""Host registry and plugin contract tests."""

from __future__ import annotations

import pytest

from nodebridge.core.exceptions import HostError
from nodebridge.core.node import IRNode
from nodebridge.hosts import get_host, list_hosts, register_host
from nodebridge.hosts.registry import HostRegistry


def test_builtin_hosts_are_registered() -> None:
    assert list_hosts() == ["blender", "houdini", "unreal"]
    blender = get_host("blender")
    assert blender.display_name == "Blender"
    assert "geometry_nodes" in blender.graph_systems
    assert blender.frontend.application == "blender"
    assert blender.backend.name == "blender"
    assert get_host("ue5").id == "unreal"
    assert get_host("houdini-sop").id == "houdini"


def test_duplicate_host_registration_rejected() -> None:
    registry = HostRegistry()
    registry.register(get_host("blender"))
    with pytest.raises(HostError):
        registry.register(get_host("blender"))


def test_unknown_host_raises() -> None:
    with pytest.raises(HostError):
        get_host("maya")


def test_implementation_for_known_and_unknown_ops() -> None:
    houdini = get_host("houdini")
    exact = houdini.implementation_for("geometry.transform")
    assert exact.available
    missing = houdini.implementation_for("shader.principled_surface")
    assert not missing.available
    fragment = houdini.backend.lower_node(IRNode(id="n", operation="geometry.transform"))
    assert fragment.nodes[0].type == "xform"
