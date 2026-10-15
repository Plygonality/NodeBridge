"""JSON serialization of Graph IR and Semantic IR documents.

Loading a document never executes code. Generated scripts are separate
artifacts produced explicitly by a backend.
"""

from __future__ import annotations

import json
from typing import Any

from .. import __version__
from ..common.units import ValueRole
from .graph import GraphDocument, NodeTree, TreeKind
from .semantic import Const, ExposedParameter, GraphOutput, InputValue, Link, Param, SemanticGraph, SemanticOp, SourceRef
from .types import DataType, TypeRef

FORMAT_VERSION = 1


def graph_document_to_dict(document: GraphDocument) -> dict:
    return {
        "format": "nodebridge.graph",
        "format_version": FORMAT_VERSION,
        "nodebridge_version": __version__,
        "root": document.root,
        "source": document.source,
        "trees": [tree.as_dict() for tree in document.trees.values()],
    }


def graph_document_from_dict(data: dict) -> GraphDocument:
    if data.get("format") != "nodebridge.graph":
        raise ValueError("not a NodeBridge Graph IR document")
    trees = {tree["name"]: NodeTree.from_dict(tree) for tree in data.get("trees", [])}
    return GraphDocument(root=data["root"], trees=trees, source=dict(data.get("source", {})))


def dumps_graph(document: GraphDocument) -> str:
    return json.dumps(graph_document_to_dict(document), indent=2, sort_keys=False, default=_default) + "\n"


def loads_graph(text: str) -> GraphDocument:
    return graph_document_from_dict(json.loads(text))


# --- semantic ------------------------------------------------------------
def _value_to_json(value: InputValue) -> Any:
    if isinstance(value, Const):
        return {"const": value.value, "type": value.type.value}
    if isinstance(value, Param):
        return {"param": value.name}
    if isinstance(value, Link):
        return {"link": [value.op, value.output]}
    if isinstance(value, tuple):
        return {"multi": [_value_to_json(item) for item in value]}
    raise TypeError(f"unknown input value {value!r}")


def _value_from_json(data: Any) -> InputValue:
    if "const" in data:
        return Const(data["const"], DataType(data.get("type", "any")))
    if "param" in data:
        return Param(data["param"])
    if "link" in data:
        return Link(data["link"][0], data["link"][1])
    if "multi" in data:
        return tuple(_value_from_json(item) for item in data["multi"])
    raise ValueError(f"unknown input value {data!r}")


def semantic_to_dict(graph: SemanticGraph) -> dict:
    return {
        "format": "nodebridge.semantic",
        "format_version": FORMAT_VERSION,
        "name": graph.name,
        "kind": graph.kind.value,
        "is_subgraph": graph.is_subgraph,
        "source": graph.source,
        "parameters": [
            {
                "key": p.key,
                "name": p.name,
                "type": p.data_type.value,
                "role": p.role.value,
                "default": p.default,
                "value": p.value,
                "min": p.min_value,
                "max": p.max_value,
                "description": p.description,
                "identifier": p.identifier,
            }
            for p in graph.parameters
        ],
        "operations": [
            {
                "id": op.id,
                "kind": op.kind,
                "name": op.name,
                "inputs": {key: _value_to_json(value) for key, value in op.inputs.items()},
                "params": op.params,
                "outputs": {key: ref.as_dict() for key, ref in op.outputs.items()},
                "source": op.source.as_dict(),
                **({"annotations": op.annotations} if op.annotations else {}),
            }
            for op in graph.ops.values()
        ],
        "outputs": [{"name": o.name, "label": o.label, "value": _value_to_json(o.value), "type": o.data_type.value} for o in graph.outputs],
        "subgraphs": [semantic_to_dict(sub) for sub in graph.subgraphs.values()],
    }


def semantic_from_dict(data: dict) -> SemanticGraph:
    graph = SemanticGraph(name=data["name"], kind=TreeKind(data["kind"]), source=dict(data.get("source", {})), is_subgraph=data.get("is_subgraph", False))
    for p in data.get("parameters", []):
        graph.parameters.append(
            ExposedParameter(
                key=p["key"],
                name=p["name"],
                data_type=DataType(p["type"]),
                role=ValueRole(p.get("role", "scalar")),
                default=p.get("default"),
                value=p.get("value"),
                min_value=p.get("min"),
                max_value=p.get("max"),
                description=p.get("description", ""),
                identifier=p.get("identifier", ""),
            )
        )
    for item in data.get("operations", []):
        source = item.get("source", {})
        graph.add(
            SemanticOp(
                id=item["id"],
                kind=item["kind"],
                name=item.get("name", ""),
                inputs={key: _value_from_json(value) for key, value in item.get("inputs", {}).items()},
                params=dict(item.get("params", {})),
                outputs={key: TypeRef.from_dict(ref) for key, ref in item.get("outputs", {}).items()},
                source=SourceRef(source.get("tree", ""), source.get("nodes", []), source.get("types", []), source.get("names", [])),
                annotations=dict(item.get("annotations", {})),
            )
        )
    graph.outputs = [GraphOutput(o["name"], _value_from_json(o["value"]), DataType(o.get("type", "geometry")), o.get("label", "")) for o in data.get("outputs", [])]
    for sub in data.get("subgraphs", []):
        child = semantic_from_dict(sub)
        graph.subgraphs[child.name] = child
    return graph


def dumps_semantic(graph: SemanticGraph) -> str:
    return json.dumps(semantic_to_dict(graph), indent=2, default=_default) + "\n"


def loads_semantic(text: str) -> SemanticGraph:
    return semantic_from_dict(json.loads(text))


def _default(value: Any) -> Any:
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, tuple):
        return list(value)
    return str(value)
