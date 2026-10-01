# Houdini backend

Generated scripts are pasted into the Houdini Python Source Editor and executed there. NodeBridge does not launch Houdini.

## Geometry

The script creates a new `/obj` Geometry node. It deletes only the default children of that new node. Other scene nodes are left alone.

Typical lowering:

| Semantic operation | Houdini | Confidence |
| --- | --- | --- |
| `geometry.primitive` | `box`, `sphere`, `grid`, `tube`, `circle`, `line` | Exact |
| `geometry.transform` | `xform` | Exact |
| `geometry.join` | `merge` | Exact |
| `points.distribute` | `scatter` | Equivalent. Density becomes `npts`. The random sequence differs. |
| `geometry.instance` | `copytopoints` | Equivalent |
| `geometry.realize_instances` | `unpack` then `convert` | Equivalent |
| `math.*`, `vector.*`, noise | `attribwrangle` | Equivalent. VEX is not Blender's implementation. |
| `geometry.subdivide` | `subdivide` | Approximate |
| `geometry.curve_to_mesh` | `sweep` | Approximate |

Node types are created through a helper that raises `hou.NodeError` when the type is missing.

## Materials

Shader graphs create a Material Builder under `/mat` and MaterialX nodes (`mtlxstandard_surface`, `mtlxnoise3d`, `mtlxmix`, and math nodes). Principled BSDF is equivalent, not identical. Noise will not match.

## Compositor

COP2 nodes inside `/img`: `colorcorrect`, `blur`, `blend`, `null`. Glare is an approximate blur. Ellipse and box masks are unsupported. If `/img` is missing, the script raises instead of inventing a Copernicus network.

## Coordinates and units

Blender position `(x, y, z)` becomes Houdini `(x, z, -y)`. Rotation values on transform parameters are converted from radians to degrees. Lengths stay in meters.
