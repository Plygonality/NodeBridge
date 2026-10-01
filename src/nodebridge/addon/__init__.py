"""Blender add-on UI. Contains no translation logic; it calls the compiler."""

from . import operators, panels, properties

MODULES = (properties, operators, panels)


def register() -> None:
    for module in MODULES:
        module.register()


def unregister() -> None:
    for module in reversed(MODULES):
        module.unregister()
