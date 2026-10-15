# NodeBridge

NodeBridge is a cross-DCC procedural compiler.

Build a procedural system in Blender. NodeBridge reads the graph, translates its procedural meaning into an intermediate representation, and generates code that constructs a native system in another DCC. The result is an editable Houdini network or an Unreal asset, not a baked export.

```
Blender Geometry Nodes
        |
        v
    NodeBridge
        |
        +--> Houdini Python  -->  paste into the Python Source Editor  -->  SOP network
        |
        +--> Unreal Editor Python  -->  run in the editor  -->  PCG graph or material
```

NodeBridge translates procedural meaning. Source nodes are syntax. The semantic IR is the meaning. Target backends choose the implementation.

It does not promise pixel-identical or vertex-identical output. Many translations are semantically equivalent: same intention, different samples, noise, or topology. The report says which.

## Confidence

| Class | Meaning |
| --- | --- |
| Exact | The target should reproduce the source behavior very closely. |
| Equivalent | The intention is preserved. Implementation details or random samples may differ. |
| Approximate | The target can produce a similar result, not the full source behavior. |
| Unsupported | No reliable target implementation exists. The operation is reported and is not dropped silently. |

## Workflow

1. Build the system in Blender Geometry Nodes, the Shader Editor, or the Compositor.
2. Open the sidebar and select the NodeBridge tab.
3. Choose Houdini or Unreal Engine 5.
4. Click Analyze. The panel counts nodes, operations, and each confidence class.
5. Click Generate Code.
6. Click Copy Code.
7. Paste into the Houdini Python Source Editor, or run the script in Unreal Editor with the Python Editor Script plugin enabled.
8. The target builds a native graph. Edit that graph with the target's own tools.

```
+------------------------------------+
| NodeBridge                         |
+------------------------------------+
| Source                             |
| Geometry Nodes                     |
| BuildingGenerator                  |
|                                    |
| Target                             |
| [ Houdini ]                        |
|                                    |
| [ Analyze Graph ]                  |
|                                    |
| 47 Nodes                           |
| 24 Operations                      |
|                                    |
| Exact: 17                          |
| Equivalent: 5                      |
| Approximate: 1                     |
| Unsupported: 1                     |
|                                    |
| [ Generate Code ]                  |
|                                    |
| import hou                         |
| ...                                |
|                                    |
| [ Copy Code ]  [ Save .py ]        |
+------------------------------------+
```

The panel is the Blender sidebar in the 3D View and the node editor. The preview above is the layout, not a captured screenshot. Generated scripts also land in the Text Editor as `NodeBridge.py` and `NodeBridge Report.txt`.

Advanced options: translation strictness, comments, source names, layout, metadata, deterministic randomness, and debug output.

## Install

NodeBridge targets Blender 4.2 or newer. The compiler itself is pure Python 3.11 and does not import `bpy` until Blender registers the add-on.

**Blender**

```bash
python3 scripts/package_addon.py
```

In Blender: Edit > Preferences > Add-ons > Install from Disk, and choose `dist/nodebridge.zip`. Enable NodeBridge. The zip's top folder is `nodebridge` and `bl_info` lives in `nodebridge/__init__.py`.

