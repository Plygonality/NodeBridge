# Roadmap

## Done in 0.3

1. **Milestone 1:** Blender Geometry Nodes → Semantic IR → Houdini SOP network (scatter, instancing, random scale and rotation, noise masks, math, transforms, materials, extrusion, nested groups as subnets with promoted parameters).
2. **Milestone 2:** Geometry Nodes → Unreal PCG graphs (point-processing subset).
3. **Milestone 3:** Shader nodes → Houdini MaterialX and → Unreal Materials.
4. **Milestone 4:** Compositor → Houdini COP2 and → Unreal Post Process Volume, where a semantic equivalent exists.

## Next, in priority order

1. **Run the four examples in live Houdini 20.x and Unreal 5.4 / 5.5.** Record the parameter names, pin labels and property names reported in `NB_WARNINGS`, fix the mappings, and add version notes. This is the highest-value step: the generated code is so far verified structurally (recording fakes), not in a live session.
2. **Unreal PCG graph parameters.** Use real PCG user parameters instead of script-level controls once the Python API can create them reliably.
3. **Field coverage on Unreal.** Map more per-point fields onto PCG attribute nodes (Attribute Maths, Attribute Noise, Point From Mesh), and consider a Geometry Script context for mesh modelling (extrude, boolean, curves).
4. **Houdini HDAs.** Optionally turn subnets that come from node groups into digital assets, with the group interface as the HDA interface.
5. **Simulation and Repeat zones.** Houdini Solver SOPs and For-Each blocks are natural targets.
6. **More shader coverage:** Principled coat/sheen/subsurface in MaterialX, Unreal Substrate, and material functions for shader groups.
7. **Copernicus** (Houdini 20.5+) as the compositor target instead of COP2.
8. **Round trips:** a Houdini frontend (SOP network → Graph IR) using the `SourceFrontend` interface.
9. **Additional targets** through `TargetBackend`: Maya / Bifrost, Godot, Cinema 4D, Nuke, Substance Designer.

## Explicitly not planned

* Promising vertex- or pixel-identical results between applications.
* An AI model in the translation path. An optional suggestion provider may come later.
