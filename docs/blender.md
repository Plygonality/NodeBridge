# Blender host

Status: **frontend and backend implemented** for a small Geometry Nodes
subset, at the construction-plan / fixture level. Live `bpy` extraction
is optional and not exercised in CI.

Blender is a peer host, not a privileged source.

```
Geometry Nodes  ↕  BlenderFrontend / BlenderBackend  ↕  Semantic IR
```

## Frontend

`BlenderFrontend.extract()` accepts:

* a `NativeGraph` fixture
* a JSON dict
* a duck-typed bpy tree (`nodes`, `links`, `bl_idname`)

`nodebridge.hosts.blender.runtime.native_from_bpy` uses importlib and
raises if `bpy` is missing.

`bl_idname` values become provenance, not IR operations. Parameter-aware
dispatch maps `ShaderNodeMath` / `ShaderNodeVectorMath` /
`FunctionNodeRandomValue` onto several semantic operations.

## Backend

`BlenderBackend.build()` returns a Geometry Nodes construction plan.
`generate()` emits bpy script **text**. Loading IR never runs it.

## Vertical slice mappings

| Semantic operation | Blender native type |
| --- | --- |
| `graph.input` / `graph.output` | `NodeGroupInput` / `NodeGroupOutput` |
| `points.distribute` | `GeometryNodeDistributePointsOnFaces` |
| `geometry.instance` | `GeometryNodeInstanceOnPoints` |
| `geometry.realize_instances` | `GeometryNodeRealizeInstances` |
| `geometry.transform` | `GeometryNodeTransform` |
| `geometry.primitive` | mesh primitive nodes |
| `random.vector` | `FunctionNodeRandomValue` |
| `math.*` | `ShaderNodeMath` |

## Runtime limitations

* Requires Blender 4.2+ for Geometry Nodes as used here.
* Nested groups, simulation zones, and viewer nodes are not lowered.
* The add-on under `blender_addon/` is a UI shell only.

## Isolation

`import bpy` is not a static import anywhere in the package. Only
`hosts/blender/runtime.py` loads it, and only when called.
