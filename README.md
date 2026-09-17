# NodeBridge

NodeBridge is a **cross-DCC compiler for procedural graphs**.

A procedural system authored in one supported DCC or game engine should be convertible into an editable native procedural system in another supported application — without requiring the artist to rebuild the graph from scratch.

**NodeBridge translates procedural semantics, not node names.**

```
                         NodeBridge
                    Semantic Compiler

                           IR
                           │
                ┌──────────┼──────────┐
                │          │          │
             Blender    Houdini     Unreal
                ↕          ↕          ↕
               GN        SOP/VEX      PCG
```

Each host can operate as a frontend (native → IR), a backend (IR → native), or both.

## Why this is hard

Geometry Nodes, Houdini SOPs, and Unreal PCG do not share a node catalog. A Blender *Distribute Points on Faces* node is not a Houdini *Scatter* node and is not an Unreal *Surface Sampler*. They sometimes describe related ideas — sample a surface, produce points — and sometimes they do not.

Pairwise converters (`Blender → Houdini`, `Houdini → Unreal`, …) do not scale, and they encode the false assumption that one source node equals one target node.

NodeBridge instead compiles:

```
Native DCC graph
    → frontend / source adapter
    → canonical semantic IR
    → analysis + normalization + rewrite + lowering
    → target backend
    → editable native DCC graph
```

Future hosts (Maya/Bifrost, Substance Designer, Nuke, …) should plug in through the host contract, not by editing every compiler module.

## What NodeBridge is

* A software-independent procedural graph compiler
* A canonical semantic IR for operations, data flow, types, and provenance
* A registry of semantic operations that can grow incrementally
* A host plugin architecture (frontend + backend + capabilities)
* A translation planner that classifies every operation before generation
* Structured fidelity: `EXACT`, `LOWERED`, `APPROXIMATE`, `CUSTOM_CODE`, `BAKED`, `UNSUPPORTED`

## What NodeBridge is not

* A Blender exporter that string-replaces node names
* A collection of pairwise converters
* A requirement that graph topology survives translation
* A live IPC bridge between running applications
* A tool that silently approximates unsupported behavior
* A promise of perfect round-trip equivalence

## Current status (implemented today)

**Version 0.2** implements the many-to-many compiler architecture and a Blender ↔ Houdini vertical slice at the **pure translation / construction-plan** level.

| Layer | Status |
| --- | --- |
| Canonical semantic IR | Implemented |
| Type system | Implemented |
| Semantic operation catalog (narrow) | Implemented |
| Validation + JSON serialization | Implemented |
| Host plugin registry | Implemented |
| Capability model | Implemented |
| Compiler pipeline (validate → normalize → plan → lower → report) | Implemented |
| Blender Geometry Nodes frontend | Implemented for a small subset, fixture/duck-typed trees |
| Blender Geometry Nodes backend | Implemented as construction plans + bpy script text |
| Houdini SOP frontend | Implemented for a small subset, fixture/duck-typed networks |
| Houdini SOP backend | Implemented as construction plans + hou script text + VEX snippets |
| Unreal PCG frontend | Architecture + fixtures; live `unreal` inspection is experimental |
| Unreal PCG backend | Construction plans + experimental UE 5.7 Python text |
| Live `bpy` / `hou` / `unreal` execution | Not run in CI; optional runtime modules use importlib |
| Blender add-on UI | Scaffold only |

The core package imports without Blender, Houdini, or Unreal installed.

**Not implemented today:** live editor integration, a large node catalog, shader/compositor coverage, baking evaluators, Maya/Substance/Nuke hosts, and perfect round-trips.

## Supported hosts

| Host | Graph system | Frontend | Backend | Runtime API |
| --- | --- | --- | --- | --- |
| Blender | Geometry Nodes | Yes (fixtures + optional bpy) | Yes (plan + bpy script) | Optional, Blender only |
| Houdini | SOP / VEX | Yes (fixtures + optional hou) | Yes (plan + hou script) | Optional, Houdini only |
| Unreal Engine 5 | PCG | Yes (fixtures; live inspect limited) | Yes (plan + experimental Python) | Editor-only, UE 5.7+ experimental |

## Supported semantic operations (vertical slice)

The catalog is larger than the well-tested slice. The slice with cross-host mappings is approximately:

