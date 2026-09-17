# Architecture

NodeBridge is a compiler for procedural graphs. Source inspection, semantic
representation, and target generation never collapse into one another.

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

The central rule: **NodeBridge translates procedural semantics between
applications. It does not merely translate node names.**

It is not a collection of pairwise converters. Adding Maya, Substance, or
Nuke should mean implementing the host contract, not editing every existing
host and not adding `if host == ...` branches to the compiler.

## Layers

### Core (`nodebridge.core`)

Application-agnostic primitives:

* graphs, nodes, sockets, connections
* data types and type compatibility
* semantic operations and their schemas
* diagnostics and translation fidelity
* provenance / UI metadata
* rewrite-pass protocol

Core code must never import `bpy`, `hou`, or Unreal Python.

### IR (`nodebridge.ir`)

Versioned documents around a graph:

* schema envelope (`nodebridge_version`, `ir_version`, `source`, `graph`)
* JSON serialization and deserialization
* structural validation
* migration hooks

Serialization is a separate concern from the in-memory model. Loading a
`.nodebridge.json` file never executes embedded code.

### Compiler (`nodebridge.compiler`)

```
validate → normalize → plan → lower → generate → report
```

* **normalize** — alias canonicalization, clamp fusion, constant folding
* **plan** — ask the target host how each operation will be realized
* **lower** — expand one semantic operation into a native fragment
* **report** — classify every operation; no invented compatibility %

### Hosts (`nodebridge.hosts`)

Each DCC is a plugin with:

* id, display name, versions, graph systems
* capability declaration
* frontend (native → IR)
* backend (IR → native construction plan + optional script text)
* semantic mappings and lowering recipes

Blender is a host, not the identity of the project. Houdini and Unreal
are peer hosts, not terminal export targets.

### Compatibility shims

`nodebridge.adapters` and `nodebridge.backends` re-export the host
frontends/backends so Milestone 1 imports (`BlenderExtractor`,
`HoudiniBackend`, `UnrealBackend`) keep working.

## Why an IR

Direct `Blender Node → Houdini Node` mapping fails as soon as:

* one source node needs several target nodes
* several source nodes normalize into one semantic operation
* two applications share intent but not UI
* a field in Blender is an attribute in Houdini
* a shader graph and a geometry graph need different Unreal systems

The IR names *operations* (`geometry.transform`, `points.distribute`)
rather than widgets (`GeometryNodeTransform`, `scatter`).

## One-to-many and many-to-one

Lowering recipes return **fragments**:

* zero or more native nodes
* connections inside the fragment
* a fidelity classification
* optional generated host code (VEX, Python)

Example: `geometry.realize_instances` on Houdini becomes Unpack → Convert
(`LOWERED`). `math.max` followed by `math.min` normalizes to `math.clamp`
(many-to-one) before any host is consulted.

## Metadata versus semantics

Each node stores:

* **operation** — what it means
* **sockets / parameters** — data flow and constants
* **provenance** — where it came from (`original_type`, `original_id`)
* **UI hints** — position, frames, mute, labels
* **history** — translation events for round-trip diagnostics

Translation decisions use operations, types, and data flow. Provenance
must never be used to fake equivalent behavior.

## Isolation rules

| Package | May import host SDKs? |
| --- | --- |
| `nodebridge.core` | No |
| `nodebridge.ir` | No |
| `nodebridge.compiler` | No |
| `nodebridge.cli` | No |
| `nodebridge.translators` | No |
| `nodebridge.hosts.*.runtime` | Yes, via importlib, optional |
| `blender_addon` | Yes, `bpy`, UI only |

Static `import bpy` / `import hou` / `import unreal` are forbidden
everywhere so `import nodebridge` works in ordinary Python.

## Safety

Generated Python, VEX, and Unreal scripts are **not** the IR. They are
emitted by an explicit `generate` stage. Opening a `.nodebridge.json`
file must not run them.
