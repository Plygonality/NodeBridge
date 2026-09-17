# Translation pipeline

```
extract
    ↓
validate IR
    ↓
normalize
    ↓
analyze target capabilities
    ↓
construct translation plan
    ↓
rewrite / lower
    ↓
generate (optional, explicit)
    ↓
report
```

Implemented by `nodebridge.compiler.pipeline.compile_graph` and
`compile_native`.

## Stages

### Extract

A host frontend maps a `NativeGraph` (or a duck-typed DCC tree) onto IR.
Host type names become provenance.

### Validate

Structural checks only. See [intermediate_representation.md](intermediate_representation.md).

### Normalize

Host-independent IR rewrites:

* alias canonicalization (`surface_sample` → `points.distribute`)
* many-to-one clamp fusion (`math.max` + `math.min` → `math.clamp`)
* constant folding of unused math/vector nodes
* dead-node elimination when a `graph.output` is present

### Plan

For each IR node the compiler asks the **target host**:

* Can you implement this operation?
* How? (exact node, fragment, approximation, custom code, bake, unsupported)

The plan is deterministic for a given graph and host.

### Lower

Each planned operation becomes a native fragment. Fragments are wired
using IR data flow, not by assuming 1:1 topology.

### Generate

Optional. Emits host-script **text** (`bpy`, `hou`, Unreal Python, VEX).
Never runs as a side effect of loading IR.

### Report

See [translation_fidelity.md](translation_fidelity.md).

## CLI

```bash
nodebridge plan graph.nodebridge.json --target houdini
nodebridge report graph.nodebridge.json --target unreal --json
nodebridge translate scatter.native.json --source blender --target houdini
```
