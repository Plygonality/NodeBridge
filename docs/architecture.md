# Architecture

NodeBridge is layered so source inspection, semantic representation, and
target generation never collapse into one another.

```
Source Adapter
      ↓
Intermediate Representation
      ↓
Semantic Translation
      ↓
Target Backend
```

The central rule: **NodeBridge translates procedural semantics between
applications. It does not merely translate node names.**

## Layers

### Core (`nodebridge.core`)

Application-agnostic primitives:

* graphs, nodes, sockets, connections
* data types and type compatibility
* semantic operations
* diagnostics and translation status
* provenance / UI metadata
* rewrite-pass protocol

Core code must never import `bpy`, `hou`, or Unreal Python.

### IR (`nodebridge.ir`)

Versioned documents around a graph:

* schema envelope (`nodebridge_version`, `ir_version`, `source`, `graph`)
* JSON serialization and deserialization
* structural validation
* migration hooks

Serialization is a separate concern from the in-memory model. Core types
do not know JSON field names.

### Adapters (`nodebridge.adapters`)

A source adapter inspects a host graph and emits IR. Blender is the first
adapter, not the identity of the project. Future adapters (Houdini, Maya,
MaterialX, USD) should plug in at this layer.

Milestone 1 ships the contract and a Blender placeholder. Extraction is
Milestone 2.

### Translators (`nodebridge.translators`)

A registry maps `(operation, target)` to a handler. Handlers return graph
*fragments* so one IR operation may become many target nodes.

```python
@register_translation(source="geometry.transform", target="houdini")
def translate_transform(node):
    ...
```

Adding an operation must not require editing a central switch statement.

### Backends (`nodebridge.backends`)

A backend realizes fragments in a host system. The backend API returns
fragments, not a single node. Houdini may emit several SOPs plus a
wrangle. Unreal may choose PCG, Material, Geometry Script, or Blueprint
based on capabilities.

### Export and CLI

Export writes IR JSON today and target scripts later. The CLI inspects,
validates, and reports; `translate` is reserved.

## Why an IR

Direct `Blender Node → Houdini Node` mapping fails as soon as:

* one source node needs several target nodes
* two applications share intent but not UI
* a field in Blender is an attribute in Houdini
* a shader graph and a geometry graph need different Unreal systems

The IR names *operations* (`geometry.transform`, `math.add`) rather than
widgets (`GeometryNodeTransform`, `xform`).

## Metadata versus semantics

Each node stores:

* **operation** — what it means
* **sockets / parameters** — data flow and constants
* **provenance** — where it came from (`original_type`, `original_id`)
* **UI hints** — position, frames, mute, labels
* **source mapping** — source id → IR id → generated target ids

Translation decisions use operations, types, and data flow. UI hints are
preserved for reconstruction and debugging only.

## Rewrite pipeline

```
Raw IR
  → Normalization
  → Semantic simplification
  → Target-aware rewriting
  → Backend generation
```

`PassPipeline` is in place. Concrete passes (constant folding, dead-node
elimination, implicit conversions, fusion, lowering) are later work.

## Isolation rules

| Package | May import host SDKs? |
| --- | --- |
| `nodebridge.core` | No |
| `nodebridge.ir` | No |
| `nodebridge.translators` | No |
| `nodebridge.cli` | No |
| `nodebridge.adapters.blender` | Yes, `bpy` only, when implemented |
| `nodebridge.backends.houdini` | Yes, `hou` only, when implemented |
| `nodebridge.backends.unreal` | Yes, Unreal Python only, when implemented |
| `blender_addon` | Yes, `bpy`, UI only |

Tests in `tests/test_coupling.py` enforce the Milestone 1 side of this
rule: the installed package currently imports none of those SDKs.

## One-to-many translation

`GraphFragment` is the backend return type:

* zero or more `TargetNodeSpec`
* connections between those specs
* a `TranslationStatus`
* diagnostics
* a `SourceMapping`

Backends must not assume `len(fragment.nodes) == 1`.

## Future hosts

The adapter/backend split is deliberately host-agnostic so later work can
add Maya, Substance Designer, Unity, Godot, USD, or MaterialX without
rewriting the IR. Blender is a source, not the project identity.

Live IPC (Blender ↔ NodeBridge service ↔ Houdini/Unreal) is explicitly
out of scope for the prototype.
