# Shader examples — click-by-click

**Where this folder will live in the workflow**

```
Blender Shader Editor (material)
        ↓
  examples/shaders/          ← .blend + IR (later)
        ↓
  Unreal Material Editor     ← Milestone 7 candidate
```

No shader graphs ship yet. The IR already has operations such as
`shader.principled_surface`, `color.mix`, and `texture.sample`, so you
can practice the file format without Unreal or Blender.

---

## What you can do today

**Where:** terminal at the repo root, or `python3`.

### 1. See which shader operations the catalog already knows

```python
from nodebridge.core.operations import DEFAULT_OPERATION_REGISTRY

for spec in DEFAULT_OPERATION_REGISTRY.by_category("shader"):
    print(spec.name, "—", spec.description)
for spec in DEFAULT_OPERATION_REGISTRY.by_category("color"):
    print(spec.name, "—", spec.description)
```

### 2. Build a tiny principled-surface IR by hand

This is **not** a full Principled BSDF. It is enough to inspect, save,
and report.

```python
from nodebridge import GraphBuilder, GraphSystem, DataType, dump, validate_graph

b = GraphBuilder(name="principled_demo", system=GraphSystem.SHADER)

shader = b.node("shader.principled_surface")
b.input(shader, "base_color", DataType.COLOR, default=(0.8, 0.8, 0.8, 1.0))
b.input(shader, "roughness", DataType.FLOAT, default=0.5)
b.input(shader, "metallic", DataType.FLOAT, default=0.0)
surface = b.output(shader, "shader", DataType.SHADER)

out = b.node("graph.output")
shader_in = b.input(out, "surface", DataType.SHADER)
b.connect(shader, surface, out, shader_in)

assert validate_graph(b.graph).ok
dump(b.graph, "examples/shaders/principled_demo.nodebridge.json")
```

### 3. Inspect and report it

```bash
python3 -m nodebridge inspect examples/shaders/principled_demo.nodebridge.json
python3 -m nodebridge validate examples/shaders/principled_demo.nodebridge.json
python3 -m nodebridge report examples/shaders/principled_demo.nodebridge.json --target unreal
```

The report should list `shader.principled_surface` as **Unsupported**
until the Unreal material backend exists. That is expected.

---

## Later — author the material in Blender

**Where:** Blender, Shader Editor. Requires a later extraction milestone.

1. Open Blender.
2. Click the **Shading** workspace tab.
3. Select the object whose material you want to export.
4. In the Shader Editor, confirm the tree ends at **Material Output**.
5. Keep the first examples small: Principled BSDF + one color or noise.
6. Press `N` → **NodeBridge**.
7. Source: Shader Nodes. Target: **Unreal**.
8. Click **Analyse**, then **Export**.

---

## Later — rebuild it in Unreal

**Where:** Unreal Editor Python console. Requires Milestone 7.

1. Generate (fails today):

```bash
python3 -m nodebridge translate \
  examples/shaders/principled_demo.nodebridge.json \
  --target unreal \
  --output unreal_material.py
```

2. Open the Unreal project with Python enabled
   (Edit → Plugins → Python Editor Script Plugin).
3. Window → Developer Tools → Output Log.
4. Run the generated script (paste, or `py` the file from the console).
5. Content Browser: look for a Material whose graph is native Unreal
   nodes (not a baked texture).

Shader graphs should go to the **Material Editor**, not PCG. Geometry
graphs go the other way. NodeBridge is supposed to pick the capability,
not force every Blender tree into one Unreal system.

---

## When you add a real example here

1. One material per file; name IR and `.blend` the same stem.
2. Prefer Principled BSDF over custom node groups for the first drop.
3. Note whether normals, displacement, or volume are in the tree —
   those change the Unreal target.
