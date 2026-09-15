"""NodeBridge — cross-DCC procedural graph translation.

NodeBridge translates procedural *semantics* between applications. It does
not merely rename nodes. This package is importable without Blender,
Houdini, or Unreal installed.
"""

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
from nodebridge.ir.deserializer import deserialize_document, load, loads
from nodebridge.ir.schema import IRDocument
from nodebridge.ir.serializer import dump, dumps, serialize_graph
from nodebridge.ir.validation import validate_graph
from nodebridge.ir.versioning import IR_VERSION, PACKAGE_VERSION

__version__ = PACKAGE_VERSION

__all__ = [
    "IR_VERSION",
    "PACKAGE_VERSION",
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
    "TranslationReport",
    "TranslationStatus",
    "TypeRef",
    "__version__",
    "deserialize_document",
    "dump",
    "dumps",
    "load",
    "loads",
    "serialize_graph",
    "validate_graph",
]
