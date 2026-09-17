"""Declarative lowering recipes shared by host backends.

A recipe describes how one semantic operation becomes a fragment of
host-native nodes. Recipes are data, not a ``source_node → target_node``
dictionary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from nodebridge.core.diagnostics import TranslationStatus
from nodebridge.core.node import IRNode
from nodebridge.core.values import JSONValue, normalize_value
from nodebridge.hosts.contract import Implementation, LoweringFragment
from nodebridge.hosts.native import NativeLink, NativeNode, NativeSocket


ParameterFn = Callable[[IRNode], dict[str, JSONValue]]


@dataclass(frozen=True)
class NodeTemplate:
    """One native node inside a lowering fragment."""

    local_id: str
    native_type: str
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    parameters: dict[str, JSONValue] = field(default_factory=dict)


@dataclass(frozen=True)
class Recipe:
    """How one semantic operation is realized on one host."""

    operation: str
    fidelity: TranslationStatus
    nodes: tuple[NodeTemplate, ...]
    links: tuple[tuple[str, str, str, str], ...] = ()
    expose_inputs: dict[str, tuple[str, str]] = field(default_factory=dict)
    expose_outputs: dict[str, tuple[str, str]] = field(default_factory=dict)
    note: str = ""
    code_kind: str = ""
    code: str = ""
    parameter_builder: ParameterFn | None = None

    def implementation(self) -> Implementation:
        return Implementation(
            operation=self.operation,
            fidelity=self.fidelity,
            recipe=self.nodes[0].native_type if len(self.nodes) == 1 else "fragment",
            note=self.note,
            code_kind=self.code_kind,
            code=self.code,
            available=True,
        )

    def apply(self, node: IRNode, *, prefix: str | None = None) -> LoweringFragment:
        """Instantiate this recipe for *node*.

        Generated native ids are prefixed with the IR node id so fragments
        from different operations never collide.
        """
        stem = prefix or node.id
        extras = self.parameter_builder(node) if self.parameter_builder else {}
        native_nodes: list[NativeNode] = []
        for template in self.nodes:
            parameters = dict(template.parameters)
            parameters.update(extras.get(template.local_id, {}) if _is_nested(extras) else {})
            if not _is_nested(extras) and len(self.nodes) == 1:
                parameters.update(extras)
            copied_params = {
                key: normalize_value(_resolve_param(value, node))
                for key, value in parameters.items()
            }
            native_nodes.append(
                NativeNode(
                    id=f"{stem}__{template.local_id}",
                    type=template.native_type,
                    name=template.local_id,
                    inputs=[NativeSocket(name=name) for name in template.inputs],
                    outputs=[NativeSocket(name=name) for name in template.outputs],
                    parameters=copied_params,
                    metadata={
                        "ir_node_id": node.id,
                        "operation": node.operation,
                        "fidelity": self.fidelity.value,
                    },
                )
            )
        native_links = [
            NativeLink(
                source_node=f"{stem}__{source_node}",
                source_socket=source_socket,
                target_node=f"{stem}__{target_node}",
                target_socket=target_socket,
            )
            for source_node, source_socket, target_node, target_socket in self.links
        ]
        snippet = ""
        if native_nodes:
            maybe = native_nodes[0].parameters.get("snippet")
            if isinstance(maybe, str) and maybe:
                snippet = maybe
            elif len(native_nodes) > 1:
                maybe = native_nodes[-1].parameters.get("snippet")
                if isinstance(maybe, str) and maybe:
                    snippet = maybe
        return LoweringFragment(
            nodes=native_nodes,
            links=native_links,
            inputs={
                name: (f"{stem}__{local_id}", socket)
                for name, (local_id, socket) in self.expose_inputs.items()
            },
            outputs={
                name: (f"{stem}__{local_id}", socket)
                for name, (local_id, socket) in self.expose_outputs.items()
            },
            fidelity=self.fidelity,
            note=self.note,
            recipe=",".join(template.native_type for template in self.nodes),
            code_kind=self.code_kind,
            code=snippet or (_resolve_code(self.code, node) if self.code else ""),
        )


def _is_nested(extras: dict[str, Any]) -> bool:
    return extras and all(isinstance(value, dict) for value in extras.values())


def _resolve_param(value: JSONValue, node: IRNode) -> JSONValue:
    if isinstance(value, str) and value.startswith("$param."):
        name = value[7:]
        parameter = node.parameters.get(name)
        return parameter.value if parameter is not None else None
    if isinstance(value, str) and value.startswith("$input."):
        name = value[7:]
        try:
            socket = node.socket_by_name(name)
        except KeyError:
            return None
        return socket.default
    return value


def _resolve_code(template: str, node: IRNode) -> str:
    replacements = {"node_id": node.id, "operation": node.operation}
    for name, parameter in node.parameters.items():
        replacements[f"param.{name}"] = str(parameter.value)
    for socket in node.inputs.values():
        replacements[f"input.{socket.name}"] = str(socket.default)
    result = template
    for key, value in replacements.items():
        result = result.replace("{" + key + "}", value)
    return result


def unsupported_fragment(node: IRNode, *, note: str = "") -> LoweringFragment:
    """Placeholder fragment that makes unsupported ops visible."""
    placeholder = NativeNode(
        id=f"{node.id}__unsupported",
        type="nodebridge.unsupported",
        name=node.operation,
        metadata={
            "ir_node_id": node.id,
            "operation": node.operation,
            "fidelity": TranslationStatus.UNSUPPORTED.value,
            "note": note or "No defensible translation exists",
        },
    )
    outputs = {}
    if node.outputs:
        first = next(iter(node.outputs.values()))
        placeholder.outputs = [NativeSocket(name=first.name, data_type=first.data_type.name)]
        outputs[first.name] = (placeholder.id, first.name)
    inputs = {}
    if node.inputs:
        first_in = next(iter(node.inputs.values()))
        placeholder.inputs = [
            NativeSocket(name=item.name, data_type=item.data_type.name)
            for item in node.inputs.values()
        ]
        inputs[first_in.name] = (placeholder.id, first_in.name)
    return LoweringFragment(
        nodes=[placeholder],
        inputs=inputs,
        outputs=outputs,
        fidelity=TranslationStatus.UNSUPPORTED,
        note=note or "No defensible translation exists",
        recipe="nodebridge.unsupported",
    )
