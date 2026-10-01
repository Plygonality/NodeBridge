# Architecture

NodeBridge is a compiler. Parsing, meaning, and target code stay separate.

```
Blender node tree
        │
        ▼
BlenderFrontend.parse          graph IR (structure)
        │
        ▼
analyze_dependencies           order, cycles, dead nodes, branches
        │
        ▼
semanticize                    semantic IR (operations)
        │
        ▼
normalize / rewrite rules      smaller semantic graph
        │
        ▼
capability + confidence        exact, equivalent, approximate, unsupported
        │
        ▼
HoudiniBackend / UnrealBackend generated Python
        │
        ▼
native SOP, MaterialX, COP, PCG, or Material graph
```

The rule: **do not translate node names. Translate procedural meaning.**

`GeometryNodeDistributePointsOnFaces` is metadata on a graph-IR node. The semantic operation is `points.distribute`. The Houdini backend chooses a Scatter SOP. The Unreal backend chooses a Surface Sampler. Those choices are recipes, not the identity of the IR.

## Two representations

### Graph IR (`nodebridge.ir.graph_ir`)

Preserves structure:

- `NodeTree`, `GraphNode`, `GraphSocket`, `GraphEdge`, `NodeParameter`
- node ids, names, source type names, defaults, nested groups
- JSON serialization for debugging

Editor coordinates are optional metadata. Ordering comes from links.

### Semantic IR (`nodebridge.core`)

Preserves meaning:

- `geometry.transform`, `points.distribute`, `geometry.instance`, `procedural.noise`
- sockets, parameters, nested graphs, provenance

The source Blender type is stored on the node as provenance. Backends are not allowed to treat that string as the operation.

## Rewrite rules

`nodebridge.compiler.rules` is a pass pipeline, not a hardcoded pair of examples.

- `CollapseReroutePass` deletes reroutes and reconnects neighbors.
- `FuseClampPass` turns min/max pairs into `math.clamp`.
- `SpatialNoiseMaskPass` fuses noise → map range → compare into `selection.spatial_noise` when each step has a single consumer.
- `FuseInstanceTransformPass` folds Rotate Instances and Scale Instances into the preceding Instance operation.

A rule that cannot match leaves the graph unchanged.

## Backends

`TargetBackend` is the host backend: `implementation_for`, `lower_node`, `build`, `generate`.

`HoudiniBackend` writes SOP Python, and switches to a Material Builder or a COP2 network from the graph system. `UnrealBackend` writes PCG Python, Material Editor Python, or an explicit compositor refusal.

Recipes are data (`Recipe`, `NodeTemplate`) registered on the host. They are not a single `if node.type` chain.

## Shared conversions

| Module | Responsibility |
| --- | --- |
| `nodebridge.common.coordinates` | Handedness, up axis, position, normal, scale, Euler, UV |
| `nodebridge.common.units` | Meters, centimeters, radians, degrees, frames |
| `nodebridge.common.random` | `random_unit(seed, element_id)` and the VEX port |
| `nodebridge.common.names` | `Building Scatter` → `building_scatter` |

Translators call these. They do not embed their own axis swaps.

## What stays out of the core

`import nodebridge` does not import `bpy`, `hou`, or `unreal`. The Blender panel lives in `nodebridge.addon` and is loaded only when Blender calls `register()`. Host SDKs are named inside generated scripts, which are text, and inside optional runtime modules via importlib.

Generated Python is not the IR. Opening a `.nodebridge.json` file does not run it.

## Extending

A new DCC implements `SourceFrontend` or a host backend and registers recipes. A new semantic operation is an `OperationSpec` plus zero or more recipes. Missing recipes classify as unsupported.

`TranslationFallbackProvider` can later explain a gap. The shipping compiler uses no provider.
