# Unreal Engine 5 host

Status: **peer host architecture implemented**. Frontend and backend
exist. Live PCG editor integration is **experimental and editor-only**.
CI uses construction-plan fixtures, not the Unreal editor.

Unreal is not a special terminal export target.

```
PCG graph  ↕  UnrealFrontend / UnrealBackend  ↕  Semantic IR
```

## API investigation (UE 5.7 experimental Python)

Documented on `unreal.PCGGraph` / `unreal.PCGNode`:

* `add_node_of_type(settings_class)` — create a node
* `add_edge(from, from_pin, to, to_pin)` — wire pins
* `get_input_node()` / `get_output_node()`
* `nodes`, `node.get_settings()`, `set_node_position`

Known constraints:

* The API is experimental and version-sensitive.
* `add_edge` silently no-ops on wrong pin labels (Surface Sampler input
  is `Surface`, not `In`; graph input output pin is `In`).
* There is no reliable public `graph.edges` listing. Pin-edge traversal
  is incomplete, so live *inspection* of links is limited.
* Construction requires the Unreal editor; it cannot run in CI.

NodeBridge therefore:

* implements frontend/backend contracts and fixture mappings
* emits construction plans without calling Unreal
* emits script text that uses the documented 5.7 APIs
* does **not** fabricate additional editor calls
* classifies PCG spawning vs. Geometry Nodes instancing as APPROXIMATE

## Vertical slice mappings

| Semantic operation | PCG settings class | Fidelity |
| --- | --- | --- |
| `points.distribute` | `PCGSurfaceSamplerSettings` | EXACT |
| `geometry.transform` | `PCGTransformPointsSettings` | EXACT |
| `geometry.instance` | `PCGStaticMeshSpawnerSettings` | APPROXIMATE |
| `geometry.realize_instances` | same spawner (no realize analogue) | APPROXIMATE |
| `random.float` | `PCGAttributeNoiseSettings` | EXACT/APPROXIMATE |
| `math.*` | none | UNSUPPORTED |

Math and vector ops are unsupported on PCG rather than silently rewritten
as Materials or Blueprints.

## Isolation

`unreal` is loaded via importlib from `hosts/unreal/runtime.py` only.
