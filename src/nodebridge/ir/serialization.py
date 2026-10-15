"""JSON serialization for graph IR and semantic IR.

The format is data. Loading it does not execute Python, VEX, or Unreal
scripts. Code generation is a separate, explicit step.
"""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from nodebridge.ir.graph import (
    GraphEdge,
    GraphNode,
    GraphSocket,
    GraphSystem,
    InterfaceSocket,
    NodeParameter,
    NodeTree,
    SocketDirection,
)
from nodebridge.ir.semantic import (
    ExposedParameter,
    Operation,
    OperationKind,
    Port,
    SemanticEdge,
    SemanticGraph,
    SourceRef,
)
from nodebridge.ir.types import DataType

IR_VERSION = "1.0"

_CLASSES = {
    "NodeTree": NodeTree,
    "GraphNode": GraphNode,
    "GraphSocket": GraphSocket,
    "GraphEdge": GraphEdge,
    "NodeParameter": NodeParameter,
    "InterfaceSocket": InterfaceSocket,
    "SemanticGraph": SemanticGraph,
    "Operation": Operation,
    "SemanticEdge": SemanticEdge,
    "Port": Port,
    "SourceRef": SourceRef,
    "ExposedParameter": ExposedParameter,
}

_ENUMS = {
    "GraphSystem": GraphSystem,
    "SocketDirection": SocketDirection,
    "DataType": DataType,
    "OperationKind": OperationKind,
}


def dumps(value: Any, *, indent: int = 2) -> str:
    """Serialize a NodeBridge value to a JSON string."""

    return json.dumps(to_plain(value), indent=indent, sort_keys=True)


def loads(text: str) -> Any:
    """Deserialize JSON produced by :func:`dumps`."""

    return from_plain(json.loads(text))


def dump(value: Any, path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(dumps(value))
        handle.write("\n")


def load(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return loads(handle.read())


def to_plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        payload: dict[str, Any] = {"__type__": type(value).__name__}
        if isinstance(value, (NodeTree, SemanticGraph)):
            payload["ir_version"] = IR_VERSION
        for item in fields(value):
            payload[item.name] = to_plain(getattr(value, item.name))
        return payload
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def from_plain(value: Any) -> Any:
    if isinstance(value, list):
        return [from_plain(item) for item in value]
    if isinstance(value, dict):
        if "__type__" in value:
            return _from_typed(value)
        return {key: from_plain(item) for key, item in value.items()}
    return value


def _from_typed(payload: dict[str, Any]) -> Any:
    name = payload["__type__"]
    cls = _CLASSES.get(name)
    if cls is None:
        raise ValueError(f"Unknown IR type: {name}")
    kwargs = {}
    for item in fields(cls):
        if item.name not in payload:
            continue
        kwargs[item.name] = _coerce_field(item.name, from_plain(payload[item.name]))
    return cls(**kwargs)


def _coerce_field(name: str, value: Any) -> Any:
    if name in {"system"} and isinstance(value, str):
        return GraphSystem(value)
    if name in {"direction"} and isinstance(value, str):
        return SocketDirection(value)
    if name in {"data_type", "base"} and isinstance(value, str):
        return DataType(value)
    if name == "kind" and isinstance(value, str):
        return OperationKind(value)
    if name == "source" and isinstance(value, dict) and "__type__" not in value:
        return SourceRef(
            node_ids=tuple(value.get("node_ids", ())),
            node_types=tuple(value.get("node_types", ())),
            node_names=tuple(value.get("node_names", ())),
        )
    if name == "source" and isinstance(value, SourceRef):
        return SourceRef(
            node_ids=tuple(value.node_ids),
            node_types=tuple(value.node_types),
            node_names=tuple(value.node_names),
        )
    if name == "location" and isinstance(value, list):
        return (float(value[0]), float(value[1])) if value else None
    if name in {"node_ids", "node_types", "node_names"} and isinstance(value, list):
        return tuple(value)
    return value
