"""Errors for bundle publishing and path checks.

These are operational failures. The CLI maps them to exit code 1.
Missing files and malformed arguments stay ``ValueError`` / ``FileNotFoundError``
so the CLI can keep exit code 2 for bad input.
"""

from __future__ import annotations


class BundleError(Exception):
    """A bundle could not be published or is structurally invalid."""


class PathSecurityError(BundleError):
    """A bundle member path escapes the bundle root or is not relative."""
