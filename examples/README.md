# Examples

Open [`nodebridge_examples.blend`](nodebridge_examples.blend) to try the four systems. The file is built by [`blender/build_examples.py`](blender/build_examples.py). Rebuild it from Blender's Text Editor with **Run Script**, or headless:

```bash
blender --background --factory-startup --python examples/blender/build_examples.py -- --save examples.blend
```

| Folder | Blender system | Files |
| --- | --- | --- |
| [`scatter/`](scatter/) | **ScatterRocks** on the *Ground* object: Distribute Points on Faces → Delete Geometry by a noise coverage mask → Instance on Points (an ico sphere with a material) with random scale → Rotate Instances with a random yaw → Realize → Join | `scatter.graph.json` (Graph IR exported from Blender 4.2), `expected_report_*.txt`, `generated_*.py` |
| [`building/`](building/) | **BuildingGenerator** on the *Building* object: grid footprint → extruded mass (Floors × Floor Height); floor slabs from the nested **FloorSlab** group stacked on a Mesh Line; windows distributed on walls (Normal.z ≈ 0) with random scale | same |
| [`shader/`](shader/) | **ProceduralRock** material: Object coordinates → Mapping → Noise → 3-stop Color Ramp (base color), Map Range with a labeled *Roughness Scale* Value (roughness), Bump (normal) | same |
| [`compositor/`](compositor/) | Scene compositor: Render Layers → Glare (fog glow) → Color Balance → Multiply with a blurred Ellipse Mask (vignette) → Composite | same |

`generated_houdini.py` and `generated_unreal.py` are exactly what the add-on's **Generate Code** button produces for these trees. The tests compare against them. Regenerate them with `python tools/regenerate_examples.py`.

[`openusd/`](openusd/) holds a one-cube USDA stage for `nodebridge usd package`. It is not a Blender export of the building. The building's evaluated USD scene is written by **Export USD Bundle** inside Blender.
