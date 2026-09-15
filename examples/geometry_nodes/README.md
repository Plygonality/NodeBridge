# Geometry Nodes examples — click-by-click

**Where this folder will live in the workflow**

```
Blender Geometry Nodes
        ↓
  examples/geometry_nodes/   ← .blend files + exported IR (later)
        ↓
  tests/fixtures/            ← use these JSON files today
        ↓
  Houdini SOP network
```

This directory is empty of graphs on purpose. Milestone 2 will drop
small `.blend` / exported `.nodebridge.json` examples here. Until then,
use the IR stand-ins.

---

## What you can do today

**Where:** terminal at the repo root. Blender is not required.

### 1. Inspect the Geometry Nodes stand-in

```bash
python3 -m nodebridge inspect tests/fixtures/transform_geometry.nodebridge.json
```

That graph is the IR equivalent of:

`Group Input` → `Transform Geometry` ← `Vector Math (Add)` → `Group Output`

### 2. Validate it

```bash
python3 -m nodebridge validate tests/fixtures/transform_geometry.nodebridge.json
```

Expect `OK`.

### 3. Ask how it would fare in Houdini (no SOPs generated yet)

```bash
python3 -m nodebridge report tests/fixtures/transform_geometry.nodebridge.json --target houdini
```

Every operation will be **Unsupported**. That is the honest Milestone 1
result, not a failed install.

### 4. Rebuild the same graph yourself in Python

```python
from nodebridge import GraphBuilder, GraphSystem, DataType, dump, validate_graph

b = GraphBuilder(name="transform_geometry", system=GraphSystem.GEOMETRY)

incoming = b.node("graph.input", node_id="node_in")
geo_in = b.output(incoming, "geometry", DataType.GEOMETRY)

offset = b.node("vector.add", node_id="node_offset")
b.input(offset, "a", DataType.VECTOR3, default=(0.0, 0.0, 1.0))
b.input(offset, "b", DataType.VECTOR3, default=(0.0, 0.0, 0.0))
vec = b.output(offset, "vector", DataType.VECTOR3)

xform = b.node("geometry.transform", node_id="node_xform")
geo_sock = b.input(xform, "geometry", DataType.GEOMETRY)
t_sock = b.input(xform, "translation", DataType.VECTOR3)
geo_out = b.output(xform, "geometry", DataType.GEOMETRY)

outgoing = b.node("graph.output", node_id="node_out")
final = b.input(outgoing, "geometry", DataType.GEOMETRY)

b.connect(incoming, geo_in, xform, geo_sock)
b.connect(offset, vec, xform, t_sock)
b.connect(xform, geo_out, outgoing, final)

assert validate_graph(b.graph).ok
dump(b.graph, "examples/geometry_nodes/transform_geometry.nodebridge.json")
```

Then:

```bash
python3 -m nodebridge inspect examples/geometry_nodes/transform_geometry.nodebridge.json
```

(Git ignores `*.nodebridge.json` at the repo root; files under
`examples/` are fine to create locally.)

---

## Later — author the graph in Blender

**Where:** Blender, Geometry Nodes workspace. Requires Milestone 2+.

1. Open Blender.
2. Click the **Geometry Nodes** workspace tab at the top.
3. Select the default cube (or add a mesh).
4. In the modifier properties, click **Add Modifier → Geometry Nodes**.
5. Click **New** to create a node tree.
6. Add these nodes (`Shift+A`):
   - **Geometry → Transform Geometry**
   - **Utilities → Vector Math** (set to Add, Z = 1)
7. Wire:
   - `Group Input` Geometry → Transform Geometry Geometry
   - Vector Math Vector → Transform Geometry Translation
   - Transform Geometry Geometry → `Group Output` Geometry
8. Press `N` in the node editor.
9. Open the **NodeBridge** sidebar tab (Milestone 6).
10. Target: **Houdini**. Click **Analyse**, then **Export**.

Until the add-on exists, skip 8–10 and use the Python snippet above.

---

## Later — rebuild it in Houdini

**Where:** Houdini Python Source Editor. Requires Milestone 3.

1. Generate (command will fail today):

```bash
python3 -m nodebridge translate \
  tests/fixtures/transform_geometry.nodebridge.json \
  --target houdini \
  --output houdini_output.py
```

2. Open Houdini.
3. Create an object at `/obj`, dive into it.
4. Windows → **Python Source Editor**.
5. Load `houdini_output.py` and run it.
6. Look for a **NodeBridge** subnet containing native SOPs (likely a
   Transform SOP plus any attribute helpers).
7. The network should stay editable — that is the point of semantic
   translation, not a baked mesh.

---

## When you add a real example here

1. Keep the Blender tree tiny (the five-node Milestone 2 subset).
2. Export IR next to the `.blend` with the same stem name.
3. Add a one-screen screenshot only if the node layout needs it.
4. Document the exact Blender version in a short note in this file.
