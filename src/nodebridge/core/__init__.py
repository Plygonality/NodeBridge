"""Core IR primitives. No application-specific imports live here."""

from nodebridge.core.capabilities import CapabilitySet, TargetCapability
from nodebridge.core.diagnostics import (
    Diagnostic,
    DiagnosticSeverity,
    OperationOutcome,
    TranslationReport,
    TranslationStatus,
)
from nodebridge.core.exceptions import (
    AdapterError,
    BackendError,
    NodeBridgeError,
    SerializationError,
    TranslationError,
    UnknownOperationError,
    ValidationError,
    VersionError,
)
from nodebridge.core.graph import GraphBuilder, GraphInterface, GraphSystem, IRGraph
from nodebridge.core.ids import IdFactory, is_valid_id, require_id
from nodebridge.core.link import IRConnection
from nodebridge.core.metadata import Metadata, Provenance, SourceMapping, UIHints
from nodebridge.core.node import IRNode, IRParameter
from nodebridge.core.operations import (
    DEFAULT_OPERATION_REGISTRY,
    OperationRef,
    OperationRegistry,
    OperationSpec,
)
from nodebridge.core.passes import IdentityPass, PassPipeline, RewritePass
from nodebridge.core.socket import (
    FieldKind,
    GeometryDomain,
    IRSocket,
    SocketDirection,
)
from nodebridge.core.types import (
    DEFAULT_TYPE_REGISTRY,
    DataType,
    TypeCompatibility,
    TypeRef,
    TypeRegistry,
    compare_types,
)

__all__ = [
    "AdapterError",
    "BackendError",
    "CapabilitySet",
    "DEFAULT_OPERATION_REGISTRY",
    "DEFAULT_TYPE_REGISTRY",
    "DataType",
    "Diagnostic",
    "DiagnosticSeverity",
    "FieldKind",
    "GeometryDomain",
    "GraphBuilder",
    "GraphInterface",
    "GraphSystem",
    "IRConnection",
    "IRGraph",
    "IRNode",
    "IRParameter",
    "IRSocket",
    "IdFactory",
    "IdentityPass",
    "Metadata",
    "NodeBridgeError",
    "OperationOutcome",
    "OperationRef",
    "OperationRegistry",
    "OperationSpec",
    "PassPipeline",
    "Provenance",
    "RewritePass",
    "SerializationError",
    "SocketDirection",
    "SourceMapping",
    "TargetCapability",
    "TranslationError",
    "TranslationReport",
    "TranslationStatus",
    "TypeCompatibility",
    "TypeRef",
    "TypeRegistry",
    "UIHints",
    "UnknownOperationError",
    "ValidationError",
    "VersionError",
    "compare_types",
    "is_valid_id",
    "require_id",
]
