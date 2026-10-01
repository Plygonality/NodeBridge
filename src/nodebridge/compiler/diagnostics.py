"""Diagnostics: every dropped, approximated or invalid construct is recorded here."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class Diagnostic:
    severity: Severity
    code: str
    message: str
    tree: str = ""
    nodes: list[str] = field(default_factory=list)
    op: str = ""
    target: str = ""

    def as_dict(self) -> dict:
        data = {"severity": self.severity.value, "code": self.code, "message": self.message}
        for key in ("tree", "nodes", "op", "target"):
            value = getattr(self, key)
            if value:
                data[key] = value
        return data

    def __str__(self) -> str:
        return f"{self.severity.value.upper()}: {self.message}"


class DiagnosticBag(list):
    """A list of diagnostics with convenience constructors."""

    def info(self, code: str, message: str, **kw) -> Diagnostic:
        return self._add(Severity.INFO, code, message, **kw)

    def warning(self, code: str, message: str, **kw) -> Diagnostic:
        return self._add(Severity.WARNING, code, message, **kw)

    def error(self, code: str, message: str, **kw) -> Diagnostic:
        return self._add(Severity.ERROR, code, message, **kw)

    def _add(self, severity: Severity, code: str, message: str, **kw) -> Diagnostic:
        item = Diagnostic(severity, code, message, **kw)
        self.append(item)
        return item

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self if d.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self if d.severity == Severity.WARNING]
