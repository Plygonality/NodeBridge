"""Semantic IR.

Operations name procedural intent. ``ScatterOperation`` describes scattering
points on a surface. The Blender node that produced it is only a source
reference. Target backends decide whether that becomes a Houdini Scatter SOP
or an Unreal PCG Surface Sampler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from nodebridge.ir.graph import GraphSystem
from nodebridge.ir.types import DataType


class OperationKind(str, Enum):
    PRIMITIVE = "primitive"
    GEOMETRY_INPUT = "geometry_input"
    GEOMETRY_OUTPUT = "geometry_output"
    TRANSFORM = "transform"
    TRANSFORM_POINTS = "transform_points"
    MERGE = "merge"
    SEPARATE = "separate"
    SCATTER = "scatter"
    INSTANCE = "instance"
    REALIZE_INSTANCES = "realize_instances"
    ATTRIBUTE_READ = "attribute_read"
    ATTRIBUTE_WRITE = "attribute_write"
    FIELD = "field"
    SAMPLE = "sample"
    INTERPOLATE = "interpolate"
    NOISE = "noise"
    RANDOM = "random"
    MAP_RANGE = "map_range"
    MATH = "math"
    VECTOR_MATH = "vector_math"
    COMPARE = "compare"
    BOOLEAN_MATH = "boolean_math"
    SELECTION = "selection"
    FILTER = "filter"
    DELETE_GEOMETRY = "delete_geometry"
    EXTRUDE = "extrude"
    SUBDIVIDE = "subdivide"
    CURVE = "curve"
    CURVE_RESAMPLE = "curve_resample"
    CURVE_TO_MESH = "curve_to_mesh"
    MESH_TO_CURVE = "mesh_to_curve"
    RAYCAST = "raycast"
    PROXIMITY = "proximity"
    BOOLEAN = "boolean"
    MATERIAL_ASSIGNMENT = "material_assignment"
    TEXTURE_SAMPLE = "texture_sample"
    COLOR_OPERATION = "color_operation"
    SHADER_OPERATION = "shader_operation"
    COMPOSITOR_OPERATION = "compositor_operation"
    GROUP_INPUT = "group_input"
    GROUP_OUTPUT = "group_output"
    REROUTE = "reroute"
    SUBGRAPH = "subgraph"
    CUSTOM_EXPRESSION = "custom_expression"
    UNSUPPORTED = "unsupported"
    SWITCH = "switch"
    SPATIAL_NOISE_MASK = "spatial_noise_mask"
    RANDOM_TRANSFORM = "random_transform"


@dataclass(frozen=True)
class Port:
    """A semantic input or output."""

    name: str
    data_type: DataType
    role: str = "value"
    field: bool = False
    optional: bool = True


@dataclass(frozen=True)
class SourceRef:
    """Provenance. These strings are not used as the translation key."""

    node_ids: tuple[str, ...] = ()
    node_types: tuple[str, ...] = ()
    node_names: tuple[str, ...] = ()


@dataclass
class ExposedParameter:
    """A control that should remain editable in the target DCC."""

    name: str
    identifier: str
    data_type: DataType
    default: Any = None
    minimum: Any = None
    maximum: Any = None
    description: str = ""


@dataclass
class SemanticEdge:
    id: str
    from_operation: str
    from_port: str
    to_operation: str
    to_port: str


@dataclass
class Operation:
    """One semantic operation.

    Typed views in :mod:`nodebridge.ir.operations` expose named fields such as
    ``density`` and ``seed`` without a separate serialization format per class.
    New operations are new :class:`OperationKind` values plus a view and a
    translator. The graph container does not change.
    """

    id: str
    kind: OperationKind
    name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, Port] = field(default_factory=dict)
    outputs: dict[str, Port] = field(default_factory=dict)
    source: SourceRef = field(default_factory=SourceRef)
    notes: list[str] = field(default_factory=list)
    subgraph: SemanticGraph | None = None

    def param(self, name: str, default: Any = None) -> Any:
        return self.parameters.get(name, default)


@dataclass
class SemanticGraph:
    """What a source tree does, independent of any DCC node catalog."""

    name: str
    system: GraphSystem
    operations: list[Operation] = field(default_factory=list)
    edges: list[SemanticEdge] = field(default_factory=list)
    interface: list[ExposedParameter] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    source_tree_id: str = ""

    def get(self, operation_id: str) -> Operation:
        for operation in self.operations:
            if operation.id == operation_id:
                return operation
        raise KeyError(operation_id)

    def try_get(self, operation_id: str) -> Operation | None:
        for operation in self.operations:
            if operation.id == operation_id:
                return operation
        return None

    def edge_to(self, operation_id: str, port: str) -> SemanticEdge | None:
        for edge in self.edges:
            if edge.to_operation == operation_id and edge.to_port == port:
                return edge
        return None

    def incoming(self, operation_id: str) -> list[SemanticEdge]:
        return [edge for edge in self.edges if edge.to_operation == operation_id]

    def outgoing(self, operation_id: str) -> list[SemanticEdge]:
        return [edge for edge in self.edges if edge.from_operation == operation_id]

    def by_kind(self, kind: OperationKind) -> list[Operation]:
        return [operation for operation in self.operations if operation.kind is kind]
