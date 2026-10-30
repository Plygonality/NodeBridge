# Bundle schema

A NodeBridge bundle is a directory. `manifest.json` is the authority for its contents. The Graph IR format version (`format_version` 1 in `ir/serialization.py`) and the application version are different numbers from this schema.

## format_version 1

```json
{
  "format": "nodebridge.bundle",
  "format_version": 1,
  "nodebridge_version": "0.4.0",
  "publisher": "blender",
  "publication_id": "<sha256 of artifact path and hash lines>",
  "source": {
    "dcc": "blender",
    "graph_path": "procedural/source.graph.json",
    "semantic_path": "procedural/generator.semantic.json",
    "generator_id": "nodebridge:/dcc=blender/object=Building/modifier=NodeBridge Example/tree=BuildingGenerator",
    "generator_revision": "<sha256 of the graph sidecar bytes>",
    "semantic_revision": "<sha256 of the semantic sidecar bytes>",
    "tree": "BuildingGenerator"
  },
  "scene": {
    "usd_path": "scene.usdc",
    "composition": "basic",
    "up_axis": "Z",
    "meters_per_unit": 1.0,
    "up_axis_source": "usd-stage",
    "default_prim": "/World"
  },
  "targets": {
    "houdini": {"script_path": "procedural/houdini.py"}
  },
  "artifacts": [
    {"path": "scene.usdc", "sha256": "<hex>", "bytes": 1234, "role": "scene"}
  ],
  "provenance": {},
  "warnings": [],
  "limitations": []
}
```

`publication_id` is the SHA-256 of sorted lines `path<TAB>sha256`, including a trailing newline. `manifest.json` is not an artifact of itself. Optional scripts, the report, and a provenance overlay are included only when those files were written.

`limitations` are standing facts about the representation. `warnings` are specific to this publication (for example, pxr was absent so the stage was not read back). `nodebridge usd validate --strict` fails on warnings. It does not fail on limitations.

## On-disk contract

Basic bundle (Blender exporter, pxr not required):

```
Name.nodebridge/
  scene.usdc                         # or scene.usda / scene.usd, matching the exported file
  procedural/source.graph.json
  procedural/generator.semantic.json
  procedural/report.json             # when a translation report was available
  procedural/report.txt
  procedural/houdini.py              # only when that target was generated
  procedural/unreal.py               # only when that target was generated
  procedural/provenance.usda         # only when pxr could author an overlay
  manifest.json
```

Layered bundle (`--layered`, requires pxr):

```
Name.nodebridge/
  scene.usda                         # composition root; open this file
  geometry/evaluated.usdc            # the exported geometry, unmodified by composition
  procedural/...
  manifest.json
```

`scene.usda` sublayers `./geometry/evaluated.<ext>` with a relative path. Stage `upAxis`, `metersPerUnit`, and the default prim are copied from the geometry layer when that layer authors them. NodeBridge custom data is an `over` on the default prim in the root layer. The geometry file is not rewritten.

Paths in the manifest are bundle-relative POSIX paths. `..`, absolute paths, and symlinks that resolve outside the bundle are rejected. Validation parses the IR JSON as data. It does not import or execute `houdini.py` or `unreal.py`.

A bundle stays valid when the directory is moved, as long as the files inside it move together. Layered references are relative. The publication hash does not include a machine path or a timestamp.

Binary USD written by Blender can differ across Blender versions. The manifest hash records the bytes that were actually written. It does not claim those bytes are stable across DCCs.

## Identifiers

Logical ids do not include file bytes:

```
nodebridge:/dcc=<dcc>[/scene=<scene>][/object=<object>][/modifier=<modifier>]/tree=<tree>
```

Components are Unicode NFC, trimmed, with whitespace collapsed. A slash inside a component becomes `_`. `dcc` and `tree` are required, so two generators that share a display name and differ by object or modifier stay distinct.

A nested group is `<generator>/group/<tree>`. A semantic operation is `<owner>/op/<operation id>`. Those operation ids are listed under `provenance.semantic_operations`. They identify sidecar operations. They are not USD prim paths.

`source.generator_revision` is the SHA-256 of `procedural/source.graph.json`. Editing the graph changes the revision and leaves `generator_id` in place.

`provenance.prim_mappings` is asset-level for an evaluated mesh. NodeBridge does not invent a per-face map from Geometry Nodes to USD faces. An empty `prim_path` means the default prim was not read.

## USD custom data

When pxr authors metadata, the key is the dictionary `nodebridge` on the default prim:

```text
schema = nodebridge.provenance
schema_version = 1
generator_id = <logical id>
generator_revision = <graph sha256>    # layered root only, after the graph bytes are known
manifest = <relative path to manifest.json>
mapping = asset
```

The publication hash is not stored inside the USD layer. Putting it there would change the hash. The manifest remains the package index.

`UsdProc.GenerativeProcedural` is optional (`nodebridge usd package --layered --procedural`). `proceduralSystem` is `nodebridge`. The prim points at the semantic sidecar. A DCC that does not implement NodeBridge will not evaluate it.

## Validation

`nodebridge usd validate DIRECTORY` checks:

- `format` and `format_version`
- every artifact exists, is inside the bundle, and matches `sha256`
- `publication_id` matches those hashes
- Graph IR and Semantic IR parse with the existing loaders
- scene, geometry, overlay, and script paths exist when the manifest names them

Exit codes: 0 valid, 1 the bundle or stage failed validation, 2 the path or arguments are unusable.

A single `.usd`, `.usda`, `.usdc`, or `.usdz` file can be validated only when pxr is installed. Missing composed references fail that check. `usdchecker` is not bundled with `usd-core` and is not required.
