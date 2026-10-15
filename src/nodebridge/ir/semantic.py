"""Semantic IR: what a procedural graph *does*.

A :class:`SemanticGraph` is a DAG of :class:`SemanticOp`. Each operation
has a registered kind (``SCATTER``, ``NOISE``, ``INSTANCE``, ...), typed
inputs and outputs, and settings. Source nodes are metadata only
(:class:`SourceRef`); several source nodes may become one operation and
one source node may become several.

Operation inputs are one of:

* :class:`Const` — a literal value
* :class:`Param` — a reference to an exposed, user-facing parameter
* :class:`Link` — an output of another operation
* a tuple of the above, for multi-input sockets (Join Geometry)
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Union

from ..common.units import ValueRole
from .graph import TreeKind
from .types import DataType, TypeRef


@dataclass(frozen=True)
class Const:
    value: Any
    type: DataType = DataType.ANY


@dataclass(frozen=True)
class Param:
    name: str


@dataclass(frozen=True)
class Link:
    op: str
    output: str


Value = Union[Const, Param, Link]
InputValue = Union[Const, Param, Link, tuple]


def iter_links(value: InputValue | None) -> Iterator[Link]:
    if isinstance(value, Link):
        yield value
    elif isinstance(value, tuple):
        for item in value:
            yield from iter_links(item)


@dataclass
class SourceRef:
    """Where an operation came from in the source DCC."""

    tree: str = ""
    nodes: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    names: list[str] = field(default_factory=list)

    def merged(self, other: "SourceRef") -> "SourceRef":
        return SourceRef(
            self.tree or other.tree,
            _unique(self.nodes + other.nodes),
            _unique(self.types + other.types),
            _unique(self.names + other.names),
        )

    @property
    def label(self) -> str:
        return ", ".join(self.names) or ", ".join(self.nodes) or "(generated)"

    def as_dict(self) -> dict:
        return {"tree": self.tree, "nodes": self.nodes, "types": self.types, "names": self.names}


def _unique(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


@dataclass
class SemanticOp:
    id: str
    kind: str
    inputs: dict[str, InputValue] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, TypeRef] = field(default_factory=dict)
    name: str = ""
    source: SourceRef = field(default_factory=SourceRef)
    annotations: dict[str, Any] = field(default_factory=dict)

    def get(self, name: str, default: Any = None) -> InputValue | Any:
        return self.inputs.get(name, default)

    def const(self, name: str, default: Any = None) -> Any:
        """Literal value of an input, or ``default`` if it is linked / a parameter."""
        value = self.inputs.get(name)
        return value.value if isinstance(value, Const) else default

    def is_const(self, name: str) -> bool:
        return isinstance(self.inputs.get(name), Const) or name not in self.inputs

    def links(self) -> Iterator[tuple[str, Link]]:
        for input_name, value in self.inputs.items():
            for link in iter_links(value):
                yield input_name, link

    @property
    def display_name(self) -> str:
        return self.name or self.source.label or self.kind.lower()


@dataclass
class ExposedParameter:
    """A user-facing control (Geometry Nodes group input, material parameter)."""

    key: str
    name: str
    data_type: DataType
    role: ValueRole = ValueRole.SCALAR
    default: Any = None
    value: Any = None
    min_value: float | None = None
    max_value: float | None = None
    description: str = ""
    identifier: str = ""

    @property
    def current(self) -> Any:
        return self.default if self.value is None else self.value


@dataclass
class GraphOutput:
    name: str  # interface identifier
    value: InputValue
    data_type: DataType = DataType.GEOMETRY
    label: str = ""


@dataclass
class SemanticGraph:
    name: str
    kind: TreeKind
    ops: dict[str, SemanticOp] = field(default_factory=dict)
    outputs: list[GraphOutput] = field(default_factory=list)
    parameters: list[ExposedParameter] = field(default_factory=list)
    subgraphs: dict[str, "SemanticGraph"] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)
    is_subgraph: bool = False
    _counter: Iterator[int] = field(default_factory=lambda: itertools.count(1), repr=False, compare=False)

    # -- construction -------------------------------------------------
    def new_id(self, prefix: str) -> str:
        base = prefix.lower()
        while True:
            candidate = f"{base}_{next(self._counter)}"
            if candidate not in self.ops:
                return candidate

    def add(self, op: SemanticOp) -> SemanticOp:
        if op.id in self.ops:
            raise ValueError(f"duplicate operation id {op.id!r}")
        self.ops[op.id] = op
        return op

    def remove(self, op_id: str) -> None:
        self.ops.pop(op_id, None)

    def parameter(self, key: str) -> ExposedParameter | None:
        return next((p for p in self.parameters if p.key == key), None)

    # -- queries ------------------------------------------------------
    def consumers(self, op_id: str, output: str | None = None) -> list[tuple[SemanticOp, str]]:
        result: list[tuple[SemanticOp, str]] = []
        for op in self.ops.values():
            for input_name, link in op.links():
                if link.op == op_id and (output is None or link.output == output):
                    result.append((op, input_name))
        return result

    def output_uses(self, op_id: str) -> list[GraphOutput]:
        return [out for out in self.outputs if any(link.op == op_id for link in iter_links(out.value))]

    def use_count(self, op_id: str, output: str | None = None) -> int:
        count = len(self.consumers(op_id, output))
        for out in self.outputs:
            count += sum(1 for link in iter_links(out.value) if link.op == op_id and (output is None or link.output == output))
        return count

    def resolve(self, value: InputValue | None) -> SemanticOp | None:
        return self.ops.get(value.op) if isinstance(value, Link) else None

    def replace_uses(self, old: Link, new: InputValue) -> None:
        """Redirect every use of ``old`` to ``new``."""

        def swap(value: InputValue) -> InputValue:
            if value == old:
                return new
            if isinstance(value, tuple):
                return tuple(swap(item) for item in value)
            return value

        for op in self.ops.values():
            for key, value in list(op.inputs.items()):
                op.inputs[key] = swap(value)
        for out in self.outputs:
            out.value = swap(out.value)

    def dependencies(self, op_id: str) -> list[str]:
        return _unique([link.op for _, link in self.ops[op_id].links() if link.op in self.ops])

    def topological_order(self) -> list[SemanticOp]:
        from ..compiler.analyzer import topological_sort

        order, cycles = topological_sort(self.ops.keys(), self.edges())
        if cycles:
            raise ValueError(f"semantic graph {self.name!r} contains a cycle: {sorted(cycles)}")
        return [self.ops[i] for i in order]

    def edges(self) -> list[tuple[str, str]]:
        return [(dep, op.id) for op in self.ops.values() for dep in self.dependencies(op.id)]

    def upstream(self, values: Iterable[InputValue]) -> set[str]:
        """All operation ids that ``values`` depend on (inclusive)."""
        pending = [link.op for value in values for link in iter_links(value)]
        seen: set[str] = set()
        while pending:
            op_id = pending.pop()
            if op_id in seen or op_id not in self.ops:
                continue
            seen.add(op_id)
            pending.extend(self.dependencies(op_id))
        return seen

    def walk(self) -> Iterator[tuple["SemanticGraph", SemanticOp]]:
        """Every operation in this graph and nested subgraphs."""
        for op in self.ops.values():
            yield self, op
        for sub in self.subgraphs.values():
            yield from sub.walk()

    def operation_count(self, *, recursive: bool = True) -> int:
        if not recursive:
            return len(self.ops)
        return sum(1 for _ in self.walk())
