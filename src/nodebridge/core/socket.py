"""IR sockets: typed ports on a node."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from nodebridge.core.ids import require_id
from nodebridge.core.metadata import Metadata
from nodebridge.core.types import DataType, TypeRef
from nodebridge.core.values import JSONValue, normalize_value


class SocketDirection(str, Enum):
    """Whether a socket receives data or produces it."""

    INPUT = "input"
    OUTPUT = "output"


class FieldKind(str, Enum):
    """Whether a socket carries a constant or a field (per-element) value."""

    VALUE = "value"
    FIELD = "field"
    UNKNOWN = "unknown"


class GeometryDomain(str, Enum):
    """Domain a field is evaluated on. Independent of any one DCC."""

    POINT = "point"
    EDGE = "edge"
    FACE = "face"
    CORNER = "corner"
    CURVE = "curve"
    INSTANCE = "instance"
    SPLINE = "spline"
    UNKNOWN = "unknown"


@dataclass
class IRSocket:
    """A typed input or output port.

    ``id`` is the stable identifier used by connections. ``name`` is a
    human-readable semantic name (for example ``geometry``), not a UI label.
    """

    id: str
    name: str
    data_type: TypeRef
    direction: SocketDirection
    default: JSONValue = None
    field_kind: FieldKind = FieldKind.VALUE
    domain: GeometryDomain | None = None
    metadata: Metadata = field(default_factory=Metadata)

    def __post_init__(self) -> None:
        require_id(self.id, what="socket id")
        if not self.name:
            raise ValueError(f"Socket {self.id!r} is missing a name")
        if not isinstance(self.data_type, TypeRef):
            self.data_type = TypeRef.of(self.data_type)
        if not isinstance(self.direction, SocketDirection):
            self.direction = SocketDirection(self.direction)
        if not isinstance(self.field_kind, FieldKind):
            self.field_kind = FieldKind(self.field_kind)
        if self.domain is not None and not isinstance(self.domain, GeometryDomain):
            self.domain = GeometryDomain(self.domain)
        self.default = normalize_value(self.default)

    @classmethod
    def input(
        cls,
        id: str,
        name: str,
        data_type: str | DataType | TypeRef,
        *,
        default: JSONValue = None,
        field_kind: FieldKind = FieldKind.VALUE,
        domain: GeometryDomain | None = None,
        metadata: Metadata | None = None,
    ) -> IRSocket:
        """Convenience constructor for an input socket."""
        return cls(
            id=id,
            name=name,
            data_type=TypeRef.of(data_type),
            direction=SocketDirection.INPUT,
            default=default,
            field_kind=field_kind,
            domain=domain,
            metadata=metadata or Metadata(),
        )

    @classmethod
    def output(
        cls,
        id: str,
        name: str,
        data_type: str | DataType | TypeRef,
        *,
        field_kind: FieldKind = FieldKind.VALUE,
        domain: GeometryDomain | None = None,
        metadata: Metadata | None = None,
    ) -> IRSocket:
        """Convenience constructor for an output socket."""
        return cls(
            id=id,
            name=name,
            data_type=TypeRef.of(data_type),
            direction=SocketDirection.OUTPUT,
            field_kind=field_kind,
            domain=domain,
            metadata=metadata or Metadata(),
        )
