"""Houdini SOP backend (Milestone 3).

This module intentionally does not import ``hou``. Generated scripts will
use the ``hou`` API and be executed inside Houdini.
"""

from __future__ import annotations

from nodebridge.backends.base import UnimplementedBackend
from nodebridge.core.capabilities import CapabilitySet, TargetCapability
from nodebridge.core.exceptions import BackendError
from nodebridge.core.graph import IRGraph


class HoudiniBackend(UnimplementedBackend):
    """Translate IR geometry graphs into Houdini SOP networks."""

    name = "houdini"
    capabilities = CapabilitySet([TargetCapability.SOP, TargetCapability.VEX])

    def generate(self, graph: IRGraph) -> str:
        raise BackendError(
            "Houdini generation is Milestone 3. Milestone 1 only defines the IR."
        )
