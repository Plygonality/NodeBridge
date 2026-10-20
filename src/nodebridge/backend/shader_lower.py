"""Shared shader lowering: unsupported ops keep their main colour or float input.

Side inputs (a factor, a mask) are dropped and dead-code elimination runs
again, so a node that only fed that side input is not reported as translated.
"""

from __future__ import annotations

from ..compiler.rewrite import eliminate_dead_operations
from ..ir.semantic import SemanticGraph
from ..translation.confidence import Confidence

# Prefer a colour or value over a factor. Socket identifiers from the
# lifter (``color``, ``Color``, ``a``) and from an unlifted node (``Color``).
_MAIN_KEYS = ("color", "Color", "image", "Image", "vector", "Vector", "value", "Value", "a", "A")
_SKIP = {"fac", "factor", "alpha"}


def main_shader_input(op) -> str | None:
    """Input that should pass through when ``op`` cannot be translated."""
    for key in _MAIN_KEYS:
        if key in op.inputs and key.lower() not in _SKIP:
            return key
    for key in op.inputs:
        if key.lower() not in _SKIP:
            return key
    return next(iter(op.inputs), None)


def relax_unsupported_shaders(backend, graph: SemanticGraph, context: str, diagnostics) -> None:
    """Drop non-main inputs of unsupported shader ops, then delete what that orphans."""
    for op in list(graph.ops.values()):
        if op.kind in ("MATERIAL_OUTPUT", "COMPOSITE_OUTPUT", "GEOMETRY_OUTPUT"):
            continue
        item = backend.translator(op, context)
        if item is None:
            unsupported = True
        else:
            unsupported = item.classify(op, graph).confidence == Confidence.UNSUPPORTED
        if not unsupported:
            continue
        key = main_shader_input(op)
        if key is None or key not in op.inputs:
            op.inputs = {}
        else:
            op.inputs = {key: op.inputs[key]}
    eliminate_dead_operations(graph, diagnostics)
