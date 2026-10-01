"""Lift Blender Graph IR into Semantic IR.

Each Blender node type registers a *lifter* with :func:`lifts`. A lifter
reads the node's sockets through :class:`LiftContext` and emits one or
more semantic operations. Group nodes become ``SUBGRAPH`` operations whose
nested trees are lifted recursively. Nodes without a lifter become
``UNSUPPORTED_OPERATION`` so they are reported, never dropped.

Node *types* appear only in this frontend; the compiler and backends see
semantic kinds.
"""

from __future__ import annotations

from typing import Any, Callable

from ...common.names import NameAllocator, python_identifier
from ...common.units import ValueRole
from ...compiler.analyzer import analyze_tree
from ...compiler.diagnostics import DiagnosticBag
from ...compiler.normalize import normalize_tree
from ...ir.graph import GraphDocument, GraphEdge, GraphNode, InterfaceSocket, NodeTree, TreeKind
from ...ir.operations import Category, get_operation
from ...ir.semantic import Const, ExposedParameter, GraphOutput, InputValue, Link, Param, SemanticGraph, SemanticOp, SourceRef, iter_links
from ...ir.types import GEOMETRY_TYPES, DataType, TypeRef

LifterFn = Callable[["LiftContext", GraphNode], None]
_LIFTERS: dict[tuple[TreeKind | None, str], LifterFn] = {}


def lifts(*node_types: str, kinds: tuple[TreeKind, ...] | None = None) -> Callable[[LifterFn], LifterFn]:
    """Register a lifter for one or more Blender node ``bl_idname`` values."""

    def decorator(fn: LifterFn) -> LifterFn:
        for node_type in node_types:
            for kind in kinds or (None,):
                _LIFTERS[(kind, node_type)] = fn
        return fn

    return decorator


def lifter_for(kind: TreeKind, node_type: str) -> LifterFn | None:
    return _LIFTERS.get((kind, node_type)) or _LIFTERS.get((None, node_type))


def supported_node_types(kind: TreeKind) -> list[str]:
    return sorted({t for (k, t) in _LIFTERS if k in (kind, None)} | {"NodeGroupInput", "NodeGroupOutput", "NodeReroute"})


class LiftError(Exception):
    """Raised by a lifter when a node configuration cannot be lifted."""


SUBTYPE_ROLES = {
    "DISTANCE": ValueRole.LENGTH,
    "ANGLE": ValueRole.ANGLE,
    "FACTOR": ValueRole.FACTOR,
    "PERCENTAGE": ValueRole.FACTOR,
    "TRANSLATION": ValueRole.POSITION,
    "EULER": ValueRole.EULER,
    "DIRECTION": ValueRole.DIRECTION,
    "XYZ": ValueRole.DIRECTION,
    "TIME": ValueRole.TIME,
    "TIME_ABSOLUTE": ValueRole.TIME,
}
TYPE_ROLES = {
    DataType.INT: ValueRole.INTEGER,
    DataType.BOOL: ValueRole.BOOLEAN,
    DataType.COLOR: ValueRole.COLOR,
    DataType.ROTATION: ValueRole.EULER,
    DataType.STRING: ValueRole.STRING,
    DataType.MATERIAL: ValueRole.REFERENCE,
    DataType.OBJECT: ValueRole.REFERENCE,
    DataType.COLLECTION: ValueRole.REFERENCE,
    DataType.IMAGE: ValueRole.REFERENCE,
}
NON_PARAMETER_TYPES = GEOMETRY_TYPES | {DataType.SHADER}
INTRINSIC_FIELD_KINDS = {"FIELD_INPUT", "ATTRIBUTE_READ", "TEXTURE_COORDINATE"}


def role_for(data_type: DataType, subtype: str) -> ValueRole:
    return SUBTYPE_ROLES.get(subtype.upper(), TYPE_ROLES.get(data_type, ValueRole.SCALAR))


