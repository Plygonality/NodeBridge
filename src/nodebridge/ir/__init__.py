"""Versioned IR documents, serialization, and validation."""

from nodebridge.ir.deserializer import deserialize_document, deserialize_graph, load, loads
from nodebridge.ir.schema import IRDocument
from nodebridge.ir.serializer import dump, dumps, serialize_document, serialize_graph
from nodebridge.ir.validation import ValidationResult, validate_graph
from nodebridge.ir.versioning import (
    IR_VERSION,
    PACKAGE_VERSION,
    SUPPORTED_IR_VERSIONS,
    MigrationRegistry,
)

__all__ = [
    "IR_VERSION",
    "IRDocument",
    "MigrationRegistry",
    "PACKAGE_VERSION",
    "SUPPORTED_IR_VERSIONS",
    "ValidationResult",
    "deserialize_document",
    "deserialize_graph",
    "dump",
    "dumps",
    "load",
    "loads",
    "serialize_document",
    "serialize_graph",
    "validate_graph",
]
