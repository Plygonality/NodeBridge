# Roadmap

## Done in 0.4

1. **OpenUSD bundles.** A Blender user can export the evaluated Geometry Nodes object with Blender's USD exporter and store Graph IR, Semantic IR, the translation report, and an optional native script in one directory. `manifest.json` records relative paths, SHA-256 hashes, and asset-level provenance.
2. **Validation without USD.** `nodebridge usd validate` checks the manifest, hashes, and IR documents with no `pxr` and no Blender. It does not execute sidecar scripts.
3. **Optional pxr tools.** When the bindings import, NodeBridge can inspect a stage, write a `scene.usda` root that references the geometry layer, and attach namespaced custom data. An experimental `UsdProc` marker can be added. Generic DCCs do not evaluate it.
4. **Scene comparison.** `nodebridge usd compare` reports MATCH, DIFFERENCE, or INCONCLUSIVE from bounds, transforms, topology, and material bindings. That result is evidence about the exported scenes. It is not a translation classification.

Live Houdini and Unreal sessions were not run for 0.4. USD does not close that gap.

## Done in 0.3

1. **Milestone 1:** Blender Geometry Nodes → Semantic IR → Houdini SOP network (scatter, instancing, random scale and rotation, noise masks, math, transforms, materials, extrusion, nested groups as subnets with promoted parameters).
2. **Milestone 2:** Geometry Nodes → Unreal PCG graphs (point-processing subset).
3. **Milestone 3:** Shader nodes → Houdini MaterialX and → Unreal Materials.
4. **Milestone 4:** Compositor → Houdini COP2 and → Unreal Post Process Volume, where a semantic equivalent exists.

## Next, in priority order

1. **Run the four examples in live Houdini 20.x and Unreal 5.4 / 5.5.** Record the parameter names, pin labels and property names reported in `NB_WARNINGS`, fix the mappings, and add version notes. This is still the highest-value step: the generated code is verified structurally (recording fakes), not in a live session. A USD bundle does not replace that check. Where both DCCs can export USD, a later comparison can measure the evaluated results; it still will not prove the graphs are equivalent.
2. **Unreal PCG graph parameters.** Use real PCG user parameters instead of script-level controls once the Python API can create them reliably.
3. **Field coverage on Unreal.** Map more per-point fields onto PCG attribute nodes (Attribute Maths, Attribute Noise, Point From Mesh), and consider a Geometry Script context for mesh modelling (extrude, boolean, curves).
4. **Houdini HDAs.** Optionally turn subnets that come from node groups into digital assets, with the group interface as the HDA interface.
5. **Simulation and Repeat zones.** Houdini Solver SOPs and For-Each blocks are natural targets.
6. **More shader coverage:** Principled coat/sheen/subsurface in MaterialX, Unreal Substrate, and material functions for shader groups.
7. **Copernicus** (Houdini 20.5+) as the compositor target instead of COP2.
8. **Round trips:** a Houdini frontend (SOP network → Graph IR) using the `SourceFrontend` interface.
9. **Additional targets** through `TargetBackend`: Maya / Bifrost, Godot, Cinema 4D, Nuke, Substance Designer.
10. **USD follow-ons, only with a verified consumer:** a portable MaterialX document for the supported shader subset, a UsdShade binding layer, and a NodeBridge-aware procedural evaluator. Not a Hydra plugin, not a C++ file-format plugin, and not automatic variant sets for every exposed parameter.

## Explicitly not planned

* Promising vertex- or pixel-identical results between applications.
* Treating an OpenUSD stage as a replacement for Semantic IR, or as a native procedural target next to Houdini and Unreal.
* An AI model in the translation path. An optional suggestion provider may come later.
