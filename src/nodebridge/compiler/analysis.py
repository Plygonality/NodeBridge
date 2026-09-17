"""Capability analysis helpers."""

from __future__ import annotations

from nodebridge.compiler.planning import TranslationPlan, plan_translation
from nodebridge.core.graph import IRGraph
from nodebridge.core.operations import DEFAULT_OPERATION_REGISTRY
from nodebridge.hosts.contract import HostPlugin
from nodebridge.hosts.registry import get_host


def analyze_target_capabilities(
    graph: IRGraph,
    target: str | HostPlugin,
) -> TranslationPlan:
    """Plan plus capability coverage for *graph* toward *target*."""
    return plan_translation(graph, target, operations=DEFAULT_OPERATION_REGISTRY)


def can_implement(target: str | HostPlugin, operation: str) -> bool:
    """Return True if *target* has a non-unsupported mapping for *operation*."""
    host = target if not isinstance(target, str) else get_host(target)
    implementation = host.implementation_for(operation)
    return implementation.available and implementation.fidelity.value != "unsupported"
