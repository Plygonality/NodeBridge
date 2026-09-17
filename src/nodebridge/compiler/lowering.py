"""Target-aware lowering of IR into native construction plans."""

from __future__ import annotations

from nodebridge.compiler.planning import TranslationPlan
from nodebridge.core.diagnostics import TranslationReport
from nodebridge.core.graph import IRGraph
from nodebridge.hosts.assemble import assemble_native
from nodebridge.hosts.contract import HostPlugin
from nodebridge.hosts.native import NativeGraph
from nodebridge.hosts.registry import get_host


def lower_graph(
    graph: IRGraph,
    target: str | HostPlugin,
) -> tuple[NativeGraph, TranslationReport]:
    """Lower *graph* to a native construction plan for *target*."""
    host = target if not isinstance(target, str) else get_host(target)
    system = host.graph_systems[0] if host.graph_systems else host.id
    return assemble_native(graph, host.backend, host_id=host.id, system=system)


def generate_script(graph: IRGraph, target: str | HostPlugin) -> str:
    """Emit host-script text. Never executed by IR load."""
    host = target if not isinstance(target, str) else get_host(target)
    return host.backend.generate(graph)
