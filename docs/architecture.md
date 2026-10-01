# Architecture

NodeBridge is a compiler. Its central rule is **translate procedural meaning, not node names**: Blender node types are syntax, the Semantic IR is meaning, and each target backend decides the native implementation.

```
Blender node tree
    │  frontend/blender/parser.py         bpy objects -> Graph IR (no bpy import)
    ▼
Graph IR  (ir/graph.py)                   nodes, sockets, links, interfaces, groups, modifier values
    │  compiler/normalize.py              frames, reroutes, muted nodes, invalid links, dead nodes
    │  frontend/blender/lifting.py        per-node lifters -> semantic operations
    ▼
Semantic IR  (ir/semantic.py)             SCATTER, INSTANCE, NOISE, MATH, ... + exposed parameters
    │  backend.prepare()                  which node groups stay reusable (subnets) or are inlined
    │  compiler/rewrite.py + rules.py     idiom recognition, folding (fixpoint)
    │  compiler/rewrite.py                dead-operation elimination
    │  backend.lower()                    target-specific lowering hook
    │  pipeline.infer_parameter_roles()   unit-less parameters inherit the role of the ports they feed
    ▼
Classification  (translation/registry.py, compiler/capabilities.py)
    │                                     every op -> EXACT / EQUIVALENT / APPROXIMATE / UNSUPPORTED
    ▼
Target backend  (backend/houdini, backend/unreal)
    │                                     generate() -> readable Python using only documented APIs
    ▼
Generated code + translation report  (compiler/report.py)
```

## Package layout

```
src/nodebridge/
  __init__.py              version, bl_info, register()/unregister() (lazy add-on import)
  blender_manifest.toml    Blender 4.2+ extension manifest
  addon/                   Blender UI only: properties, operators, panels
  frontend/
    base.py                SourceFrontend interface + registry
    blender/               parser, context resolution, lifting framework, GN/shader/compositor lifters
  ir/
    types.py               DataType, TypeRef (field-ness), conversion rules
    graph.py               Graph IR dataclasses
    semantic.py            Semantic IR dataclasses (Const / Param / Link inputs)
    operations.py          registry of OperationSpec (ports with value roles)
    serialization.py       JSON for both IRs
    validation.py          structural and type validation
  compiler/
    analyzer.py            topological order, cycles (Tarjan), branches, dead nodes, subgraph extraction
    normalize.py           Graph IR normalization
    rewrite.py, rules.py   rewrite framework and built-in rules
    evaluate.py            reference Blender semantics for constant folding / baking
    subgraphs.py           node-group inlining policy helpers
    capabilities.py        capability matrix derived from translators
    diagnostics.py, report.py, pipeline.py
  translation/
    confidence.py          Confidence, Strictness, Classification
    registry.py            @translator registry
    fallback.py            optional TranslationFallbackProvider protocol (default None)
  backend/
    base.py                TargetBackend interface, script validation
    registry.py            backend registry
    codegen.py             readable Python emission helpers
    houdini/               SOP, VEX field compiler, HScript expressions, MaterialX, COP2
    unreal/                PCG, Materials, Post Process, script-level controls
  common/
    coordinates.py         frames, Euler orders, quaternions, Unreal rotators, UV, normal maps
    units.py               lengths, densities, angles, time / frames, value roles
    random.py              deterministic random(seed, id) in Python and VEX
    names.py               target-safe naming
  cli.py                   command-line interface
```

The add-on and the compiler are the same package. Only `addon/` and `frontend/blender/context.py` touch `bpy`, and only when Blender loads the add-on. All internal imports are relative, so the package works as a Blender extension (`bl_ext.<repo>.nodebridge`), as a legacy add-on, and as a normal Python package used by the CLI and tests.

## Two intermediate representations

**Graph IR** is a faithful copy of the source structure. It records socket identifiers *and* names, the enabled state of sockets (Random Value, Compare and Map Range have one socket per data type), defaults, node properties, color ramps, mute internal links, group references and the group interface, including subtypes such as `DISTANCE` or `FACTOR` and the current Geometry Nodes modifier values.

**Semantic IR** is a DAG of `SemanticOp(kind, inputs, params, outputs, source)`. An input is one of:

* `Const(value, type)`: a literal,
* `Param(key)`: a user-facing control (group input, labeled Value node),
* `Link(op, output)`: another operation's output,
* a tuple of these, for multi-input sockets.

Outputs carry a `TypeRef(base, field)`. Field-ness is what lets backends tell a single value apart from a per-element expression: the Houdini backend turns single values into HScript channel expressions and fields into VEX.

Operations are **data** (`ir/operations.py`). Each port declares a `ValueRole` (`LENGTH`, `AREA_DENSITY`, `POSITION`, `DIRECTION`, `SCALE`, `EULER`, `COLOR`, `UV`, ...) that the conversion layers use. Adding an operation means registering a spec; no compiler module changes.

## Lifting

`@lifts("GeometryNodeDistributePointsOnFaces")` registers a small function that reads sockets through `LiftContext` and emits operations. Some details:

* Lookups use socket *names*, preferring enabled sockets, so per-data-type socket variants resolve correctly in Blender 4.2 and 4.5.
* Implicit field inputs become shared `FIELD_INPUT` operations. For example, Random Value's unlinked ID is the element ID field, and Noise's unlinked Vector is position (or Generated coordinates in shaders).
* Group nodes become `SUBGRAPH` operations, and their trees are lifted recursively (cached, with recursion detection).
* Nodes without a lifter become `UNSUPPORTED_OPERATION`, with their links preserved.

## Rewrite rules

`compiler/rewrite.py` provides a `Pattern` matcher (kinds, params, nested inputs, single-use constraints) and a fixpoint engine. The built-in rules are:

