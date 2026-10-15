"""Backend registry. Future targets (Maya, Godot, Nuke, ...) register here."""

from __future__ import annotations

from .base import TargetBackend

_BACKENDS: dict[str, TargetBackend] = {}
_LOADED = False


def register_backend(backend: TargetBackend) -> TargetBackend:
    _BACKENDS[backend.id] = backend
    return backend


def load_builtin_backends() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    from . import houdini, unreal  # noqa: F401  (register backends and translators)


def get_backend(backend_id: str) -> TargetBackend:
    load_builtin_backends()
    if backend_id not in _BACKENDS:
        raise KeyError(f"Unknown target {backend_id!r}. Available: {', '.join(sorted(_BACKENDS))}")
    return _BACKENDS[backend_id]


def list_backends() -> list[TargetBackend]:
    load_builtin_backends()
    return [_BACKENDS[key] for key in sorted(_BACKENDS)]
