"""Compositor extraction through the graph-IR parser."""

from __future__ import annotations

from nodebridge.compiler.semanticize import semanticize
from nodebridge.frontend.blender.parser import parse_node_tree
from nodebridge.ir.schema import IRDocument


def extract_compositor(node_tree: object) -> IRDocument:
    """Extract a compositor node tree into semantic IR."""
    return semanticize(parse_node_tree(node_tree, system="compositor"))
