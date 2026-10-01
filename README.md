# NodeBridge

NodeBridge is a **cross-DCC procedural compiler**.

Build a procedural system in Blender. NodeBridge reads the node tree, translates its procedural meaning into an intermediate representation, and generates code that constructs a native procedural system in another DCC.

```
Blender node tree
        │
        ▼
   Graph IR          structure: nodes, sockets, links, groups
        │
        ▼
  Semantic IR        meaning: Scatter, Instance, Noise, Transform
        │
        ▼
 Normalize / rewrite
        │
        ▼
 Capability resolver
        │
        ├── Houdini Python  →  native SOP / material / COP network
        └── Unreal Editor Python  →  PCG graph or Material
```

NodeBridge translates procedural meaning. Source node names are syntax. Target backends choose the implementation.

It does not promise pixel-identical or vertex-identical results. The expected result is a **semantically equivalent procedural system** that you can keep editing in the target DCC.

## Confidence

Every operation is classified before code is generated.

| Class | Meaning |
| --- | --- |
| **Exact** | The target should reproduce the source behavior to a very high degree. |
| **Equivalent** | The procedural intention is preserved. Topology, controls, or random samples may differ. |
| **Approximate** | The target can produce a similar result, but not the full source behavior. |
| **Unsupported** | No reliable target implementation exists. The operation is reported and left as a comment. It is not dropped silently. |

Random samplers are never classified as exact. Houdini Scatter, Unreal Surface Sampler, and Blender Distribute Points on Faces do not share a random sequence. Where NodeBridge owns the random function, it uses `random(seed, element_id)` and emits the same hash in Python and as a VEX reference. That hash is not Blender's random.

## Workflow

1. Build a Geometry Nodes, Shader, or Compositor tree in Blender.
2. Open the sidebar and select the **NodeBridge** tab.
3. Choose **Houdini** or **Unreal Engine 5**.
4. Click **Analyze Graph**.
5. Read the coverage counts and the warnings.
6. Click **Generate Code**.
7. Click **Copy Code**.
8. Paste into the Houdini Python Source Editor, or run the script in the Unreal Editor Python environment.
9. Edit the generated network as a normal native graph.

The script builds nodes, parameters, and connections. It does not import baked geometry.

```
┌────────────────────────────────────┐
│ NodeBridge                         │
├────────────────────────────────────┤
│ Source                             │
│ Geometry Nodes                     │
│ BuildingGenerator                  │
│                                    │
│ Target                             │
│ [ Houdini ▼ ]                      │
│                                    │
│ [ Analyze Graph ]                  │
│                                    │
│ 47 Nodes                           │
│ 24 Operations                      │
│                                    │
│ ✓ 17 Exact                         │
│ ≈ 5 Equivalent                     │
│ ~ 1 Approximate                    │
│ ✕ 1 Unsupported                    │
│                                    │
│ [ Generate Code ]                  │
│                                    │
│  import hou                        │
│  ...                               │
│                                    │
│ [ Copy Code ] [ Save Script ]      │
└────────────────────────────────────┘
```

Screenshots of a live Blender session are not included in this repository. The panel layout above is the UI the add-on draws. Generated scripts for the example graphs are in `examples/`.

## Install

Python 3.11 or newer.

```bash
python -m pip install -e ".[dev]"
```

### Blender add-on

The installable add-on is the `nodebridge` package:

```bash
cd src && zip -r ../nodebridge.zip nodebridge
```

In Blender: Edit → Preferences → Add-ons → Install → select `nodebridge.zip` → enable **NodeBridge**.

The panel is in the node editor sidebar (N) and in the 3D viewport sidebar, category **NodeBridge**. Blender 4.2 or newer.

From a git checkout you can instead enable `blender_addon/nodebridge`. That loader puts `src/` on the path and registers the same add-on.

No OpenAI, Anthropic, Gemini, or local LLM key is required. Translation is a compiler.

## What the first slice generates

### Houdini

Paste the script into the Python Source Editor and run it. For Geometry Nodes the script:

- creates a new Geometry object and does not modify other scene nodes
- creates SOP nodes with readable names
- sets parameters, including vector tuples
- connects inputs
- sets the display and render flags
- calls `moveToGoodPosition()` and `layoutChildren()`
- promotes numeric group inputs to spare parameters on the geometry container
- writes sticky-note text for approximate translations
- raises if a named node type does not exist, instead of skipping it

Shader graphs become a Material Builder under `/mat` using MaterialX node types. Compositor graphs target a COP2 `/img` network. Glare is an approximate blur. A vignette mask is unsupported and stays in the report.

Coordinates and units are converted in one place: Blender Z-up to Houdini Y-up (`(x, y, z) → (x, z, -y)`), and rotation sockets from radians to degrees.

### Unreal Engine 5

Geometry graphs emit Unreal Editor Python that creates a PCG asset with `PCGGraphFactory` and `add_node_of_type` when that editor API exists. If the running editor does not expose those calls, the script raises. It does not invent a private API.

