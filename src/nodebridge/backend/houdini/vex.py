"""Semantic expressions to VEX.

VEX is used when a native SOP cannot carry a field. Noise uses Houdini's
``noise()`` and is approximate. Math uses the same arithmetic as the
constant folder, so constant and field math agree.
"""

from __future__ import annotations

from nodebridge.common.random import vex_random_library
from nodebridge.compiler.evaluate import Expr, as_constant


def expression_to_vex(expr: Expr, *, deterministic: bool) -> str:
    """Return a VEX expression. The result may be a float or a vector."""

    if expr.op == "const" or as_constant(expr) is not None and expr.op not in {"exposed", "attr", "random", "noise", "voronoi"}:
        constant = expr.args[0] if expr.op == "const" else as_constant(expr)
        return _literal(constant)
    if expr.op == "exposed":
        name = _parm(str(expr.args[0]))
        if expr.dtype in {"vector3", "color"}:
            return f'chv("../{name}")'
        return f'chf("../{name}")'
    if expr.op == "attr":
        return {
            "position": "@P",
            "normal": "@N",
            "index": "@ptnum",
            "id": "idtopoint(0, @id)",
            "uv": "@uv",
        }.get(str(expr.args[0]), f"@{expr.args[0]}")
    if expr.op == "random":
        return _random(expr, deterministic)
    if expr.op in {"noise", "voronoi"}:
        position = expression_to_vex(expr.args[0], deterministic=deterministic) if isinstance(expr.args[0], Expr) else "@P"
        scale = expression_to_vex(expr.args[1], deterministic=deterministic) if len(expr.args) > 1 and isinstance(expr.args[1], Expr) else "1"
        if position in {"0", "0.0", "{0,0,0}"}:
            position = "@P"
        sampler = "wnoise" if expr.op == "voronoi" else "noise"
        return f"{sampler}(({position}) * ({scale}))"
    if expr.op == "spatial_noise_mask":
        scale = expr.args[0] if expr.args else 5.0
        threshold = expr.args[1] if len(expr.args) > 1 else 0.5
        return f"(noise(@P * {float(scale):.6f}) > {float(threshold):.6f})"
    if expr.op == "map_range":
        parts = [_child(arg, deterministic) for arg in expr.args]
        return f"fit({parts[0]}, {parts[1]}, {parts[2]}, {parts[3]}, {parts[4]})"
    if expr.op == "compare":
        comparison = str(expr.args[0])
        left = _child(expr.args[1], deterministic)
        right = _child(expr.args[2], deterministic)
        symbol = {
            "less_than": "<",
            "greater_than": ">",
            "less_equal": "<=",
            "greater_equal": ">=",
            "equal": "==",
            "not_equal": "!=",
        }.get(comparison, ">")
        return f"({left} {symbol} {right})"
    if expr.op == "switch":
        condition = _child(expr.args[0], deterministic)
        false_value = _child(expr.args[1], deterministic)
        true_value = _child(expr.args[2], deterministic)
        return f"({condition} ? {true_value} : {false_value})"
    if expr.op.startswith("bool_"):
        left = _child(expr.args[0], deterministic)
        right = _child(expr.args[1], deterministic) if len(expr.args) > 1 else "0"
        name = expr.op.removeprefix("bool_")
        if name == "not":
            return f"(!{left})"
        symbol = {"or": "||", "xor": "^", "and": "&&"}.get(name, "&&")
        return f"({left} {symbol} {right})"
    if expr.op.startswith("vector_"):
        return _vector(expr, deterministic)
    if expr.op in {"add", "subtract", "multiply", "divide", "power", "minimum", "maximum", "modulo"}:
        left = _child(expr.args[0], deterministic)
        right = _child(expr.args[1], deterministic)
        symbol = {
            "add": "+",
            "subtract": "-",
            "multiply": "*",
            "divide": "/",
            "power": "",
            "minimum": "min",
            "maximum": "max",
            "modulo": "%",
        }[expr.op]
        if expr.op == "power":
            return f"pow({left}, {right})"
        if expr.op in {"minimum", "maximum"}:
            return f"{symbol}({left}, {right})"
        return f"({left} {symbol} {right})"
    unary = {
        "absolute": "abs",
        "sqrt": "sqrt",
        "floor": "floor",
        "ceil": "ceil",
        "sine": "sin",
        "cosine": "cos",
        "tangent": "tan",
        "radians": "radians",
        "degrees": "degrees",
    }
    if expr.op in unary:
        return f"{unary[expr.op]}({_child(expr.args[0], deterministic)})"
    if expr.op == "fraction":
        return f"frac({_child(expr.args[0], deterministic)})"
    return "0"


def snippet(body: str, *, deterministic: bool) -> str:
    """A complete Attribute Wrangle snippet. The hash library is included when used."""

    prefix = ""
    if deterministic and "nb_rand" in body:
        prefix = vex_random_library() + "\n"
    return prefix + body.strip() + "\n"


def _child(value, deterministic: bool) -> str:
    if isinstance(value, Expr):
        return expression_to_vex(value, deterministic=deterministic)
    return _literal(value)


def _random(expr: Expr, deterministic: bool) -> str:
    data_type = str(expr.args[0]) if expr.args else "float"
    seed = _child(expr.args[3], deterministic) if len(expr.args) > 3 else "0"
    if "vector" in data_type:
        if deterministic:
            return f"set(nb_rand(int({seed}) + 11, @ptnum), nb_rand(int({seed}) + 29, @ptnum), nb_rand(int({seed}) + 47, @ptnum))"
        return f"set(rand(@ptnum + ({seed}) + 11), rand(@ptnum + ({seed}) + 29), rand(@ptnum + ({seed}) + 47))"
    if deterministic:
        return f"nb_rand(int({seed}), @ptnum)"
    return f"rand(@ptnum + ({seed}))"


def _vector(expr: Expr, deterministic: bool) -> str:
    name = expr.op.removeprefix("vector_")
    left = _child(expr.args[0], deterministic)
    right = _child(expr.args[1], deterministic) if len(expr.args) > 1 else "{0,0,0}"
    if name == "add":
        return f"({left} + {right})"
    if name == "subtract":
        return f"({left} - {right})"
    if name == "multiply":
        return f"({left} * {right})"
    if name == "scale":
        return f"({left} * ({right}))"
    if name == "normalize":
        return f"normalize({left})"
    if name == "dot":
        return f"dot({left}, {right})"
    if name == "cross":
        return f"cross({left}, {right})"
    if name == "length":
        return f"length({left})"
    if name == "distance":
        return f"distance({left}, {right})"
    return left


def _literal(value) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return f"{float(value):.6f}"
    if isinstance(value, (list, tuple)):
        items = list(value)[:3] or [0.0]
        while len(items) < 3:
            items.append(items[-1])
        return "set(" + ", ".join(f"{float(item):.6f}" for item in items[:3]) + ")"
    if value is None:
        return "0"
    return "0"


def _parm(identifier: str) -> str:
    from nodebridge.common.names import sanitize_identifier

    return sanitize_identifier(identifier)
