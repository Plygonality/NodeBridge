"""Lazy discovery of the OpenUSD ``pxr`` bindings."""

from __future__ import annotations

from ..errors import BundleError


class UsdUnavailable(BundleError):
    """A requested feature needs pxr, and the bindings are not importable."""


def pxr_available() -> bool:
    """Return whether ``pxr.Usd`` imports. Does not cache a negative result."""
    try:
        from pxr import Usd  # noqa: F401
    except ImportError:
        return False
    return True


def pxr_version() -> str | None:
    if not pxr_available():
        return None
    from pxr import Usd

    version = Usd.GetVersion()
    if isinstance(version, tuple):
        return ".".join(str(part) for part in version)
    return str(version)


def require_pxr(feature: str) -> None:
    if pxr_available():
        return
    raise UsdUnavailable(
        f"{feature} needs the optional OpenUSD Python bindings (pxr). "
        'Install them with: python -m pip install "nodebridge[usd]" '
        "(usd-core>=26.11; wheels exist for CPython 3.11-3.14, and 26.11 was imported successfully on CPython 3.12). "
        "A DCC that already ships pxr can put that module on PYTHONPATH instead. "
        "Publishing a basic bundle from Blender and validating manifest.json do not need pxr."
    )