class LiftContext:
    def __init__(self, lifter: "BlenderLifter", tree: NodeTree, graph: SemanticGraph) -> None:
        self.lifter = lifter
        self.tree = tree
        self.graph = graph
        self.kind = tree.kind
        self.diagnostics = lifter.diagnostics
        self.outputs: dict[tuple[str, str], InputValue] = {}
        self._incoming: dict[tuple[str, str], list[GraphEdge]] = {}
        for edge in tree.edges:
            self._incoming.setdefault((edge.to_node, edge.to_socket), []).append(edge)
        self._implicit: dict[str, Link] = {}
        self._geometry_inputs: dict[str, str] = {}
        self._param_keys: dict[str, str] = {p.identifier: p.key for p in graph.parameters}

    # -- reading inputs ------------------------------------------------
    def edges_into(self, node: GraphNode, identifier: str) -> list[GraphEdge]:
        return self._incoming.get((node.id, identifier), [])

    def _resolve(self, edge: GraphEdge) -> InputValue | None:
        return self.outputs.get((edge.from_node, edge.from_socket))

    def has_link(self, node: GraphNode, name: str) -> bool:
        socket = node.find_input(name)
        return bool(socket and self.edges_into(node, socket.identifier))

    def input(self, node: GraphNode, name: str, *, implicit: str | None = None, default: Any = None) -> InputValue | None:
        """Value feeding input ``name``: a link, an implicit field, or the socket default."""
        socket = node.find_input(name)
        if socket is None:
            return Const(default) if default is not None else None
        edges = self.edges_into(node, socket.identifier)
        if edges:
            return self._resolve(edges[0])
        if implicit:
            return self.implicit(implicit)
        if socket.data_type in GEOMETRY_TYPES or socket.data_type == DataType.SHADER:
            return None
        value = socket.default if socket.default is not None else default
        return Const(value, socket.data_type)

    def multi_input(self, node: GraphNode, name: str) -> tuple:
        socket = node.find_input(name)
        if socket is None:
            return ()
        # Blender's multi-input sockets list links bottom-to-top; Graph IR keeps link order.
        values = [self._resolve(edge) for edge in self.edges_into(node, socket.identifier)]
        return tuple(v for v in values if v is not None)

    def prop(self, node: GraphNode, key: str, default: Any = None) -> Any:
        return node.parameters.get(key, default)

    def socket_or_prop(self, node: GraphNode, socket_name: str, prop: str, default: Any = None) -> InputValue:
        """Blender 4.5 moved several compositor properties to sockets."""
        socket = node.find_input(socket_name)
        if socket is not None and socket.enabled:
            value = self.input(node, socket_name, default=default)
            if value is not None:
                return value
        return Const(node.parameters.get(prop, default))

    def implicit(self, field: str) -> Link:
        """Shared implicit field input (position, normal, index, id, uv, generated...)."""
        if field not in self._implicit:
            data_type = DataType.INT if field in ("index", "id") else DataType.VECTOR3
            op = SemanticOp(
                id=self.graph.new_id(f"implicit_{field}"),
                kind="FIELD_INPUT",
                params={"field": field},
                outputs={"value": TypeRef(data_type, True)},
                name=f"{field.title()} (implicit)",
                source=SourceRef(tree=self.tree.name),
            )
            self.graph.add(op)
            self._implicit[field] = Link(op.id, "value")
        return self._implicit[field]

    def is_field(self, value: InputValue | None) -> bool:
        if isinstance(value, tuple):
            return any(self.is_field(v) for v in value)
        if isinstance(value, Link):
            op = self.graph.ops.get(value.op)
            return bool(op and op.outputs.get(value.output) and op.outputs[value.output].field)
        return False

    # -- emitting ------------------------------------------------------
    def source(self, node: GraphNode, *extra: GraphNode) -> SourceRef:
        nodes = (node,) + extra
        return SourceRef(self.tree.name, [n.id for n in nodes], [n.type for n in nodes], [n.display_name for n in nodes])

    def emit(
        self,
        kind: str,
        node: GraphNode,
        inputs: dict[str, InputValue | None] | None = None,
        params: dict[str, Any] | None = None,
        outputs: dict[str, str | None] | None = None,
        *,
        output_types: dict[str, DataType] | None = None,
        name: str | None = None,
    ) -> SemanticOp:
        """Create an operation and bind node output sockets to its outputs.

        ``outputs`` maps operation output names to Blender output socket
        names (``None`` declares an output without binding it).
        """
        spec = get_operation(kind)
        if spec is None:
            raise LiftError(f"unregistered operation {kind}")
        clean = {k: v for k, v in (inputs or {}).items() if v is not None and v != ()}
        op = SemanticOp(
            id=self.graph.new_id(kind),
            kind=kind,
            inputs=clean,
            params=dict(params or {}),
            name=name or node.display_name,
            source=self.source(node),
        )
        any_field = kind in INTRINSIC_FIELD_KINDS or any(self.is_field(v) for v in clean.values())
        for out_name, socket_name in (outputs or {}).items():
            port = spec.output(out_name)
            base = (output_types or {}).get(out_name)
            if base is None and socket_name is not None:
                socket = node.find_output(socket_name)
                base = socket.data_type if socket is not None else None
            if base is None:
                base = port.type if port is not None else DataType.ANY
            if port is not None and spec.category == Category.FIELD:
                is_field = any_field
            elif port is not None:
                is_field = port.field and base not in GEOMETRY_TYPES
            else:
                is_field = any_field and base not in GEOMETRY_TYPES
            op.outputs[out_name] = TypeRef(base, is_field)
        self.graph.add(op)
        for out_name, socket_name in (outputs or {}).items():
            if socket_name is not None:
                self.bind(node, socket_name, Link(op.id, out_name))
        return op

    def bind(self, node: GraphNode, socket_name: str, value: InputValue | None) -> None:
        socket = node.find_output(socket_name)
        if socket is not None and value is not None:
            self.outputs[(node.id, socket.identifier)] = value

    def bind_all(self, node: GraphNode, value: InputValue | None) -> None:
        for socket in node.outputs:
            if value is not None:
                self.outputs[(node.id, socket.identifier)] = value

    def warn(self, code: str, message: str, node: GraphNode) -> None:
        self.diagnostics.warning(code, message, tree=self.tree.name, nodes=[node.id])

    def info(self, code: str, message: str, node: GraphNode) -> None:
        self.diagnostics.info(code, message, tree=self.tree.name, nodes=[node.id])

    # -- structural nodes ---------------------------------------------
    def lift_group_input(self, node: GraphNode) -> None:
        for socket in node.outputs:
            if socket.identifier == "__extend__":
                continue
            interface = next((s for s in self.tree.inputs if s.identifier == socket.identifier), None)
            data_type = interface.data_type if interface else socket.data_type
            if data_type in GEOMETRY_TYPES:
                if socket.identifier not in self._geometry_inputs:
                    op = SemanticOp(
                        id=self.graph.new_id("geometry_input"),
                        kind="GEOMETRY_INPUT",
                        params={"name": socket.name, "identifier": socket.identifier},
                        outputs={"geometry": TypeRef(DataType.GEOMETRY)},
                        name=socket.name,
                        source=self.source(node),
                    )
                    self.graph.add(op)
                    self._geometry_inputs[socket.identifier] = op.id
                self.outputs[(node.id, socket.identifier)] = Link(self._geometry_inputs[socket.identifier], "geometry")
            elif socket.identifier in self._param_keys:
                self.outputs[(node.id, socket.identifier)] = Param(self._param_keys[socket.identifier])

    def lift_group_output(self, node: GraphNode) -> None:
        if node.parameters.get("is_active_output") is False:
            return
        for socket in node.inputs:
            if socket.identifier == "__extend__":
                continue
            interface = next((s for s in self.tree.outputs if s.identifier == socket.identifier), None)
            data_type = interface.data_type if interface else socket.data_type
            edges = self.edges_into(node, socket.identifier)
            if edges:
                value = self._resolve(edges[0])
            elif data_type in GEOMETRY_TYPES or data_type == DataType.SHADER:
                value = None
            else:
                value = Const(socket.default, data_type)
            if value is None:
                continue
            if data_type in GEOMETRY_TYPES and not self.graph.is_subgraph:
                self.emit("GEOMETRY_OUTPUT", node, {"geometry": value}, {"name": socket.name}, name=socket.name)
            self.graph.outputs.append(GraphOutput(socket.identifier, value, data_type, socket.name))

    def lift_group_node(self, node: GraphNode, sub: SemanticGraph) -> None:
        inputs: dict[str, InputValue | None] = {}
        for socket in node.inputs:
            if socket.identifier == "__extend__":
                continue
            edges = self.edges_into(node, socket.identifier)
            if edges:
                inputs[socket.identifier] = self._resolve(edges[0])
            elif socket.data_type not in GEOMETRY_TYPES and socket.data_type != DataType.SHADER:
                inputs[socket.identifier] = Const(socket.default, socket.data_type)
        clean = {k: v for k, v in inputs.items() if v is not None}
        op = SemanticOp(
            id=self.graph.new_id("subgraph"),
            kind="SUBGRAPH",
            inputs=clean,
            params={"graph": sub.name},
            name=node.display_name,
            source=self.source(node),
        )
        input_is_field = any(self.is_field(v) for v in clean.values())
        for out in sub.outputs:
            produced_field = _subgraph_output_is_field(sub, out)
            is_field = out.data_type not in GEOMETRY_TYPES and (produced_field or input_is_field)
            op.outputs[out.name] = TypeRef(out.data_type, is_field)
        self.graph.add(op)
        for socket in node.outputs:
            if socket.identifier in op.outputs:
                self.outputs[(node.id, socket.identifier)] = Link(op.id, socket.identifier)

    def unsupported(self, node: GraphNode, reason: str = "") -> SemanticOp:
        inputs: dict[str, InputValue] = {}
        for socket in node.inputs:
            edges = self.edges_into(node, socket.identifier)
            if edges:
                value = self._resolve(edges[0])
                if value is not None:
                    inputs[socket.identifier] = value
        op = SemanticOp(
            id=self.graph.new_id("unsupported"),
            kind="UNSUPPORTED_OPERATION",
            inputs=inputs,
            params={"source_type": node.type, "reason": reason or f"No NodeBridge semantic lifting exists for {node.type} yet."},
            name=node.display_name,
            source=self.source(node),
        )
        for socket in node.outputs:
            if socket.enabled:
                op.outputs[socket.identifier] = TypeRef(socket.data_type, self.kind != TreeKind.COMPOSITOR and socket.data_type not in GEOMETRY_TYPES and socket.data_type != DataType.SHADER)
        self.graph.add(op)
        for socket in node.outputs:
            if socket.identifier in op.outputs:
                self.outputs[(node.id, socket.identifier)] = Link(op.id, socket.identifier)
        self.warn("lift.unsupported", f"{node.display_name} ({node.type}): {op.params['reason']}", node)
        return op


