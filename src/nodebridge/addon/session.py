"""In-memory result of the last Analyze or Generate action."""

from __future__ import annotations

from nodebridge.compiler.pipeline import CompileResult


class Session:
    def __init__(self) -> None:
        self.result: CompileResult | None = None
        self.generated = False
        self.message = ""

    def store(self, result: CompileResult, *, generated: bool) -> None:
        self.result = result
        self.generated = generated
        counts = result.report.counts
        self.message = (
            f"{result.report.node_count} nodes, {result.report.operation_count} operations. "
            f"{counts.get('exact', 0)} exact, {counts.get('equivalent', 0)} equivalent, "
            f"{counts.get('approximate', 0)} approximate, {counts.get('unsupported', 0)} unsupported."
        )

    def clear(self) -> None:
        self.result = None
        self.generated = False
        self.message = ""

    @property
    def code(self) -> str:
        if self.result is None or not self.generated:
            return ""
        return self.result.code

    @property
    def report_text(self) -> str:
        if self.result is None:
            return ""
        return self.result.report.text


SESSION = Session()
