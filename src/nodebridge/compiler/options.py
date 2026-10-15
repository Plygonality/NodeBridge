"""Options that travel with one compilation.

Backends read these attributes. They are plain data so a Blender panel, the
CLI, and tests can construct the same object.
"""

from __future__ import annotations

from dataclasses import dataclass

from nodebridge.translation.confidence import Strictness
from nodebridge.translation.fallback import TranslationFallbackProvider


@dataclass
class CompileOptions:
    """How far a backend may depart from the source, and how the script is written."""

    strictness: Strictness = Strictness.ALLOW_APPROXIMATE
    include_comments: bool = True
    preserve_names: bool = True
    organized_layout: bool = True
    embed_metadata: bool = True
    deterministic_random: bool = True
    debug_output: bool = False
    fuse_patterns: bool = True
    fallback: TranslationFallbackProvider | None = None
