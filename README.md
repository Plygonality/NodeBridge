# NodeBridge

NodeBridge is an extensible Python framework for translating procedural node
systems between digital content creation tools and game engines.

It inspects a source graph, converts it into a normalized Intermediate
Representation (IR), analyses that representation, and generates a native
procedural system in a target application.

**NodeBridge translates procedural semantics between applications. It does not
merely translate node names.**

```
Blender
   │
   ▼
Source Adapter (bpy)
   │
   ▼
Normalized Intermediate Representation
   │
   ├───────────────┐
   ▼               ▼
Houdini Backend    Unreal Engine Backend
   │               │
   ▼               ▼
Native SOP graph   Native UE5 system
```

## What NodeBridge is

* A software-independent procedural graph translation system
* A strongly structured IR for operations, data flow, types, and metadata
* A registry of semantic operations that can grow incrementally
* A place to classify translation quality instead of guessing silently
* A foundation for Houdini, Unreal Engine 5, and later additional hosts

## What NodeBridge is not

* A Blender exporter that string-replaces node names
* A one-to-one node lookup table
* A requirement that every Blender node has an identical counterpart
* A live IPC bridge (that is a later milestone)
* A tool that silently approximates unsupported behavior

## Current status

**Milestone 1 — Core IR** is implemented.

| Layer | Status |
| --- | --- |
| IR data model | Implemented |
| Type system | Implemented |
| Validation | Implemented |
| JSON serialization | Implemented |
| Diagnostics / reports | Implemented |
| Translation registry | Implemented (no mappings yet) |
| Blender extraction | Not started (Milestone 2) |
| Houdini generation | Not started (Milestone 3) |
| Unreal generation | Not started (Milestone 7) |
| Blender add-on UI | Scaffold only (Milestone 6) |

The core package imports without Blender, Houdini, or Unreal installed.

## Current supported applications

| Role | Application | Status |
| --- | --- | --- |
| Source | Blender | Planned (adapter contract only) |
| Target | SideFX Houdini | Planned (backend contract only) |
| Target | Unreal Engine 5 | Planned (backend contract only) |

## Current supported graph systems

| System | Extract | Translate |
| --- | --- | --- |
| Geometry Nodes | Milestone 2 | Milestone 3 (Houdini SOP) |
| Shader Nodes | Later | Milestone 7 candidate |
| Compositor Nodes | Later | Later |

## Installation

Requires Python 3.11+.

```bash
python -m pip install -e ".[dev]"
```

## Basic usage

Milestone 1 works with IR documents, not live Blender trees.

```python
from nodebridge import GraphBuilder, GraphSystem, DataType, dumps, loads, validate_graph

builder = GraphBuilder(name="example", system=GraphSystem.GEOMETRY)
add = builder.node("math.add")
builder.input(add, "a", DataType.FLOAT, default=1.0)
builder.input(add, "b", DataType.FLOAT, default=2.0)
builder.output(add, "value", DataType.FLOAT)

result = validate_graph(builder.graph)
assert result.ok

json_text = dumps(builder.graph)
restored = loads(json_text).graph
```

CLI:

```bash
nodebridge inspect graph.nodebridge.json
nodebridge validate graph.nodebridge.json
nodebridge report graph.nodebridge.json --target houdini
```

`nodebridge translate` is reserved for Milestone 3.

## Architecture

Layers are strictly separated:

```
Source Adapter → IR → Semantic Translation → Target Backend
```

* **Adapters** inspect a host graph and emit IR. Only adapters may import `bpy`.
* **IR** stores operations, sockets, connections, types, and provenance.
* **Translators** map semantic operations to backend fragments via a registry.
* **Backends** generate native graphs. Only backends may import `hou` or Unreal Python.

See [docs/architecture.md](docs/architecture.md) and
[docs/intermediate_representation.md](docs/intermediate_representation.md).

## Example workflow (target state)

1. Author a Geometry Nodes tree in Blender.
2. Extract it to `graph.nodebridge.json`.
3. Analyse compatibility for Houdini.
4. Generate a Houdini Python script.
5. Run the script inside Houdini to rebuild an editable SOP network.
6. Read the translation report for anything that was not exact.

Today, steps 2–4 can be exercised with hand-built IR fixtures.

## Compatibility

See [docs/compatibility.md](docs/compatibility.md). Coverage is intentionally
narrow. The catalog starts with a small set of semantic operations so the IR
can stay coherent.

## Limitations

* No Blender extraction yet
* No Houdini or Unreal code generation yet
* Operation catalog is a seed, not a complete Geometry Nodes coverage list
* Rewrite passes exist as a pipeline only (identity / test doubles)
* Nested groups are represented, but group semantics are not yet lowered
* Field evaluation differences between applications are recorded, not solved

## Roadmap

The full milestone plan is in [docs/roadmap.md](docs/roadmap.md).

1. Core IR — **this release**
2. Blender Geometry Nodes extraction (small subset)
3. Houdini SOP prototype
4. Translation diagnostics
5. More Geometry Nodes
6. Blender add-on
7. Unreal prototype
8. Advanced semantic translation

## Tests

```bash
python -m pytest
```

## License

MIT. See [LICENSE](LICENSE).
