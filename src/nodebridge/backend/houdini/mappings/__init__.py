"""Import translators once so decorators register them."""

from __future__ import annotations

_LOADED = False


def load() -> None:
    global _LOADED
    if _LOADED:
        return
    from nodebridge.backend.houdini.mappings import compositor, fields, geometry, shading

    fields.register()
    compositor.register()
    shading.register()
    _LOADED = True
    # The imports register geometry translators via decorators.
    del geometry, shading, compositor
