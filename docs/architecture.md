# Architecture

NodeBridge is a cross-DCC procedural compiler. It translates procedural meaning. Source node names are syntax. The semantic IR is the meaning. A target backend chooses a native implementation.

```
Blender node tree
        |
        v
  Blender parser          frontend/blender/parser.py
        |
        v
     Graph IR             ir/graph.py
        |
        v
 Dependency analysis      compiler/analyzer.py
        |
        v
    Semantic IR           ir/semantic.py
        |
        v
 Normalization            compiler/normalize.py
 Graph rewrite rules      compiler/rewrite.py
        |
        v
 Capability resolver      translation/registry.py
                          compiler/capabilities.py
        |
        v
   Target backend         backend/houdini, backend/unreal
        |
        v
  Generated Python
        |
        v
 Native DCC graph         SOP network, material, COP network, PCG graph, Unreal material
```

## Two representations

Graph IR keeps nodes, sockets, links, defaults, nested groups, and the source node type as metadata. Editor coordinates are stored and then ignored by ordering.

Semantic IR names operations such as `ScatterOperation` data on an `Operation` whose `kind` is `scatter`. The Blender node `GeometryNodeDistributePointsOnFaces` is a source reference, not the translation key.

Several source nodes can become one semantic operation. `Noise -> Map Range -> Compare` can become `spatial_noise_mask` when the chain has no other consumers. Rewrite rules live in `compiler/rewrite.py` and are the place to add the next pattern.

## What generates code

Translators register themselves:

```python
@translator(OperationKind.SCATTER, "houdini", confidence=Confidence.EQUIVALENT, ...)
def translate_scatter(operation, build):
    ...
```

There is no central `if node.type` cascade. `TranslationFallbackProvider` exists for a future optional comment source. The default is `None`. Compilation does not call an LLM or a network API.

## Confidence

| Class | Meaning |
| --- | --- |
| Exact | The target should follow the source very closely. |
| Equivalent | The procedural intention is preserved. Samples, topology, or noise can differ. |
| Approximate | A similar result, not the full source behavior. |
| Unsupported | No reliable target implementation. The operation stays in the report and in the script as a comment or passthrough. |

The capability matrix is default translator metadata. A translator may downgrade one node. The translation report for that graph is the authority.

## Shared conversions

Coordinate conversion, unit conversion, and the deterministic hash live in `nodebridge.common`. Backends call those functions. They do not each invent an axis swap.

Canonical space is right-handed, X right, Y forward, Z up, meters. Houdini is Y-up: `(x, y, z)` becomes `(x, z, -y)`. Unreal locations are left-handed X-forward Z-up centimeters: `(y, x, z) * 100`. A random Euler range uses `convert_euler_axes`, which keeps a full turn as a full turn. A single orientation still uses `convert_euler`.

`nb_rand(seed, element_id)` is a signed 32-bit hash. It is emitted into VEX and copied into Unreal Python when NodeBridge owns the random sequence. Native Scatter and PCG Surface Sampler stay equivalent, because those DCCs own the sample positions.

## Adding a target

Implement a backend with `supports`, `classify`, and `generate`. Register translators for the semantic operations it can build. Leave the parser and the IR alone. Maya, Bifrost, Substance Designer, Godot, Cinema 4D, and Nuke would be new backends, not a new compiler.