Shader graphs emit `MaterialEditingLibrary` code that creates a Material asset and expression nodes. Compositor graphs are reported as unsupported. Unreal Python does not construct a Blender-style compositor, and NodeBridge does not pretend a post-process graph was built.

## Current support

This is a real subset, not a catalog of every Blender node. Unknown nodes become `Unsupported` and appear in the report.

### Geometry Nodes → Houdini SOPs

| Operation | Confidence |
| --- | --- |
| Group input / output, mesh primitives, join, transform, delete, attribute write | Exact |
| Scatter, instance, realize instances, extrude, resample curve, ray, proximity, switch, material assign, math, noise, random, rotate/scale instances | Equivalent |
| Subdivide, curve to mesh, attribute read | Approximate |
| Simulation zones and anything not listed | Unsupported |

### Geometry Nodes → Unreal PCG

| Operation | Confidence |
| --- | --- |
| Graph input / output, join, transform | Exact |
| Surface scatter, random float | Equivalent |
| Instance / static mesh spawner, realize, primitive, delete, attribute read/write, random vector | Approximate |
| Extrude, subdivide, curves, raycast, proximity, math, noise, simulation | Unsupported |

### Shaders

Principled BSDF, noise, mix, math, image texture, and material output lower to a Houdini MaterialX builder (equivalent or approximate) and to Unreal material expressions (equivalent or approximate). Bump and color ramps are approximate. The noise pattern will not match Blender.

### Compositor

Color correction, blur, and mix lower to COP2 nodes (equivalent). Glare is approximate. Masks and the whole compositor are unsupported in Unreal.

A machine-readable view is `nodebridge.hosts` plus `nodebridge.translation.report.public_confidence`.

## Examples

| Example | Path |
| --- | --- |
| Scatter: primitive, scatter, instance, realize | `examples/scatter/` |
| Building: grid, extrude, subdivide, material | `examples/building/` |
| Shader: noise, ramp, roughness, normal, Principled | `examples/shaders/` |
| Compositor: render layer, glare, color, mask, composite | `examples/compositor/` |

Each directory contains a Houdini script, an Unreal script where a backend exists, and the translation report.

## Library use without Blender

```python
from nodebridge import compile_graph, dumps, validate_graph
from nodebridge.core.graph import GraphBuilder, GraphSystem
from nodebridge.core.types import DataType

builder = GraphBuilder(name="example", system=GraphSystem.GEOMETRY)
add = builder.node("math.add")
builder.input(add, "a", DataType.FLOAT, default=1.0)
builder.input(add, "b", DataType.FLOAT, default=2.0)
builder.output(add, "value", DataType.FLOAT)

assert validate_graph(builder.graph).ok
result = compile_graph(builder.graph, "houdini", generate=True)
print(result.report.format_text())
print(result.generated_code)
```

`dumps(builder.graph)` writes JSON. Loading that JSON does not execute Houdini or Unreal code.

## Architecture

```
SourceFrontend (BlenderFrontend)
        │  bpy or a duck-typed node tree
        ▼
NodeTree  GraphNode  GraphSocket  GraphEdge     graph IR
        │  dependency order, cycles, dead nodes
        ▼
semanticize → IRGraph of operations             semantic IR
        │  reroute collapse, clamp fusion,
        │  spatial-noise mask, instance transform fusion
        ▼
TargetBackend
        ├── HoudiniBackend.generate()
        └── UnrealBackend.generate()
```

Adding Maya, Bifrost, Substance Designer, Godot, Cinema 4D, or Nuke means a new frontend or backend and new recipes. It does not mean a new pairwise converter.

`TranslationFallbackProvider` is the seam for a future optional assistant. The default is `fallback = None`.

Details: [docs/architecture.md](docs/architecture.md).

## Tests

```bash
python -m pytest
```

Compiler tests run without Blender, Houdini, or Unreal. They parse generated scripts with the Python AST and check classification, ordering, units, coordinates, and the deterministic hash. They do not launch those applications.

## Known limitations

- Live Houdini and Unreal sessions are not part of CI. Generated scripts target documented `hou` and Unreal Editor APIs and check node types at runtime.
- Scatter density becomes an approximate Houdini point count (`npts`). The samples will not match.
- Nested groups are parsed and stored as subgraphs. Houdini emits a subnet for a group node; the subnet's internal network is not fully rebuilt in every case.
- Unreal PCG pin labels are version-sensitive. `add_edge` is only called after `add_node_of_type` exists.
- Field evaluation, simulation zones, and repeat zones are unsupported.
- Compositor → Unreal is an explicit refusal, not a partial post-process export.
- MaterialX and COP2 node types must exist in the target Houdini build. A missing type raises.

## Roadmap

1. Run the scatter script inside a real Houdini session and tighten SOP parameter names against that build.
2. Verify PCG pin labels against a specific Unreal editor version.
3. Rebuild nested groups as real subnet contents and Houdini spare-parameter expressions.
4. More curve, boolean, and attribute operations, each with a confidence label and a test.
5. A Houdini or Unreal frontend so the compiler can run in the other direction.

## License

MIT. See [LICENSE](LICENSE).
