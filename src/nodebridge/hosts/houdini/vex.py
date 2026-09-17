"""Deterministic VEX snippet generation.

Snippets are data attached to CUSTOM_CODE classifications. Loading IR never
executes them. They are generated only when a native SOP cannot express the
semantics.
"""

from __future__ import annotations

from nodebridge.core.node import IRNode


def _num(node: IRNode | None, name: str, default: str) -> str:
    if node is None:
        return default
    if name in node.parameters and node.parameters[name].value is not None:
        return _literal(node.parameters[name].value)
    try:
        socket = node.socket_by_name(name)
    except KeyError:
        return default
    if socket.default is None:
        return default
    return _literal(socket.default)


def _literal(value: object) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, list) and len(value) >= 3:
        return f"{{{_literal(value[0])}, {_literal(value[1])}, {_literal(value[2])}}}"
    return "0"


def vex_for_math(operation: str, node: IRNode | None = None) -> str:
    """Return a deterministic Attribute Wrangle snippet for a math op."""
    a = _num(node, "a", "chf('a')")
    b = _num(node, "b", "chf('b')")
    value = _num(node, "value", "chf('value')")
    snippets = {
        "math.add": f"f@value = {a} + {b};",
        "math.subtract": f"f@value = {a} - {b};",
        "math.multiply": f"f@value = {a} * {b};",
        "math.divide": f"f@value = {b} == 0 ? 0 : {a} / {b};",
        "math.power": f"f@value = pow({a}, {_num(node, 'exponent', b)});",
        "math.min": f"f@value = min({a}, {b});",
        "math.max": f"f@value = max({a}, {b});",
        "math.clamp": (
            f"f@value = clamp({value}, {_num(node, 'min', '0')}, {_num(node, 'max', '1')});"
        ),
        "math.map_range": (
            "f@value = fit({value}, {from_min}, {from_max}, {to_min}, {to_max});".format(
                value=value,
                from_min=_num(node, "from_min", "0"),
                from_max=_num(node, "from_max", "1"),
                to_min=_num(node, "to_min", "0"),
                to_max=_num(node, "to_max", "1"),
            )
        ),
    }
    return snippets.get(operation, f"// unsupported math operation {operation}\n") + "\n"


def vex_for_vector(operation: str, node: IRNode | None = None) -> str:
    a = _num(node, "a", "chv('a')")
    b = _num(node, "b", "chv('b')")
    vec = _num(node, "vector", "v@P")
    scale = _num(node, "scale", "chf('scale')")
    snippets = {
        "vector.add": f"v@vector = {a} + {b};",
        "vector.subtract": f"v@vector = {a} - {b};",
        "vector.scale": f"v@vector = {vec} * {scale};",
        "vector.normalize": f"v@vector = normalize({vec});",
        "vector.cross": f"v@vector = cross({a}, {b});",
        "vector.dot": f"f@value = dot({a}, {b});",
        "vector.distance": f"f@value = distance({a}, {b});",
    }
    return snippets.get(operation, f"// unsupported vector operation {operation}\n") + "\n"


def vex_for_modify_position(node: IRNode | None = None) -> str:
    offset = _num(node, "offset", "{0, 0, 0}")
    position = None
    if node is not None:
        try:
            socket = node.socket_by_name("position")
            if socket.default is not None:
                position = _literal(socket.default)
        except KeyError:
            position = None
    if position is not None:
        return f"@P = {position} + {offset};\n"
    return f"@P = @P + {offset};\n"
