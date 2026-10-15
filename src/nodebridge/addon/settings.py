"""Map add-on properties onto compiler options. No Blender import."""

from __future__ import annotations

from nodebridge.compiler.options import CompileOptions
from nodebridge.translation.confidence import Strictness


def options_from_settings(settings) -> CompileOptions:
    """Read the N-panel properties into :class:`CompileOptions`."""

    return CompileOptions(
        strictness=Strictness(getattr(settings, "strictness", Strictness.ALLOW_APPROXIMATE.value)),
        include_comments=bool(getattr(settings, "include_comments", True)),
        preserve_names=bool(getattr(settings, "preserve_names", True)),
        organized_layout=bool(getattr(settings, "organized_layout", True)),
        embed_metadata=bool(getattr(settings, "embed_metadata", True)),
        deterministic_random=bool(getattr(settings, "deterministic_random", True)),
        debug_output=bool(getattr(settings, "debug_output", False)),
        fuse_patterns=True,
        fallback=None,
    )