* `graph.input` / `graph.output`
* `geometry.primitive`
* `geometry.transform`
* `geometry.join`
* `points.distribute` (surface sampling)
* `random.float` / `random.vector`
* `geometry.instance`
* `geometry.realize_instances`
* `math.*` (add, subtract, multiply, divide, min, max, clamp, map_range)
* `vector.*` (add, subtract, scale, normalize, dot, cross, distance)
* `attribute.read` / `attribute.write`

See [docs/semantic_operations.md](docs/semantic_operations.md) and [docs/compatibility.md](docs/compatibility.md).

## Installation

Requires Python 3.11+.

```bash
python -m pip install -e ".[dev]"
```

## Basic usage

Build IR without any DCC installed:

```python
from nodebridge import GraphBuilder, GraphSystem, DataType, compile_graph, dumps, validate_graph

builder = GraphBuilder(name="example", system=GraphSystem.GEOMETRY)
add = builder.node("math.add")
builder.input(add, "a", DataType.FLOAT, default=1.0)
builder.input(add, "b", DataType.FLOAT, default=2.0)
builder.output(add, "value", DataType.FLOAT)

assert validate_graph(builder.graph).ok
json_text = dumps(builder.graph)

result = compile_graph(builder.graph, "houdini")
print(result.report.format_text())
print(result.native_graph.nodes[0].type)  # attribwrangle for math.add
```

Compile a native Blender fixture toward Houdini:

```python
from nodebridge import compile_native
from nodebridge.hosts.blender import BlenderFrontend

# native_graph is a NativeGraph or dict describing Geometry Nodes
document = BlenderFrontend().extract(native_graph)
result = compile_native(native_graph, "houdini")
```

CLI:

```bash
nodebridge inspect graph.nodebridge.json
nodebridge validate graph.nodebridge.json
nodebridge capabilities houdini
nodebridge plan graph.nodebridge.json --target houdini
nodebridge report graph.nodebridge.json --target unreal
nodebridge translate graph.nodebridge.json --target houdini --output houdini.native.json --script houdini_build.py
nodebridge translate --source blender --target houdini --input scatter.native.json
```

`.nodebridge.json` files are data. Loading them never executes Python, VEX, or Unreal scripts. Generation and execution are explicit stages.

## Architecture

```
Native graph  →  Host frontend  →  Semantic IR  →  Compiler passes
                                                      │
                                                      ▼
Native graph  ←  Host backend   ←  Lowering / plan  ←─┘
```

* **IR** names operations such as `points.distribute`, not `GeometryNodeDistributePointsOnFaces`.
* **Frontends** map native constructs onto those operations and store host types as provenance.
* **Backends** lower operations to native fragments. One IR node may become several target nodes.
* **Fidelity** is always classified. Approximations and gaps are diagnostics, not silent substitutions.

See [docs/architecture.md](docs/architecture.md) and [docs/translation_pipeline.md](docs/translation_pipeline.md).

## Example workflow

1. Author a Geometry Nodes scattering tree in Blender (or describe it as a native fixture).
2. Extract it to NodeBridge IR (`points.distribute` → `random.vector` → `geometry.instance` → `geometry.realize_instances`).
3. Plan translation toward Houdini.
4. Generate a SOP construction plan (Scatter, Attribute Randomize, Copy to Points, Unpack).
5. Optionally emit a `hou` script to rebuild an editable network inside Houdini.
6. Read the translation report for anything that was lowered, approximated, implemented as VEX, or unsupported.

The inverse path (Houdini SOP fixture → IR → Blender Geometry Nodes plan) is implemented for the same subset.

The graphs do not need identical topology. The goal is **procedural semantic equivalence** within documented fidelity, not node-name or wiring identity.

## Limitations

* The operation catalog is a coherent seed, not Geometry Nodes / SOP / PCG coverage.
* Live DCC execution is optional and environment-dependent. CI tests use host-neutral fixtures.
* Unreal PCG Python is experimental (UE 5.7+ `add_node_of_type` / `add_edge`). Pin inspection is incomplete. NodeBridge emits plans and documented script text; it does not pretend unsupported editor APIs exist.
* Nested groups are represented but not fully lowered.
* Field-evaluation differences between applications are recorded, not solved.
* Baking is a classified fallback, not an implemented evaluator.
* The Blender add-on is a UI shell only.

## Roadmap

See [docs/roadmap.md](docs/roadmap.md). Next highest-leverage work: run the Blender ↔ Houdini slice against real `bpy` / `hou` sessions for the scattering subset.

## Tests

```bash
python -m pytest
```

## License

MIT. See [LICENSE](LICENSE).
