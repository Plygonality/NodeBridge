"""Unreal PCG fragment builders."""

from nodebridge.core.node import IRNode
from nodebridge.hosts.contract import LoweringFragment
from nodebridge.hosts.unreal.backend import UnrealBackend


def build_pcg_fragment(operation: str) -> LoweringFragment:
    """Lower a semantic operation name to a PCG fragment."""
    node = IRNode(id="node_query", operation=operation)
    return UnrealBackend().lower_node(node)
