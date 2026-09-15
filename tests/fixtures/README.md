# Test fixtures — click-by-click

**Where:** a terminal at the **repo root** (the folder with `pyproject.toml`).
These JSON files stand in for Blender node trees until extraction exists.

| File | What it represents |
| --- | --- |
| `math_add.nodebridge.json` | One `math.add` node (`1.0 + 2.0`) |
| `transform_geometry.nodebridge.json` | Geometry in → vector add → transform → geometry out |

You do not need Blender open.

---

## Step 1 — Confirm the files are there

```bash
ls tests/fixtures/*.nodebridge.json
```

You should see both files listed above.

---

## Step 2 — Inspect the math graph

```bash
python3 -m nodebridge inspect tests/fixtures/math_add.nodebridge.json
```

Expected:

```text
Graph: math_add (graph_0001)
Nodes: 1
Connections: 0
Operations:
  node_add: math.add
```

---

## Step 3 — Inspect the transform graph

```bash
python3 -m nodebridge inspect tests/fixtures/transform_geometry.nodebridge.json
```

Expected operations:

- `graph.input`
- `vector.add`
- `geometry.transform`
- `graph.output`

Three connections: geometry in, translation offset, geometry out.

---

## Step 4 — Validate both

```bash
python3 -m nodebridge validate tests/fixtures/math_add.nodebridge.json
python3 -m nodebridge validate tests/fixtures/transform_geometry.nodebridge.json
```

Each command should print `OK` and exit `0`.

---

## Step 5 — Load a fixture in Python

**Where:** `python3` from any directory, package installed.

```python
from nodebridge import load, validate_graph

doc = load("tests/fixtures/math_add.nodebridge.json")
node = doc.graph.get_node("node_add")

print(doc.source.application)          # blender
print(node.operation)                  # math.add
print(node.inputs["sock_a"].default)   # 1.0
print(node.inputs["sock_b"].default)   # 2.0
print(validate_graph(doc.graph).ok)    # True
```

If Python cannot find the file, pass an absolute path or `cd` to the
repo root first.

Load the transform fixture and walk connections:

```python
from nodebridge import load

doc = load("tests/fixtures/transform_geometry.nodebridge.json")
xform = doc.graph.get_node("node_xform")
print(xform.operation)
print(xform.metadata.provenance.original_type)  # GeometryNodeTransform

for link in doc.graph.connections:
    print(f"{link.source_node}.{link.source_socket} → {link.target_node}.{link.target_socket}")
```

---

## Step 6 — Open the JSON in an editor (optional)

1. Open `tests/fixtures/math_add.nodebridge.json` in your editor.
2. Look at the envelope at the top of the file (after sort-keys, fields
   appear alphabetically):

```json
{
  "graph": { "...": "..." },
  "ir_version": "1",
  "nodebridge_version": "0.1.0",
  "source": {
    "application": "blender"
  }
}
```

3. Do not rely on hand-editing. Rebuild with `GraphBuilder` + `dump()`
   if you need a new fixture.

---

## Step 7 — Regenerate a fixture (maintainers)

Only if the serializer output changed and tests fail on committed JSON.

**Where:** repo root, `python3`.

```python
from pathlib import Path
from nodebridge import dump
from tests.helpers import make_math_add_graph, make_transform_graph

root = Path("tests/fixtures")
dump(make_math_add_graph().graph, root / "math_add.nodebridge.json")
dump(make_transform_graph().graph, root / "transform_geometry.nodebridge.json")
```

Then re-run:

```bash
python3 -m pytest tests/test_serialization.py -v
```

The committed JSON must match `dump()` byte-for-byte (sorted keys,
trailing newline).
