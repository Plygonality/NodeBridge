"""Application-agnostic exceptions for NodeBridge."""

from __future__ import annotations


class NodeBridgeError(Exception):
    """Base exception for all NodeBridge errors."""


class ValidationError(NodeBridgeError):
    """Raised when an IR graph fails structural validation."""


class SerializationError(NodeBridgeError):
    """Raised when an IR document cannot be encoded or decoded."""


class VersionError(SerializationError):
    """Raised when an IR document version is unsupported or invalid."""


class UnknownOperationError(NodeBridgeError):
    """Raised when an operation identifier is required but not registered."""


class AdapterError(NodeBridgeError):
    """Raised by a source adapter. Adapters are not implemented in Milestone 1."""


class BackendError(NodeBridgeError):
    """Raised by a target backend. Backends are not implemented in Milestone 1."""


class TranslationError(NodeBridgeError):
    """Raised when semantic translation cannot produce a usable result."""
