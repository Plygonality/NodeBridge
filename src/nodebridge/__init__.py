"""NodeBridge — a cross-DCC compiler for procedural graphs.

NodeBridge translates procedural *semantics* between applications. It does
not merely rename nodes. Importing this package does not require Blender,
Houdini, or Unreal Python.
"""

from nodebridge.compiler.pipeline import CompilationResult, compile_graph, compile_native
from nodebridge.compiler.planning import TranslationPlan, plan_translation
from nodebridge.core.diagnostics import (
    Diagnostic,
    TranslationReport,
    TranslationStatus,
)
from nodebridge.core.graph import GraphBuilder, GraphSystem, IRGraph
from nodebridge.core.link import IRConnection
from nodebridge.core.node import IRNode, IRParameter
from nodebridge.core.socket import IRSocket
from nodebridge.core.types import DataType, TypeRef
from nodebridge.hosts import get_host, list_hosts, register_host
from nodebridge.hosts.native import NativeGraph
from nodebridge.ir.deserializer import deserialize_document, load, loads
from nodebridge.ir.schema import IRDocument
from nodebridge.ir.serializer import dump, dumps, serialize_graph
from nodebridge.ir.validation import validate_graph
from nodebridge.ir.versioning import IR_VERSION, PACKAGE_VERSION

__version__ = PACKAGE_VERSION

__all__ = [
    "IR_VERSION",
    "PACKAGE_VERSION",
    "CompilationResult",
    "DataType",
    "Diagnostic",
    "GraphBuilder",
    "GraphSystem",
    "IRConnection",
    "IRDocument",
    "IRGraph",
    "IRNode",
    "IRParameter",
    "IRSocket",
    "NativeGraph",
    "TranslationPlan",
    "TranslationReport",
    "TranslationStatus",
    "TypeRef",
    "__version__",
    "compile_graph",
    "compile_native",
    "deserialize_document",
    "dump",
    "dumps",
    "get_host",
    "list_hosts",
    "load",
    "loads",
    "plan_translation",
    "register_host",
    "serialize_graph",
    "validate_graph",
]
