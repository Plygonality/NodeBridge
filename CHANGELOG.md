# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.4.0 - 2026-10-30

Optional OpenUSD scene bundles. The compiler is unchanged: Graph IR and Semantic IR still drive Houdini and Unreal code. USD is an evaluated scene plus provenance, not a third procedural backend.

### Added

- A pure-Python bundle (`manifest.json`, Graph IR, Semantic IR, translation report, optional native scripts) that validates without Blender or `pxr`.
- Stable generator, group, and operation ids, separate from content revisions and from the bundle publication hash.
- Blender **Export USD Bundle** in the NodeBridge sidebar. It calls the running Blender's `wm.usd_export` on the evaluated Geometry Nodes object, then restores selection, mode, and visibility.
- CLI: `nodebridge usd inspect`, `validate`, `package`, and `compare`. `analyze`, `generate`, and `capabilities` are unchanged.
- When `pxr` is installed: stage inspection, a layered `scene.usda` that references the geometry layer, namespaced `customData`, and an experimental `UsdProc.GenerativeProcedural` marker that generic DCCs do not evaluate.
- Optional extra `nodebridge[usd]` (`usd-core>=26.11`). The add-on zip does not ship the USD SDK.
- Example scripts regenerated so the header reads NodeBridge 0.4.0. Reports and the support matrix are unchanged. Graph IR fixtures keep the `nodebridge_version` they were exported with.
- [OpenUSD integration](docs/openusd_integration.md) and the [bundle schema](docs/bundle_schema.md).

### Not in this release

- Live Houdini 20.x and Unreal 5.4+ execution of the generated scripts. Still unverified.
- Reconstructing a Geometry Nodes, SOP, or PCG graph from USD geometry.
- A portable `.mtlx` document or a UsdShade translation of the shader backends.
- Custom USD schema plugins, Hydra, or a C++ file-format plugin.

## 0.3.0 - 2026-10-29

First tagged release. The tag to create is `v0.3.0`. `archive/milestone-1` (at `8adf232d`) is an archive marker, not a release.

`pyproject.toml`, `__version__`, `bl_info["version"]`, and `blender_manifest.toml` are `0.3.0`.

### Added

- Blender 4.2+ add-on that reads Geometry Nodes, shader, and compositor trees and generates native Houdini or Unreal Engine 5 Python (#3, #6, #10). The sidebar runs Analyze, Generate, Copy, and Save.
- Graph IR and Semantic IR. Each operation is classified EXACT, EQUIVALENT, APPROXIMATE, or UNSUPPORTED. Unknown nodes are reported and left as connected placeholders.
- Houdini backends for SOP networks, MaterialX materials, and COP2 compositing. Unreal backends for PCG graphs, Material assets, and an unbound Post Process Volume.
- Rewrite rules for multi-node idioms (scatter, random transform, spatial noise mask), VEX for fields, and shared conversion for axes, units, and deterministic randomness.
- CLI: `nodebridge analyze`, `nodebridge generate`, and `nodebridge capabilities`.
- `tools/build_addon.py` and the checked-in add-on zip `release/nodebridge-0.3.0.zip`.
- Scatter, building, shader, and compositor examples, with expected reports and generated scripts for both targets.
- Generated Python, VEX, and HScript keep graph strings inside literals and comments. Bad documents, unknown operations, and recursive groups produce diagnostics. `nodebridge generate` exits 1 on a translation error and does not write a script when the graph has a cycle. The CLI exits 2 on bad input (#9, #10).
- CI runs pytest and Ruff as separate gating jobs, and builds the extension on Blender 4.2, 4.5, and 5.2 (#10).

### Fixed

- A vector constant read as a scalar is the mean of its supplied components. A short vector is padded with `0.0` only when the target is wider. Non-finite components are still replaced with 0, and that warning is unchanged (#11).
- Blender 5.x color balance lift maps to Houdini colorcorrect combined lift (offset + 1). Unreal still receives the offset (#10).
- A compositor group output sets one display flag: Image, otherwise Beauty, otherwise the first colour socket (#10).
- Blender 5.x modifier values are read from `properties.inputs`. Compositor Mix maps to the matching COP2 blend. Viewer nodes are not the composite output. A PCG node with no mesh source connects to the graph input (#9).
