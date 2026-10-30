# OpenUSD examples

`cube.usda` is a Z-up cube, 2 meters on each side (`metersPerUnit` 1, `size` 2). It exists so `nodebridge usd package` can be run without Blender. It is not the evaluated building from `nodebridge_examples.blend`.

A Blender export of the Building object is produced inside Blender by **Export USD Bundle**. That path is covered by `tests/blender/run_in_blender.py` when `NODEBRIDGE_BLENDER` points at Blender 4.2 or newer. It was not executed in an environment without Blender.

The commands in [docs/openusd_integration.md](../../docs/openusd_integration.md) package this cube with `examples/building/building.graph.json` and the Houdini script NodeBridge generates from that graph. Open the file named by `scene.usd_path` in `manifest.json`. For this cube that file is `scene.usda`. A Blender export uses `scene.usdc`. A layered bundle opens `scene.usda`, which references `geometry/evaluated.*`. Run `procedural/houdini.py` in Houdini if you want the editable SOP network. The script does not read the cube.
