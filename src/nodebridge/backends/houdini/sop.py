"""Houdini SOP fragment builders."""

from nodebridge.core.node import IRNode
from nodebridge.hosts.houdini.backend import HoudiniBackend
from nodebridge.hosts.contract import LoweringFragment


def build_sop_fragment(operation: str) -> LoweringFragment:
    """Lower a semantic operation name to a SOP fragment."""
    node = IRNode(id="node_query", operation=operation)
    return HoudiniBackend().lower_node(node)
