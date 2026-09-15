# Compositor examples — click-by-click

**Where this folder will live in the workflow**

```
Blender Compositor
        ↓
  examples/compositor/     ← .blend + IR (later)
        ↓
  Unreal post-process / material  (later)
```

Compositor extraction is not implemented. You can still build a
compositor-typed IR graph to learn the document shape.

---

## What you can do today

**Where:** `python3` with NodeBridge installed (see the root README,
Steps 1–2).

### 1. Build a color-mix compositor graph

```python
from nodebridge import GraphBuilder, GraphSystem, DataType, dump, validate_graph

b = GraphBuilder(name="mix_over", system=GraphSystem.COMPOSITOR)

mix = b.node("color.mix")
b.input(mix, "a", DataType.COLOR, default=(1.0, 0.0, 0.0, 1.0))
b.input(mix, "b", DataType.COLOR, default=(0.0, 0.0, 1.0, 1.0))
b.input(mix, "factor", DataType.FLOAT, default=0.5)
color = b.output(mix, "color", DataType.COLOR)

out = b.node("graph.output")
image_in = b.input(out, "image", DataType.COLOR)
b.connect(mix, color, out, image_in)

print("valid:", validate_graph(b.graph).ok)
dump(b.graph, "examples/compositor/mix_over.nodebridge.json")
```

### 2. Inspect it from the terminal

```bash
python3 -m nodebridge inspect examples/compositor/mix_over.nodebridge.json
python3 -m nodebridge validate examples/compositor/mix_over.nodebridge.json
python3 -m nodebridge report examples/compositor/mix_over.nodebridge.json --target unreal
```

Expect `System: compositor` and **Unsupported** mappings.

---

## Later — author the tree in Blender

**Where:** Blender Compositor. Requires a later extraction milestone.

1. Open Blender.
2. Switch the editor type to **Compositor** (or use the Compositing
   workspace).
3. Check **Use Nodes**.
4. Add a small tree, for example:
   - Render Layers
   - Color → Mix Color
   - Composite output
5. Press `N` → **NodeBridge**.
6. Source: Compositor. Target: Unreal (post-process) or whatever the
   add-on lists.
7. Click **Analyse**, then **Export**.

Do not start with cryptomatte, lens distortion, or multi-layer EXR
setups. Those need dedicated operations that are not in the seed
catalog.

---

## Later — rebuild in the target

Compositor semantics may land in Unreal as a **post-process material**,
not as PCG and not as a SOP network. Wait for the capability picker
before assuming a host.

The generate command will look like every other target:

```bash
python3 -m nodebridge translate \
  examples/compositor/mix_over.nodebridge.json \
  --target unreal \
  --output unreal_compositor.py
```

That command is **not implemented** in Milestone 1.

---

## When you add a real example here

1. Prefer still images over animation-only nodes.
2. Export IR beside the `.blend`.
3. List Blender version and whether the tree uses Render Layers or
   image inputs.
