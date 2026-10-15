"""Shared test helpers: fixture loading and a tiny Graph IR builder."""

from __future__ import annotations

import contextlib
import importlib
import io
import pathlib
import sys

from nodebridge.compiler.pipeline import CompileOptions, compile_document
from nodebridge.ir.graph import GraphDocument, GraphNode, GraphSocket, InterfaceSocket, NodeTree, TreeKind
from nodebridge.ir.serialization import loads_graph
from nodebridge.ir.types import DataType

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def load_example(name: str) -> GraphDocument:
    return loads_graph((EXAMPLES / name / f"{name}.graph.json").read_text(encoding="utf-8"))


def compile_example(name: str, target: str, **options):
    return compile_document(load_example(name), target, CompileOptions(**options))


def run_script(code: str, module: str):
    """Execute generated code against the recording fake module; returns the fake."""
    fake = importlib.import_module(f"fakes.fake_{module}")
    fake.reset()
    previous = sys.modules.get(module)
    sys.modules[module] = fake
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(code, f"<generated {module}>", "exec"), {"__name__": "__main__"})
    finally:
        if previous is None:
            sys.modules.pop(module, None)
        else:
            sys.modules[module] = previous
    return fake


def socket(identifier: str, data_type: DataType, default=None, *, name: str | None = None, output: bool = False, enabled: bool = True) -> GraphSocket:
    return GraphSocket(identifier, name or identifier, data_type, output, default=default, enabled=enabled)


class TreeBuilder:
    """Build small Graph IR trees for unit tests."""

    def __init__(self, name: str = "Test", kind: TreeKind = TreeKind.GEOMETRY, *, is_group: bool = False) -> None:
        self.tree = NodeTree(name=name, kind=kind, is_group=is_group)

    def node(self, node_id: str, node_type: str, inputs=(), outputs=(), **parameters) -> GraphNode:
        node = GraphNode(id=node_id, type=node_type, name=node_id, inputs=list(inputs), outputs=list(outputs), parameters=dict(parameters))
        return self.tree.add(node)

    def link(self, a: str, a_socket: str, b: str, b_socket: str) -> "TreeBuilder":
        self.tree.link(a, a_socket, b, b_socket)
        return self

    def interface(self, identifier: str, name: str, in_out: str, data_type: DataType, default=None, subtype: str = "") -> "TreeBuilder":
        self.tree.interface.append(InterfaceSocket(identifier, name, in_out, data_type, subtype=subtype, default=default))
        return self

    def group_io(self) -> "TreeBuilder":
        inputs = [s for s in self.tree.interface if s.in_out == "INPUT"]
        outputs = [s for s in self.tree.interface if s.in_out == "OUTPUT"]
        self.node("Group Input", "NodeGroupInput", outputs=[socket(s.identifier, s.data_type, name=s.name, output=True) for s in inputs])
        self.node("Group Output", "NodeGroupOutput", inputs=[socket(s.identifier, s.data_type, name=s.name) for s in outputs], is_active_output=True)
        return self

    def document(self, *groups: NodeTree, **source) -> GraphDocument:
        trees = {self.tree.name: self.tree}
        trees.update({g.name: g for g in groups})
        return GraphDocument(root=self.tree.name, trees=trees, source={"display_name": self.tree.name, **source})


G = DataType.GEOMETRY
F = DataType.FLOAT
V = DataType.VECTOR3
I = DataType.INT
B = DataType.BOOL


def geometry_passthrough(name: str = "Test") -> TreeBuilder:
    """Group Input (Geometry) -> Group Output (Geometry)."""
    builder = TreeBuilder(name)
    builder.interface("Socket_0", "Geometry", "INPUT", G).interface("Socket_1", "Geometry", "OUTPUT", G).group_io()
    return builder