def _subgraph_output_is_field(sub: SemanticGraph, out: GraphOutput) -> bool:
    for link in iter_links(out.value):
        op = sub.ops.get(link.op)
        if op and op.outputs.get(link.output) and op.outputs[link.output].field:
            return True
    return False


class BlenderLifter:
    """Drives lifting of a whole :class:`GraphDocument` (root + nested groups)."""

    def __init__(self, document: GraphDocument, diagnostics: DiagnosticBag) -> None:
        self.document = document
        self.diagnostics = diagnostics
        self._cache: dict[str, SemanticGraph] = {}
        self._stack: list[str] = []
        self.normalized: dict[str, NodeTree] = {}

    def lift(self) -> SemanticGraph:
        graph = self.lift_tree(self.document.root, is_subgraph=False)
        graph.source = dict(self.document.source)
        return graph

    def lift_tree(self, name: str, *, is_subgraph: bool) -> SemanticGraph:
        cache_key = f"{name}::{'sub' if is_subgraph else 'root'}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        if name in self._stack:
            raise LiftError(f"recursive node group {name!r}")
        self._stack.append(name)
        try:
            tree = normalize_tree(self.document.trees[name], self.diagnostics)
            self.normalized[name] = tree
            graph = SemanticGraph(name=name, kind=tree.kind, is_subgraph=is_subgraph, source=dict(tree.metadata))
            graph.parameters = _parameters_from_interface(tree.inputs)
            ctx = LiftContext(self, tree, graph)
            analysis = analyze_tree(tree)
            for cycle in analysis.cycles:
                self.diagnostics.error("graph.cycle", f"Cycle between nodes {', '.join(cycle)}; these nodes are skipped.", tree=name, nodes=cycle)
            for node_id in analysis.order:
                self._lift_node(ctx, tree.nodes[node_id])
            self._cache[cache_key] = graph
            return graph
        finally:
            self._stack.pop()

    def _lift_node(self, ctx: LiftContext, node: GraphNode) -> None:
        if node.type == "NodeGroupInput":
            ctx.lift_group_input(node)
            return
        if node.type == "NodeGroupOutput":
            ctx.lift_group_output(node)
            return
        if node.group_tree:
            if node.group_tree not in self.document.trees:
                ctx.unsupported(node, f"Node group {node.group_tree!r} was not found.")
                return
            sub = self.lift_tree(node.group_tree, is_subgraph=True)
            ctx.graph.subgraphs[sub.name] = sub
            ctx.lift_group_node(node, sub)
            return
        fn = lifter_for(ctx.kind, node.type)
        if fn is None:
            ctx.unsupported(node)
            return
        try:
            fn(ctx, node)
        except LiftError as exc:
            ctx.unsupported(node, str(exc))


def _parameters_from_interface(inputs: list[InterfaceSocket]) -> list[ExposedParameter]:
    names = NameAllocator()
    result: list[ExposedParameter] = []
    for socket in inputs:
        if socket.data_type in NON_PARAMETER_TYPES:
            continue
        result.append(
            ExposedParameter(
                key=names.allocate(python_identifier(socket.name, "parameter")),
                name=socket.name,
                data_type=socket.data_type,
                role=role_for(socket.data_type, socket.subtype),
                default=socket.default,
                value=socket.value,
                min_value=socket.min_value,
                max_value=socket.max_value,
                description=socket.description,
                identifier=socket.identifier,
            )
        )
    return result
