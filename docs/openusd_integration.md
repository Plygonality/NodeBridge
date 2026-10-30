# OpenUSD integration

NodeBridge 0.4 publishes an evaluated USD scene next to the procedural data it already knows how to serialize. The scene and the generated native network are separate deliverables.

| Deliverable | What it is | What it is not |
| --- | --- | --- |
| USD scene | Meshes, transforms, hierarchy, and bindings Blender's exporter wrote | The Geometry Nodes tree, a SOP network, or a PCG graph |
| Graph IR and Semantic IR | The source structure and the operations NodeBridge lifted | USD prims |
| Houdini or Unreal script | A native procedural system you can keep editing | An importer for the USD file |

Translation confidence stays on the report: EXACT, EQUIVALENT, APPROXIMATE, UNSUPPORTED. A stage that opens does not move an operation to EXACT.

## Dependencies

| Mode | Needs |
| --- | --- |
| `nodebridge analyze`, `generate`, `capabilities` | Python 3.11+. No Blender, no pxr. |
| Basic bundle from Blender | Blender 4.2+ with `bpy.ops.wm.usd_export`. No PyPI pxr. |
| `nodebridge usd validate` on a bundle directory | Python only. |
| Inspect, compare, layered `scene.usda`, custom data | `pxr`. `python -m pip install "nodebridge[usd]"` installs `usd-core>=26.11`. |

`usd-core` 26.11 was imported in this project's CPython 3.12 environment. PyPI publishes manylinux wheels for CPython 3.11 through 3.14. If a platform has no wheel, use the `pxr` module that ships with Houdini, Blender, or another USD build, on `PYTHONPATH`. The Blender add-on zip does not contain the USD SDK.

`pxr` is imported inside `interchange/usd/` functions. Importing `nodebridge` does not import it. If a command needs it and the import fails, the CLI prints an install hint and exits 1. It does not traceback.

## Blender workflow

1. Open `examples/nodebridge_examples.blend`.
2. Select the **Building** object. Its Geometry Nodes modifier is the generator.
3. Open the sidebar (N) and the **NodeBridge** tab, in the 3D Viewport or the Geometry Node editor.
4. Set **Target** to **Houdini**. USD is not in that list.
5. Click **Analyze Graph**, then **Generate Code** if you want to read the script first. Export also generates when **Include Native Target Script** is on.
6. In **OpenUSD**, leave **Scope** on **Generator Object**. Turn on **Replace Existing Bundle** only when the destination is already a NodeBridge bundle. **Layered USD** stays disabled until pxr imports in Blender's Python.
7. Click **Export USD Bundle** and choose a path ending in `.nodebridge`, for example `Building.nodebridge`.

The operator calls the current Blender's USD exporter. Property names are read from that operator's RNA, so Blender 4.2, 4.5, and 5.x are not given a single hard-coded argument list. The export writes a temporary `.usdc`, then the bundle is swapped into place. Selection, the active object, mode, and viewport visibility are restored if the export fails.

Scope **Generator Object** exports that object only. Other objects the graph refers to can be missing from the USD file. **Visible Scene** can include objects that are not part of the generator. Instancing, shader networks, custom attributes, and animation may be baked, partial, or omitted. The manifest says so.

**UsdPreviewSurface (limited)** is passed through only when this Blender version has `generate_preview_surface`. It is Blender's preview fallback, not a NodeBridge shader translation.

## CLI

Packaging does not evaluate Geometry Nodes. Pass a USD file that already exists.

The checked-in `examples/openusd/cube.usda` is a one-cube stage for the commands below. It is not a Blender export of the building.

```bash
nodebridge analyze examples/building/building.graph.json --target houdini --semantic > /tmp/building.semantic.json
nodebridge generate examples/building/building.graph.json --target houdini -o /tmp/building_houdini.py
nodebridge analyze examples/building/building.graph.json --target houdini --json > /tmp/building.report.json

nodebridge usd package \
  --scene examples/openusd/cube.usda \
  --graph examples/building/building.graph.json \
  --semantic /tmp/building.semantic.json \
  --report /tmp/building.report.json \
  --script houdini=/tmp/building_houdini.py \
  --output /tmp/Building.nodebridge

nodebridge usd validate /tmp/Building.nodebridge
nodebridge usd inspect /tmp/Building.nodebridge
```

With pxr installed, the same inputs can be layered, then inspected and compared:

```bash
nodebridge usd package \
  --scene examples/openusd/cube.usda \
  --graph examples/building/building.graph.json \
  --semantic /tmp/building.semantic.json \
  --script houdini=/tmp/building_houdini.py \
  --output /tmp/BuildingLayered.nodebridge \
  --layered

nodebridge usd inspect /tmp/BuildingLayered.nodebridge/scene.usda --json
nodebridge usd compare /tmp/BuildingLayered.nodebridge/scene.usda /tmp/BuildingLayered.nodebridge/scene.usda
```

`--procedural` adds a `UsdProc.GenerativeProcedural` prim with `proceduralSystem = "nodebridge"`. Nothing in a generic USD reader runs that prim.

Exit codes follow the rest of the CLI: 0 success, 1 validation or a missing pxr feature, 2 bad input. `compare` exits 0 when both stages were read, including when the verdict is DIFFERENCE or INCONCLUSIVE.

## What inspection reports

A stage summary includes the root layer, default prim, prim count, up axis, meters per unit, layer and reference paths, counts of meshes, transforms, curves, point clouds, instances, and materials, world-axis bounds, and per-prim type, transform, topology, material binding, USD kind, and NodeBridge custom data. Missing references are listed. Instance prototypes are not expanded. Bounds include transforms and use the stage's linear units. A bounds match is not vertex identity.

Comparison pairs prims by `generator_id` when both sides carry one, otherwise by exact prim path. Geometry that cannot be paired yields INCONCLUSIVE, not MATCH. Unmatched transforms or scopes do not hide a geometry match. Differences in translation, bounds, topology, or material binding yield DIFFERENCE.

## Materials

Three artifacts are easy to confuse:

1. **Houdini MaterialX network code.** The shader backend already emits `hou` calls that build a MaterialX network in `/mat`. That script is a native Houdini result. Noise and some coordinates stay APPROXIMATE.
2. **A portable `.mtlx` document.** NodeBridge 0.4 does not write one. Renaming the Houdini script to `.mtlx` would not make it MaterialX.
3. **USD UsdShade.** Inspection records material bindings when pxr can read them. NodeBridge does not author a UsdShade network from Semantic IR in this release, and it does not mark a shader EXACT because a bundle opens.

UsdPreviewSurface, when requested from Blender, is that exporter's limited fallback.

## UsdProc

`UsdProc.GenerativeProcedural` names a procedural system and can store parameters. It does not execute Blender, Houdini, or Unreal. The reliable record in 0.4 is the sidecar plus namespaced custom data. The procedural prim is an optional marker for a future NodeBridge-aware consumer.

## What this release does not do

- Bidirectional Houdini-to-Blender translation.
- A custom schema plugin, a Hydra plugin, or a file-format plugin.
- Live evaluation of the graph inside USD.
- Automatic variant sets for every exposed parameter. Variants are discrete composition choices, not the generator's continuous controls.
- Proof that two DCC exports match because their bounding boxes match.

Live Houdini 20.x and Unreal 5.4+ runs of the generated scripts are still outstanding. See [examples/live_sessions.md](../examples/live_sessions.md) and the [roadmap](roadmap.md).