**Tests and the command line**

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
nodebridge compile --example scatter --target houdini --output scatter.py --report scatter.txt
```

`--example` accepts `scatter`, `building`, `shader`, and `compositor`. `--input` accepts graph IR JSON.

## What a Houdini script does

The scatter example creates a new Geometry container under `/obj`. It does not modify other nodes. Children are destroyed only on that new container, which removes the default File SOP so the network is procedural.

The script then:

- promotes Density and Source Object
- object-merges the source surface
- builds the instance with a Box SOP
- scatters with `scatter::2.0` in density mode
- writes scale and rotation with an Attribute Wrangle
- copies the box onto the points
- unpacks the instances
- sets the display and render flags on a null named `OUT`

Paste it into the Houdini Python Source Editor and run it. Assign `source_object` to the SOP that should be scattered on. Scatter point positions follow Houdini's distribution, not Blender's, even when the seed matches. The report says so.

See `examples/scatter/houdini.py` and `examples/scatter/houdini_report.txt`.

## What an Unreal script does

Geometry graphs create a PCG asset with `PCGGraphFactory`, `add_node_of_type`, and `EditorAssetLibrary.save_asset`. A scatter becomes a Surface Sampler and a Static Mesh Spawner. Node classes are resolved with `getattr`. If a class is missing, the script logs the error and continues. It does not call an invented API.

Shader graphs create a Material and material expressions. Compositor color operations can fall back to an emissive material. Glare and masks are unsupported. The script does not spawn a Post Process Volume.

Run it in Unreal Editor with the Python Editor Script plugin. PCG graphs also need the PCG plugin. Assign the spawner mesh yourself. There is no checked Python API in this backend that builds a mesh from a Blender primitive.

## Examples

| Example | Blender source | Look at |
| --- | --- | --- |
| Procedural scatter | `examples/scatter` | Surface, scatter, random scale and rotation, instance |
| Procedural building | `examples/building` | Grid, extrude, floors, facade instances, exposed Height and Density |
| Procedural shader | `examples/shader` | Noise, color ramp, roughness, bump, Principled BSDF |
| Compositor grade | `examples/compositor` | Render layer, glare, color, vignette, composite |

Each folder contains `graph.json`, a Houdini script, an Unreal script, and both reports.

## Current support

The full default matrix and the Blender node list are in [docs/support.md](docs/support.md).

Geometry Nodes coverage is the working vertical slice: primitives, scatter, instances, transforms, math, noise, curves, extrude, booleans, raycast, proximity, and node groups. Houdini builds SOP networks from that set. Unreal builds a PCG graph for scatter and instancing. Extrude, subdivide, and join are parsed and then reported unsupported for PCG, because this backend does not have a checked node for them.

Shader translation writes a Houdini Material Builder or an Unreal material for Principled parameters, noise, and a recorded color ramp. Several shader nodes remain comments. That is approximate, not a full material match.

Compositor translation builds a Houdini COP2 network when the node type exists at runtime. Glare and vignette masks are unsupported. Unreal does not get a compositor graph.

Simulation zones and repeat zones are unsupported on both targets.

## Architecture

```
Blender node tree
    -> parser
    -> graph IR
    -> dependency analysis
    -> semantic IR
    -> normalization / rewrite
    -> capability classification
    -> Houdini or Unreal backend
    -> generated Python
    -> native graph
```

Details, including coordinates, units, and the deterministic hash, are in [docs/architecture.md](docs/architecture.md).

Future hosts (Maya, Bifrost, Substance Designer, Godot, Cinema 4D, Nuke) would be new frontends or backends. The IR does not need to change for a new target to exist.

## Roadmap

1. More Geometry Nodes patterns as rewrite rules, including simulation where a real target exists.
2. Wire shader ramps, roughness, and normals as real VOP and material-expression graphs instead of comments.
3. PCG nodes for extrude, boolean, and attribute math once their Python settings classes are confirmed.
4. A Houdini frontend and an Unreal frontend, so translation can run in the other direction.
5. Optional `TranslationFallbackProvider` for comments. It stays off. The compiler does not require a model API.

## Limitations

- These tests parse fixtures and check the generated Python. They do not launch Blender, Houdini, or Unreal.
- Equivalent and approximate results are not numerically identical.
- Deterministic `nb_rand` is used where NodeBridge emits the snippet. Native scatter and the PCG Surface Sampler keep their own random series.
- Houdini `booleanop` menu values are commented as version-sensitive.
- Unreal primitive geometry is not constructed. The PCG input is the surface, and the spawner mesh is a user assignment.
- Exposed Geometry Nodes parameters become Houdini spare parameters. The Unreal PCG script can bake a numeric default it knows how to set, such as scatter density on `points_per_squared_meter`. It does not create a PCG user parameter for controls such as Height.
- The add-on UI is implemented against Blender's Python API and has not been clicked inside Blender in this environment.

## License

MIT. See [LICENSE](LICENSE).