| Rule | Recognizes | Produces |
| --- | --- | --- |
| `fold_constants` | Math / Vector Math / Compare / ... on constants | constants |
| `fold_switch` | Switch with a constant condition | the chosen branch |
| `identity_transform` | Transform with identity values | pass-through |
| `random_instance_attributes` | Instance on Points whose scale / rotation is a Random Value | `RANDOM_TRANSFORM` on the points |
| `random_instance_transform` | Rotate / Scale Instances (local, no pivot) with a Random Value, directly after instancing | `RANDOM_TRANSFORM` before instancing |
| `spatial_noise_mask` | Position → Noise → (Map Range) → Compare | `SPATIAL_NOISE_MASK` |
| `vignette` | Ellipse Mask → (Blur) → Multiply | `VIGNETTE` |

Rules only fire when the result is equivalent. For example, Rotate Instances is folded only when it is local, has a zero pivot and an all-true selection, and the instance scale is uniform. Each application is recorded as a compiler note in the report.

## Classification and the capability matrix

Backends register translators with `@translator(kind, target=..., context=..., confidence=..., implementation=..., explanation=..., limitations=..., classify=...)`. A `classify` function can downgrade the confidence for specific configurations (Poisson disk scattering, non-face extrusion, a scatter whose surface PCG cannot see, ...). `compiler/capabilities.py` derives the matrix from this registry, and `docs/support_matrix.md` is generated from it.

Strictness (*Exact only / Allow equivalent / Allow approximate*) never drops operations. Blocked operations become annotated placeholders and are listed in the report.

## Backends

### Houdini

* **Geometry → SOPs.** Native SOPs are used wherever a defensible mapping exists (scatter, copytopoints with packing, unpack, xform, polyextrude, merge, switch, sweep, resample, boolean, material, ...). Field inputs compile into an Attribute Wrangle placed before the consuming SOP; it writes standard attributes or groups (`scale`, `orient`, `setprimgroup`, `removepoint`). Wrangles run over the domain the consumer evaluates fields on: points, or primitives for face selections.
* **VEX is evaluated in Blender's frame**: `nb_b(@P)` converts to Z-up, and results convert back with `nb_h`, `nb_hs` and `nb_orient_h`. Blender math like "Separate XYZ → Z is height" therefore keeps its meaning.
* **Parameters.** Group inputs become spare parameters on the geo node. SOP parameters reference them with `ch("../width")`. Expressions over parameters (`Floors × Floor Height`) stay HScript expressions.
* **Groups.** A node group whose interface carries only geometry and single values becomes a SOP **subnet** with promoted parameters. Groups that pass fields are inlined, because SOP subnets cannot carry fields.
* **Safety.** Generated scripts create a new uniquely named container and never modify existing nodes. Parameter names that differ between Houdini versions are reported in `NB_WARNINGS`.
* **Shaders → MaterialX in `/mat`. Compositor → COP2 in `/img`.**

### Unreal Engine 5

* **Geometry → PCG.** PCG operates on points, so the backend maps the point-processing intent: Surface Sampler, Transform Points (random ranges, with per-axis Euler → rotator sign mapping), Spatial Noise + Density Filter for noise masks (the threshold is mapped back through Map Range), Merge, and Static Mesh Spawner. Instance geometry becomes an engine basic shape scaled to the Blender primitive's size, with the material as an override.
* **Controls.** Group inputs become script-level constants, and derived values stay Python expressions over them.
* **Shaders → Material assets** via `MaterialEditingLibrary`. Labeled Value / RGB nodes become Scalar / Vector parameters. Color ramps and Map Range are rebuilt exactly from Lerp / Saturate arithmetic. UV V is flipped, and positions are converted from Unreal's centimeter, left-handed space.
* **Compositor → an unbound Post Process Volume.**
* **Safety.** `add_edge` returns `None` for unknown pin labels, so pins are tried from candidate lists. Missing classes, enums or properties are reported in `NB_WARNINGS`. Assets are never overwritten.

## Conversion layers

* `common/coordinates.py`: each coordinate system declares a basis matrix relative to Blender. Points, directions, normals, scales, rotation matrices, Euler angles in any of the six orders, quaternions, Unreal `FRotator` (mirroring `FRotationMatrix` / `FMatrix::Rotator`), UV origins and normal-map conventions are all converted here. One identity the Houdini backend relies on is tested: Blender XYZ Euler `(a, b, c)` equals Houdini rotation order `xzy` with `r = (a, c, -b)`.
* `common/units.py`: lengths (with scene scale), area densities, angles, frames and seconds, driven by each value's role.
* `common/random.py`: `random(seed, element_id, stream)` built on a Park–Miller LCG with Schrage's method, so every intermediate fits in a signed 32-bit integer. The same algorithm is emitted as VEX, and the tests compile that VEX as C to check it.

## Extending

* **A new operation:** register an `OperationSpec`, add a lifter, add translators per backend.
* **A new target** (Maya, Bifrost, Godot, Nuke, ...): subclass `TargetBackend`, register translators for its contexts, then call `register_backend`. The panel's target list, the capability matrix and the docs pick it up automatically.
* **A new source** (a Houdini or Unreal frontend): subclass `SourceFrontend` and register lifters for that application's node types. Backends stay unchanged, which is how NodeBridge can become bidirectional.

## Design choices

* **No AI in the translation path.** Translation is deterministic. `TranslationFallbackProvider` can only add suggestions to the report.
* **Never fabricate APIs.** When a target cannot build something through its public Python API, the operation is classified and reported, a placeholder or fallback is generated, and the limitation is documented.
* **Generated code is a product.** It is readable, commented, organized per operation, and validated (`ast.parse`, required imports, a `build()` entry point) before it is shown to the user.
