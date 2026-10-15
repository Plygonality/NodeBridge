"""Named views over semantic operations.

The stored record is always :class:`nodebridge.ir.semantic.Operation`. These
views are the readable surface used by translators and tests:

    scatter = ScatterOperation(operation)
    scatter.density
    scatter.seed
    scatter.distribution_mode
"""

from __future__ import annotations

from dataclasses import dataclass

from nodebridge.ir.semantic import Operation, OperationKind, Port, SourceRef
from nodebridge.ir.types import DataType


def _port(name: str, data_type: DataType, role: str, *, field: bool = False) -> Port:
    return Port(name=name, data_type=data_type, role=role, field=field)


def geometry_port(name: str, data_type: DataType = DataType.GEOMETRY) -> Port:
    return _port(name, data_type, "geometry")


def field_port(name: str, data_type: DataType) -> Port:
    return _port(name, data_type, "field", field=True)


def value_port(name: str, data_type: DataType) -> Port:
    return _port(name, data_type, "value")


@dataclass(frozen=True)
class ParameterSpec:
    """Documents one semantic parameter. Translators read the same names."""

    name: str
    data_type: DataType
    default: object = None
    description: str = ""


OPERATION_PARAMETERS: dict[OperationKind, tuple[ParameterSpec, ...]] = {
    OperationKind.PRIMITIVE: (
        ParameterSpec("primitive", DataType.STRING, "cube"),
        ParameterSpec("size", DataType.VECTOR3, (1.0, 1.0, 1.0)),
        ParameterSpec("radius", DataType.FLOAT, 1.0),
        ParameterSpec("vertices", DataType.VECTOR3, (2, 2, 2)),
        ParameterSpec("depth", DataType.FLOAT, 1.0),
    ),
    OperationKind.SCATTER: (
        ParameterSpec("distribution_mode", DataType.STRING, "density", "density or distance"),
        ParameterSpec("density", DataType.FLOAT, 10.0),
        ParameterSpec("density_attribute", DataType.STRING, ""),
        ParameterSpec("seed", DataType.INT, 0),
        ParameterSpec("distance_min", DataType.FLOAT, 0.0),
        ParameterSpec("normal_alignment", DataType.BOOL, True),
        ParameterSpec("selection", DataType.STRING, ""),
    ),
    OperationKind.INSTANCE: (
        ParameterSpec("pick_instance", DataType.BOOL, False),
        ParameterSpec("scale", DataType.VECTOR3, (1.0, 1.0, 1.0)),
        ParameterSpec("rotation", DataType.VECTOR3, (0.0, 0.0, 0.0)),
        ParameterSpec("seed", DataType.INT, 0),
    ),
    OperationKind.TRANSFORM: (
        ParameterSpec("translation", DataType.VECTOR3, (0.0, 0.0, 0.0)),
        ParameterSpec("rotation", DataType.VECTOR3, (0.0, 0.0, 0.0)),
        ParameterSpec("scale", DataType.VECTOR3, (1.0, 1.0, 1.0)),
    ),
    OperationKind.RANDOM: (
        ParameterSpec("data_type", DataType.STRING, "float"),
        ParameterSpec("minimum", DataType.FLOAT, 0.0),
        ParameterSpec("maximum", DataType.FLOAT, 1.0),
        ParameterSpec("seed", DataType.INT, 0),
    ),
    OperationKind.NOISE: (
        ParameterSpec("noise_type", DataType.STRING, "noise"),
        ParameterSpec("scale", DataType.FLOAT, 5.0),
        ParameterSpec("detail", DataType.FLOAT, 2.0),
        ParameterSpec("roughness", DataType.FLOAT, 0.5),
        ParameterSpec("distortion", DataType.FLOAT, 0.0),
        ParameterSpec("dimensions", DataType.STRING, "3D"),
    ),
    OperationKind.MATH: (ParameterSpec("operation", DataType.STRING, "add"),),
    OperationKind.VECTOR_MATH: (ParameterSpec("operation", DataType.STRING, "add"),),
    OperationKind.MAP_RANGE: (
        ParameterSpec("clamp", DataType.BOOL, True),
        ParameterSpec("from_min", DataType.FLOAT, 0.0),
        ParameterSpec("from_max", DataType.FLOAT, 1.0),
        ParameterSpec("to_min", DataType.FLOAT, 0.0),
        ParameterSpec("to_max", DataType.FLOAT, 1.0),
    ),
}


def make_operation(
    *,
    id: str,
    kind: OperationKind,
    name: str,
    parameters: dict | None = None,
    inputs: dict[str, Port] | None = None,
    outputs: dict[str, Port] | None = None,
    source: SourceRef | None = None,
    notes: list[str] | None = None,
) -> Operation:
    stored = dict(parameters or {})
    for spec in OPERATION_PARAMETERS.get(kind, ()):
        stored.setdefault(spec.name, spec.default)
    return Operation(
        id=id,
        kind=kind,
        name=name,
        parameters=stored,
        inputs=dict(inputs or {}),
        outputs=dict(outputs or {}),
        source=source or SourceRef(),
        notes=list(notes or []),
    )


class _View:
    def __init__(self, operation: Operation, kind: OperationKind) -> None:
        if operation.kind is not kind:
            raise TypeError(f"Expected {kind.value}, got {operation.kind.value}")
        self.operation = operation

    def __getattr__(self, name: str) -> object:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self.operation.parameters[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class ScatterOperation(_View):
    """Surface scatter. ``geometry_input`` is the geometry port name."""

    geometry_input = "geometry"

    def __init__(self, operation: Operation) -> None:
        super().__init__(operation, OperationKind.SCATTER)


class InstanceOperation(_View):
    def __init__(self, operation: Operation) -> None:
        super().__init__(operation, OperationKind.INSTANCE)


class TransformOperation(_View):
    def __init__(self, operation: Operation) -> None:
        super().__init__(operation, OperationKind.TRANSFORM)


class NoiseOperation(_View):
    def __init__(self, operation: Operation) -> None:
        super().__init__(operation, OperationKind.NOISE)


class RandomOperation(_View):
    def __init__(self, operation: Operation) -> None:
        super().__init__(operation, OperationKind.RANDOM)


class PrimitiveOperation(_View):
    def __init__(self, operation: Operation) -> None:
        super().__init__(operation, OperationKind.PRIMITIVE)


class MathOperation(_View):
    def __init__(self, operation: Operation) -> None:
        super().__init__(operation, OperationKind.MATH)
