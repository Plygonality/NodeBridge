"""Compiler pipeline: extract → validate → normalize → plan → lower → report.

This is the only module that sequences compiler stages. Hosts do not call
each other. Pairwise converters are not used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nodebridge.compiler.lowering import generate_script, lower_graph
from nodebridge.compiler.normalization import normalize_graph
from nodebridge.compiler.planning import TranslationPlan, plan_translation
from nodebridge.core.diagnostics import TranslationReport
from nodebridge.core.exceptions import ValidationError
from nodebridge.core.graph import IRGraph
from nodebridge.hosts.contract import HostPlugin
from nodebridge.hosts.native import NativeGraph
from nodebridge.hosts.registry import get_host
from nodebridge.ir.schema import IRDocument
from nodebridge.ir.validation import ValidationResult, validate_graph


@dataclass
class CompilationResult:
    """Outputs of one compilation from IR (or a frontend) to a target host."""

    source_graph: IRGraph
    normalized_graph: IRGraph
    plan: TranslationPlan
    native_graph: NativeGraph
    report: TranslationReport
    generated_code: str = ""
    validation: ValidationResult | None = None
    source_host: str = ""
    target_host: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_host": self.source_host,
            "target_host": self.target_host,
            "plan": self.plan.as_dict(),
            "report": self.report.as_dict(),
            "native_graph": self.native_graph.as_dict(),
            "generated_code": self.generated_code,
        }


def compile_graph(
    graph: IRGraph | IRDocument,
    target: str | HostPlugin,
    *,
    source: str | HostPlugin | None = None,
    generate: bool = False,
    raise_on_invalid: bool = False,
) -> CompilationResult:
    """Compile canonical IR toward *target*.

    Stages::

        validate → normalize → plan → lower → (optional script) → report
    """
    ir_graph = graph.graph if isinstance(graph, IRDocument) else graph
    target_host = target if not isinstance(target, str) else get_host(target)
    source_id = (
        source.id
        if source is not None and not isinstance(source, str)
        else (source or ir_graph.provenance.application or "unknown")
    )
    validation = validate_graph(ir_graph)
    if raise_on_invalid and not validation.ok:
        validation.raise_if_invalid()
    normalized = normalize_graph(ir_graph)
    plan = plan_translation(normalized, target_host)
    native, report = lower_graph(normalized, target_host)
    script = generate_script(normalized, target_host) if generate else ""
    if script and not report.generated_code:
        from nodebridge.core.diagnostics import GeneratedCode

        report.add_generated_code(
            GeneratedCode(kind="script", language=target_host.id, source=script)
        )
    return CompilationResult(
        source_graph=ir_graph,
        normalized_graph=normalized,
        plan=plan,
        native_graph=native,
        report=report,
        generated_code=script,
        validation=validation,
        source_host=str(source_id),
        target_host=target_host.id,
    )


def compile_native(
    native: NativeGraph | dict[str, Any],
    target: str | HostPlugin,
    *,
    source: str | HostPlugin | None = None,
    generate: bool = False,
) -> CompilationResult:
    """Frontend-extract *native* then compile toward *target*."""
    source_host = _resolve_source(native, source)
    document = source_host.frontend.extract(native)
    return compile_graph(
        document,
        target,
        source=source_host,
        generate=generate,
    )


def _resolve_source(
    native: NativeGraph | dict[str, Any],
    source: str | HostPlugin | None,
) -> HostPlugin:
    if source is not None:
        return source if not isinstance(source, str) else get_host(source)
    host_id = native.host if isinstance(native, NativeGraph) else str(native.get("host") or "")
    if not host_id:
        raise ValidationError("Native graph is missing a host id; pass source= explicitly")
    return get_host(host_id)
