# Examples

These graphs are duck-typed Blender trees. `graph.json` is graph IR. The `.py` files are the scripts NodeBridge generates. The `.txt` files are the translation reports.

| Example | Source | What it exercises |
| --- | --- | --- |
| `scatter` | Geometry Nodes | Surface input, density, scatter, cube instance, random scale and rotation, realize |
| `building` | Geometry Nodes | Grid, extrude, subdivide, scatter, facade instance, join, exposed Height and Density |
| `shader` | Shader nodes | Texture coordinate, noise, color ramp, roughness map range, bump, Principled BSDF |
| `compositor` | Compositor | Render layer, glare, color correction, ellipse vignette, mix, composite |

Regenerate them from the repository root:

```bash
python3 -c "from scripts.generate_examples import main; main()"
```

The generator writes the same files the tests compile. It does not run Houdini or Unreal.
