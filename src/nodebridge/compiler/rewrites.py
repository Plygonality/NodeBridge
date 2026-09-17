"""Target-aware rewrite helpers.

Normalization lives in ``normalization.py``. This module re-exports the
pass pipeline so the compiler package matches the documented layout.
"""

from nodebridge.compiler.normalization import (
    CanonicalizeOperationsPass,
    ConstantFoldPass,
    DeadNodeElimPass,
    FuseClampPass,
)
from nodebridge.core.passes import IdentityPass, PassPipeline

__all__ = [
    "CanonicalizeOperationsPass",
    "ConstantFoldPass",
    "DeadNodeElimPass",
    "FuseClampPass",
    "IdentityPass",
    "PassPipeline",
]
