"""Registry of semantic operation specifications.

Operations are data. Adding one means calling :func:`register_operation`
with its ports; no compiler module needs editing. Frontends lift source
nodes onto these kinds and backends register translators for them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..common.units import ValueRole as R
from .types import DataType as T


class Category(str, Enum):
    STRUCTURAL = "structural"
    GEOMETRY = "geometry"
    FIELD = "field"
    SHADER = "shader"
    COMPOSITOR = "compositor"


@dataclass(frozen=True)
class Port:
    name: str
    type: T
    role: R = R.SCALAR
    field: bool = False
    multi: bool = False


@dataclass(frozen=True)
class OperationSpec:
    kind: str
    category: Category
    description: str
    inputs: tuple[Port, ...] = ()
    outputs: tuple[Port, ...] = ()
    params: dict[str, Any] = field(default_factory=dict)
    dynamic: bool = False  # ports defined per instance (subgraphs, unsupported ops)

    def input(self, name: str) -> Port | None:
        return next((p for p in self.inputs if p.name == name), None)

    def output(self, name: str) -> Port | None:
        return next((p for p in self.outputs if p.name == name), None)


_REGISTRY: dict[str, OperationSpec] = {}


def register_operation(spec: OperationSpec, *, replace: bool = False) -> OperationSpec:
    if spec.kind in _REGISTRY and not replace:
        raise ValueError(f"operation {spec.kind!r} already registered")
    _REGISTRY[spec.kind] = spec
    return spec


def get_operation(kind: str) -> OperationSpec | None:
    return _REGISTRY.get(kind)


def list_operations() -> list[OperationSpec]:
    return sorted(_REGISTRY.values(), key=lambda spec: (spec.category.value, spec.kind))


def category_of(kind: str) -> Category:
    spec = _REGISTRY.get(kind)
    return spec.category if spec else Category.STRUCTURAL


def _p(name: str, type_: T, role: R = R.SCALAR, *, f: bool = False, multi: bool = False) -> Port:
    return Port(name, type_, role, f, multi)


def _op(kind: str, category: Category, description: str, inputs=(), outputs=(), params=None, dynamic=False) -> None:
    register_operation(OperationSpec(kind, category, description, tuple(inputs), tuple(outputs), dict(params or {}), dynamic))


G = Category.GEOMETRY
F = Category.FIELD
S = Category.SHADER
C = Category.COMPOSITOR
X = Category.STRUCTURAL
GEO = _p("geometry", T.GEOMETRY)
SEL = _p("selection", T.BOOL, R.BOOLEAN, f=True)

# --- structural ---------------------------------------------------------
_op("GROUP_INPUT", X, "Interface inputs of a graph or group.", dynamic=True)
_op("GROUP_OUTPUT", X, "Interface outputs of a graph or group.", dynamic=True)
_op("GEOMETRY_INPUT", G, "Geometry entering the graph (modifier object / group input).", outputs=[GEO], params={"name": "Geometry"})
_op("GEOMETRY_OUTPUT", G, "Geometry leaving the graph.", inputs=[GEO], params={"name": "Geometry"})
_op("REROUTE", X, "Pass-through. Eliminated during normalization.", dynamic=True)
_op("SUBGRAPH", X, "Instance of a nested group with its own semantic graph.", dynamic=True, params={"graph": None})
_op("CUSTOM_EXPRESSION", X, "Target-language expression supplied explicitly.", dynamic=True, params={"language": None, "code": ""})
_op("UNSUPPORTED_OPERATION", X, "A source construct with no semantic lifting yet.", dynamic=True)

# --- geometry -----------------------------------------------------------
_op(
    "PRIMITIVE",
    G,
    "Procedural mesh primitive.",
    inputs=[
        _p("size", T.VECTOR3, R.SCALE),
        _p("size_x", T.FLOAT, R.LENGTH),
        _p("size_y", T.FLOAT, R.LENGTH),
        _p("vertices_x", T.INT, R.INTEGER),
        _p("vertices_y", T.INT, R.INTEGER),
        _p("vertices_z", T.INT, R.INTEGER),
        _p("vertices", T.INT, R.INTEGER),
        _p("segments", T.INT, R.INTEGER),
        _p("rings", T.INT, R.INTEGER),
        _p("subdivisions", T.INT, R.INTEGER),
        _p("side_segments", T.INT, R.INTEGER),
        _p("fill_segments", T.INT, R.INTEGER),
        _p("radius", T.FLOAT, R.LENGTH),
        _p("radius_top", T.FLOAT, R.LENGTH),
        _p("radius_bottom", T.FLOAT, R.LENGTH),
        _p("depth", T.FLOAT, R.LENGTH),
        _p("count", T.INT, R.INTEGER),
        _p("start", T.VECTOR3, R.POSITION),
        _p("offset", T.VECTOR3, R.DIRECTION),
    ],
    outputs=[_p("geometry", T.MESH), _p("uv", T.VECTOR3, R.UV, f=True)],
    params={"shape": ("cube", "grid", "uv_sphere", "ico_sphere", "cylinder", "cone", "line", "circle"), "fill_type": None},
)
_op(
    "CURVE",
    G,
    "Procedural curve primitive.",
    inputs=[
        _p("start", T.VECTOR3, R.POSITION),
        _p("end", T.VECTOR3, R.POSITION),
        _p("resolution", T.INT, R.INTEGER),
        _p("radius", T.FLOAT, R.LENGTH),
        _p("rotations", T.FLOAT),
        _p("start_radius", T.FLOAT, R.LENGTH),
        _p("end_radius", T.FLOAT, R.LENGTH),
        _p("height", T.FLOAT, R.LENGTH),
    ],
    outputs=[_p("geometry", T.CURVE)],
    params={"shape": ("line", "circle", "spiral")},
)
_op(
    "TRANSFORM",
    G,
    "Rigid transform of whole geometry.",
    inputs=[GEO, _p("translation", T.VECTOR3, R.POSITION), _p("rotation", T.ROTATION, R.EULER), _p("scale", T.VECTOR3, R.SCALE)],
    outputs=[GEO],
)
_op("MERGE", G, "Join several geometries.", inputs=[_p("geometry", T.GEOMETRY, multi=True)], outputs=[GEO])
_op(
    "SEPARATE",
    G,
    "Split geometry by a selection.",
    inputs=[GEO, SEL],
    outputs=[_p("selection", T.GEOMETRY), _p("inverted", T.GEOMETRY)],
    params={"domain": "POINT"},
)
_op("DELETE_GEOMETRY", G, "Delete selected elements.", inputs=[GEO, SEL], outputs=[GEO], params={"domain": "POINT", "mode": "ALL"})
_op(
    "SCATTER",
    G,
    "Distribute points on a surface.",
    inputs=[
        _p("geometry", T.MESH),
        SEL,
        _p("density", T.FLOAT, R.AREA_DENSITY, f=True),
        _p("density_factor", T.FLOAT, R.FACTOR, f=True),
        _p("distance_min", T.FLOAT, R.LENGTH),
        _p("density_max", T.FLOAT, R.AREA_DENSITY),
        _p("seed", T.INT, R.INTEGER),
    ],
    outputs=[_p("points", T.POINTS), _p("normal", T.VECTOR3, R.NORMAL, f=True), _p("rotation", T.ROTATION, R.EULER, f=True)],
    params={"distribution_mode": ("random", "poisson"), "normal_alignment": False},
)
_op(
    "INSTANCE",
    G,
    "Instance geometry on points.",
    inputs=[
        _p("points", T.POINTS),
        SEL,
        _p("instance", T.GEOMETRY),
        _p("pick_instance", T.BOOL, R.BOOLEAN, f=True),
        _p("instance_index", T.INT, R.INTEGER, f=True),
        _p("rotation", T.ROTATION, R.EULER, f=True),
        _p("scale", T.VECTOR3, R.SCALE, f=True),
    ],
    outputs=[_p("instances", T.INSTANCES)],
)
_op("REALIZE_INSTANCES", G, "Convert instances into real geometry.", inputs=[GEO], outputs=[GEO])
_op(
    "INSTANCE_TRANSFORM",
    G,
    "Rotate, scale or translate existing instances.",
    inputs=[
        _p("geometry", T.INSTANCES),
        SEL,
        _p("rotation", T.ROTATION, R.EULER, f=True),
        _p("scale", T.VECTOR3, R.SCALE, f=True),
        _p("translation", T.VECTOR3, R.DIRECTION, f=True),
        _p("pivot", T.VECTOR3, R.POSITION, f=True),
        _p("local_space", T.BOOL, R.BOOLEAN, f=True),
    ],
    outputs=[_p("geometry", T.INSTANCES)],
    params={"mode": ("rotate", "scale", "translate")},
)
_op(
    "RANDOM_TRANSFORM",
    G,
    "Per-element random rotation / scale / offset within ranges.",
    inputs=[_p("geometry", T.POINTS), _p("seed", T.INT, R.INTEGER)],
    outputs=[_p("geometry", T.POINTS)],
    params={
        "rotation_min": None,
        "rotation_max": None,
        "scale_min": None,
        "scale_max": None,
        "offset_min": None,
        "offset_max": None,
        "uniform_scale": False,
    },
)
_op(
    "TRANSFORM_POINTS",
    G,
    "Per-point transform (fixed values).",
    inputs=[_p("geometry", T.POINTS), _p("offset", T.VECTOR3, R.DIRECTION), _p("rotation", T.ROTATION, R.EULER), _p("scale", T.VECTOR3, R.SCALE)],
    outputs=[_p("geometry", T.POINTS)],
)
_op(
    "SET_POSITION",
    G,
    "Write point positions.",
    inputs=[GEO, SEL, _p("position", T.VECTOR3, R.POSITION, f=True), _p("offset", T.VECTOR3, R.DIRECTION, f=True)],
    outputs=[GEO],
)
_op(
    "ATTRIBUTE_WRITE",
    G,
    "Store a named attribute.",
    inputs=[GEO, SEL, _p("name", T.STRING, R.STRING), _p("value", T.ANY, f=True)],
    outputs=[GEO],
    params={"data_type": "FLOAT", "domain": "POINT"},
)
_op(
    "EXTRUDE",
    G,
    "Extrude mesh elements.",
    inputs=[
        _p("geometry", T.MESH),
        SEL,
        _p("offset", T.VECTOR3, R.DIRECTION, f=True),
        _p("offset_scale", T.FLOAT, R.LENGTH, f=True),
        _p("individual", T.BOOL, R.BOOLEAN),
    ],
    outputs=[_p("geometry", T.MESH), _p("top", T.BOOL, R.BOOLEAN, f=True), _p("side", T.BOOL, R.BOOLEAN, f=True)],
    params={"mode": "FACES"},
)
_op("SUBDIVIDE", G, "Subdivide a mesh.", inputs=[_p("geometry", T.MESH), _p("level", T.INT, R.INTEGER)], outputs=[_p("geometry", T.MESH)], params={"method": ("simple", "catmull_clark")})
_op(
    "CURVE_RESAMPLE",
    G,
    "Resample curves by count or length.",
    inputs=[_p("geometry", T.CURVE), SEL, _p("count", T.INT, R.INTEGER), _p("length", T.FLOAT, R.LENGTH)],
    outputs=[_p("geometry", T.CURVE)],
    params={"mode": "COUNT"},
)
_op(
    "CURVE_TO_MESH",
    G,
    "Sweep a profile along curves.",
    inputs=[_p("geometry", T.CURVE), _p("profile", T.CURVE), _p("fill_caps", T.BOOL, R.BOOLEAN), _p("scale", T.FLOAT, R.FACTOR, f=True)],
    outputs=[_p("geometry", T.MESH)],
)
_op("MESH_TO_CURVE", G, "Convert mesh edges to curves.", inputs=[_p("geometry", T.MESH), SEL], outputs=[_p("geometry", T.CURVE)])
_op("MESH_TO_POINTS", G, "Convert mesh elements to points.", inputs=[_p("geometry", T.MESH), SEL, _p("radius", T.FLOAT, R.LENGTH, f=True)], outputs=[_p("geometry", T.POINTS)], params={"mode": "VERTICES"})
_op("BOOLEAN", G, "Mesh boolean.", inputs=[_p("mesh_a", T.MESH), _p("mesh_b", T.MESH, multi=True)], outputs=[_p("geometry", T.MESH)], params={"operation": "DIFFERENCE"})
_op("MATERIAL_ASSIGNMENT", G, "Assign a material.", inputs=[GEO, SEL, _p("material", T.MATERIAL, R.REFERENCE)], outputs=[GEO])
_op(
    "OBJECT_REFERENCE",
    G,
    "Geometry and transform of a scene object.",
    inputs=[_p("object", T.OBJECT, R.REFERENCE), _p("as_instance", T.BOOL, R.BOOLEAN)],
    outputs=[GEO, _p("location", T.VECTOR3, R.POSITION), _p("rotation", T.ROTATION, R.EULER), _p("scale", T.VECTOR3, R.SCALE)],
    params={"transform_space": "ORIGINAL"},
)
_op("COLLECTION_REFERENCE", G, "Instances of a scene collection.", inputs=[_p("collection", T.COLLECTION, R.REFERENCE)], outputs=[_p("geometry", T.INSTANCES)])
_op(
    "SWITCH",
    G,
    "Choose between two inputs.",
    inputs=[_p("switch", T.BOOL, R.BOOLEAN, f=True), _p("false", T.ANY, f=True), _p("true", T.ANY, f=True)],
    outputs=[_p("output", T.ANY, f=True)],
    params={"input_type": "GEOMETRY"},
)
_op("SELECTION", G, "Named or computed element selection.", inputs=[GEO, SEL], outputs=[GEO], params={"domain": "POINT"})
_op("FILTER", G, "Keep only selected elements.", inputs=[GEO, SEL], outputs=[GEO], params={"domain": "POINT"})

# --- fields / values ----------------------------------------------------
_op(
    "FIELD_INPUT",
    F,
    "Built-in per-element attribute (position, normal, index, id, uv, ...).",
    outputs=[_p("value", T.ANY, f=True)],
    params={"field": ("position", "normal", "index", "id", "uv", "generated", "object", "world_position", "camera", "reflection", "tangent")},
)
_op("ATTRIBUTE_READ", F, "Read a named attribute.", inputs=[_p("name", T.STRING, R.STRING)], outputs=[_p("value", T.ANY, f=True), _p("exists", T.BOOL, f=True)], params={"data_type": "FLOAT"})
_op(
    "RANDOM",
    F,
    "Random value per element.",
    inputs=[_p("min", T.ANY), _p("max", T.ANY), _p("probability", T.FLOAT, R.FACTOR), _p("id", T.INT, R.INTEGER, f=True), _p("seed", T.INT, R.INTEGER, f=True)],
    outputs=[_p("value", T.ANY, f=True)],
    params={"data_type": ("FLOAT", "INT", "FLOAT_VECTOR", "BOOLEAN")},
)
_op(
    "NOISE",
    F,
    "Fractal gradient noise.",
    inputs=[
        _p("vector", T.VECTOR3, R.POSITION, f=True),
        _p("w", T.FLOAT),
        _p("scale", T.FLOAT),
        _p("detail", T.FLOAT),
        _p("roughness", T.FLOAT, R.FACTOR),
        _p("lacunarity", T.FLOAT),
        _p("distortion", T.FLOAT),
    ],
    outputs=[_p("fac", T.FLOAT, R.FACTOR, f=True), _p("color", T.COLOR, R.COLOR, f=True)],
    params={"dimensions": "3D", "noise_type": "FBM", "normalize": True},
)
_op(
    "VORONOI",
    F,
    "Cellular (Worley) noise.",
    inputs=[_p("vector", T.VECTOR3, R.POSITION, f=True), _p("scale", T.FLOAT), _p("randomness", T.FLOAT, R.FACTOR), _p("detail", T.FLOAT)],
    outputs=[_p("distance", T.FLOAT, f=True), _p("color", T.COLOR, R.COLOR, f=True), _p("position", T.VECTOR3, R.POSITION, f=True)],
    params={"dimensions": "3D", "feature": "F1", "distance": "EUCLIDEAN"},
)
_op(
    "PROCEDURAL_TEXTURE",
    F,
    "Other procedural textures (gradient, checker, wave).",
    inputs=[_p("vector", T.VECTOR3, R.POSITION, f=True), _p("scale", T.FLOAT)],
    outputs=[_p("fac", T.FLOAT, f=True), _p("color", T.COLOR, R.COLOR, f=True)],
    params={"texture": ("gradient", "checker", "wave")},
)
_op(
    "MAP_RANGE",
    F,
    "Remap a value between ranges.",
    inputs=[_p("value", T.FLOAT, f=True), _p("from_min", T.FLOAT, f=True), _p("from_max", T.FLOAT, f=True), _p("to_min", T.FLOAT, f=True), _p("to_max", T.FLOAT, f=True), _p("steps", T.FLOAT, f=True)],
    outputs=[_p("result", T.FLOAT, f=True)],
    params={"interpolation": "LINEAR", "clamp": True, "data_type": "FLOAT"},
)
_op("MATH", F, "Scalar math.", inputs=[_p("a", T.FLOAT, f=True), _p("b", T.FLOAT, f=True), _p("c", T.FLOAT, f=True)], outputs=[_p("value", T.FLOAT, f=True)], params={"operation": "ADD", "clamp": False})
_op(
    "VECTOR_MATH",
    F,
    "Vector math.",
    inputs=[_p("a", T.VECTOR3, f=True), _p("b", T.VECTOR3, f=True), _p("c", T.VECTOR3, f=True), _p("scale", T.FLOAT, f=True)],
    outputs=[_p("vector", T.VECTOR3, f=True), _p("value", T.FLOAT, f=True)],
    params={"operation": "ADD"},
)
_op(
    "COMPARE",
    F,
    "Compare two values.",
    inputs=[_p("a", T.ANY, f=True), _p("b", T.ANY, f=True), _p("c", T.FLOAT, f=True), _p("angle", T.FLOAT, R.ANGLE, f=True), _p("epsilon", T.FLOAT, f=True)],
    outputs=[_p("result", T.BOOL, R.BOOLEAN, f=True)],
    params={"operation": "GREATER_THAN", "data_type": "FLOAT", "mode": "ELEMENT"},
)
_op("BOOLEAN_MATH", F, "Boolean logic.", inputs=[_p("a", T.BOOL, R.BOOLEAN, f=True), _p("b", T.BOOL, R.BOOLEAN, f=True)], outputs=[_p("value", T.BOOL, R.BOOLEAN, f=True)], params={"operation": "AND"})
_op("COMBINE_VECTOR", F, "Build a vector from components.", inputs=[_p("x", T.FLOAT, f=True), _p("y", T.FLOAT, f=True), _p("z", T.FLOAT, f=True)], outputs=[_p("vector", T.VECTOR3, f=True)])
_op("SEPARATE_VECTOR", F, "Split a vector into components.", inputs=[_p("vector", T.VECTOR3, f=True)], outputs=[_p("x", T.FLOAT, f=True), _p("y", T.FLOAT, f=True), _p("z", T.FLOAT, f=True)])
_op(
    "MIX",
    F,
    "Blend two values.",
    inputs=[_p("factor", T.FLOAT, R.FACTOR, f=True), _p("a", T.ANY, f=True), _p("b", T.ANY, f=True)],
    outputs=[_p("result", T.ANY, f=True)],
    params={"data_type": "FLOAT", "blend_type": "MIX", "clamp_factor": True, "clamp_result": False},
)
_op("COLOR_RAMP", F, "Piecewise color gradient.", inputs=[_p("fac", T.FLOAT, R.FACTOR, f=True)], outputs=[_p("color", T.COLOR, R.COLOR, f=True), _p("alpha", T.FLOAT, f=True)], params={"stops": [], "interpolation": "LINEAR"})
_op(
    "COLOR_OPERATION",
    F,
    "Color adjustments (invert, hue/saturation, gamma, brightness/contrast, separate/combine).",
    inputs=[_p("color", T.COLOR, R.COLOR, f=True), _p("factor", T.FLOAT, R.FACTOR, f=True), _p("a", T.FLOAT, f=True), _p("b", T.FLOAT, f=True), _p("c", T.FLOAT, f=True)],
    outputs=[_p("color", T.COLOR, R.COLOR, f=True), _p("value", T.FLOAT, f=True), _p("r", T.FLOAT, f=True), _p("g", T.FLOAT, f=True), _p("b", T.FLOAT, f=True)],
    params={"operation": ("invert", "hue_saturation", "gamma", "bright_contrast", "rgb_to_bw", "separate_rgb", "combine_rgb")},
)
_op(
    "ALIGN_ROTATION",
    F,
    "Rotate a rotation so one axis aligns with a vector.",
    inputs=[_p("rotation", T.ROTATION, R.EULER, f=True), _p("factor", T.FLOAT, R.FACTOR, f=True), _p("vector", T.VECTOR3, R.DIRECTION, f=True)],
    outputs=[_p("rotation", T.ROTATION, R.EULER, f=True)],
    params={"axis": "Z", "pivot_axis": "AUTO"},
)
_op(
    "PROXIMITY",
    F,
    "Closest point on target geometry.",
    inputs=[_p("target", T.GEOMETRY), _p("source_position", T.VECTOR3, R.POSITION, f=True)],
    outputs=[_p("position", T.VECTOR3, R.POSITION, f=True), _p("distance", T.FLOAT, R.LENGTH, f=True), _p("is_valid", T.BOOL, f=True)],
    params={"target_element": "FACES"},
)
_op(
    "RAYCAST",
    F,
    "Ray intersection with target geometry.",
    inputs=[_p("target", T.GEOMETRY), _p("source_position", T.VECTOR3, R.POSITION, f=True), _p("ray_direction", T.VECTOR3, R.DIRECTION, f=True), _p("ray_length", T.FLOAT, R.LENGTH, f=True)],
    outputs=[_p("is_hit", T.BOOL, f=True), _p("hit_position", T.VECTOR3, R.POSITION, f=True), _p("hit_normal", T.VECTOR3, R.NORMAL, f=True), _p("hit_distance", T.FLOAT, R.LENGTH, f=True)],
)
_op("SAMPLE", F, "Sample a field on other geometry.", inputs=[_p("geometry", T.GEOMETRY), _p("value", T.ANY, f=True), _p("index", T.INT, f=True)], outputs=[_p("value", T.ANY, f=True)], params={"mode": "INDEX", "domain": "POINT"})
_op("INTERPOLATE", F, "Evaluate a field on another domain.", inputs=[_p("value", T.ANY, f=True)], outputs=[_p("value", T.ANY, f=True)], params={"domain": "POINT"})
_op(
    "SPATIAL_NOISE_MASK",
    F,
    "Boolean mask: noise of (scaled) position compared with a threshold.",
    inputs=[_p("vector", T.VECTOR3, R.POSITION, f=True), _p("scale", T.FLOAT), _p("detail", T.FLOAT), _p("roughness", T.FLOAT), _p("threshold", T.FLOAT)],
    outputs=[_p("mask", T.BOOL, R.BOOLEAN, f=True)],
    params={"operation": "GREATER_THAN", "remap": None},
)

# --- shading -------------------------------------------------------------
_op(
    "SHADER_BSDF",
    S,
    "Surface shading model.",
    inputs=[
        _p("base_color", T.COLOR, R.COLOR, f=True),
        _p("metallic", T.FLOAT, R.FACTOR, f=True),
        _p("roughness", T.FLOAT, R.FACTOR, f=True),
        _p("ior", T.FLOAT, f=True),
        _p("alpha", T.FLOAT, R.FACTOR, f=True),
        _p("normal", T.VECTOR3, R.NORMAL, f=True),
        _p("specular", T.FLOAT, R.FACTOR, f=True),
        _p("emission_color", T.COLOR, R.COLOR, f=True),
        _p("emission_strength", T.FLOAT, f=True),
        _p("transmission", T.FLOAT, R.FACTOR, f=True),
        _p("coat", T.FLOAT, R.FACTOR, f=True),
        _p("coat_roughness", T.FLOAT, R.FACTOR, f=True),
        _p("sheen", T.FLOAT, R.FACTOR, f=True),
        _p("subsurface", T.FLOAT, R.FACTOR, f=True),
        _p("strength", T.FLOAT, f=True),
        _p("color", T.COLOR, R.COLOR, f=True),
    ],
    outputs=[_p("shader", T.SHADER)],
    params={"model": ("principled", "diffuse", "emission")},
)
_op("SHADER_MIX", S, "Mix two shaders.", inputs=[_p("factor", T.FLOAT, R.FACTOR, f=True), _p("a", T.SHADER), _p("b", T.SHADER)], outputs=[_p("shader", T.SHADER)], params={"mode": "MIX"})
_op("MATERIAL_OUTPUT", S, "Material surface / displacement outputs.", inputs=[_p("surface", T.SHADER), _p("displacement", T.VECTOR3, f=True)], params={"material": ""})
_op(
    "TEXTURE_SAMPLE",
    S,
    "Sample an image texture.",
    inputs=[_p("vector", T.VECTOR3, R.UV, f=True), _p("image", T.IMAGE, R.REFERENCE)],
    outputs=[_p("color", T.COLOR, R.COLOR, f=True), _p("alpha", T.FLOAT, f=True)],
    params={"interpolation": "Linear", "extension": "REPEAT", "colorspace": "sRGB"},
)
_op(
    "MAPPING",
    S,
    "Transform texture coordinates.",
    inputs=[_p("vector", T.VECTOR3, f=True), _p("location", T.VECTOR3, f=True), _p("rotation", T.VECTOR3, R.EULER, f=True), _p("scale", T.VECTOR3, f=True)],
    outputs=[_p("vector", T.VECTOR3, f=True)],
    params={"vector_type": "POINT"},
)
_op(
    "BUMP",
    S,
    "Perturb normals from a height field.",
    inputs=[_p("strength", T.FLOAT, R.FACTOR, f=True), _p("distance", T.FLOAT, R.LENGTH, f=True), _p("height", T.FLOAT, f=True), _p("normal", T.VECTOR3, R.NORMAL, f=True)],
    outputs=[_p("normal", T.VECTOR3, R.NORMAL, f=True)],
    params={"invert": False},
)
_op("NORMAL_MAP", S, "Tangent-space normal map.", inputs=[_p("strength", T.FLOAT, f=True), _p("color", T.COLOR, f=True)], outputs=[_p("normal", T.VECTOR3, R.NORMAL, f=True)], params={"space": "TANGENT"})
_op("SHADER_OPERATION", S, "Other shading operations.", dynamic=True, params={"operation": None})
_op("TEXTURE_COORDINATE", S, "Texture coordinate sources.", outputs=[_p("vector", T.VECTOR3, f=True)], params={"space": "UV"})

# --- compositing ---------------------------------------------------------
IMG = _p("image", T.COLOR, R.COLOR)
_op("RENDER_LAYER", C, "Rendered image of a view layer.", outputs=[IMG, _p("alpha", T.FLOAT)], params={"layer": "", "scene": ""})
_op("IMAGE_INPUT", C, "Image file input.", inputs=[_p("image_ref", T.IMAGE, R.REFERENCE)], outputs=[IMG, _p("alpha", T.FLOAT)])
_op("COMPOSITE_OUTPUT", C, "Final composite.", inputs=[IMG], params={"viewer": False})
_op(
    "GLARE",
    C,
    "Bloom / streaks / ghosts from bright areas.",
    inputs=[IMG, _p("threshold", T.FLOAT), _p("strength", T.FLOAT), _p("mix", T.FLOAT), _p("size", T.FLOAT)],
    outputs=[IMG],
    params={"glare_type": "BLOOM", "quality": "MEDIUM"},
)
_op(
    "COLOR_BALANCE",
    C,
    "Lift / gamma / gain (or offset / power / slope) grading.",
    inputs=[IMG, _p("factor", T.FLOAT, R.FACTOR), _p("lift", T.COLOR), _p("gamma", T.COLOR), _p("gain", T.COLOR)],
    outputs=[IMG],
    params={"method": "LIFT_GAMMA_GAIN"},
)
_op("COLOR_CORRECTION", C, "Saturation / contrast / gamma / gain grading.", inputs=[IMG, _p("saturation", T.FLOAT), _p("contrast", T.FLOAT), _p("gamma", T.FLOAT), _p("gain", T.FLOAT)], outputs=[IMG])
_op("BLUR", C, "Image blur.", inputs=[IMG, _p("size", T.VECTOR2)], outputs=[IMG], params={"filter_type": "GAUSS", "relative": False})
_op("BRIGHT_CONTRAST", C, "Brightness / contrast.", inputs=[IMG, _p("bright", T.FLOAT), _p("contrast", T.FLOAT)], outputs=[IMG])
_op("HUE_SATURATION", C, "Hue / saturation / value.", inputs=[IMG, _p("hue", T.FLOAT), _p("saturation", T.FLOAT), _p("value", T.FLOAT), _p("factor", T.FLOAT)], outputs=[IMG])
_op("GAMMA", C, "Gamma.", inputs=[IMG, _p("gamma", T.FLOAT)], outputs=[IMG])
_op("EXPOSURE", C, "Exposure in stops.", inputs=[IMG, _p("exposure", T.FLOAT)], outputs=[IMG])
_op("LENS_DISTORTION", C, "Lens distortion / dispersion.", inputs=[IMG, _p("distortion", T.FLOAT), _p("dispersion", T.FLOAT)], outputs=[IMG])
_op("ELLIPSE_MASK", C, "Elliptical mask.", inputs=[_p("mask", T.FLOAT), _p("value", T.FLOAT), _p("position", T.VECTOR2), _p("size", T.VECTOR2), _p("rotation", T.FLOAT, R.ANGLE)], outputs=[_p("mask", T.FLOAT)], params={"mask_type": "ADD"})
_op("VIGNETTE", C, "Radial darkening toward the frame edges.", inputs=[IMG, _p("intensity", T.FLOAT), _p("size", T.VECTOR2), _p("softness", T.FLOAT)], outputs=[IMG])
_op("INVERT", C, "Invert colors.", inputs=[IMG, _p("factor", T.FLOAT)], outputs=[IMG])
_op("COMPOSITOR_OPERATION", C, "Other compositor operations.", dynamic=True, params={"operation": None})
