# NodeBridge

NodeBridge translates procedural **semantics** between applications. It does
not merely rename nodes.

Today (Milestone 1) you work in a **terminal** and **Python**. You inspect,
validate, and report on Intermediate Representation (IR) files. Blender
extraction and Houdini / Unreal generation are not wired up yet.

```
Blender  →  IR JSON  →  Houdini SOP / Unreal system
              ▲
     you are here
```

---

## Where you use it

| You are in | You do this |
| --- | --- |
| **Terminal**, repo root | Install, inspect, validate, report, run tests |
| **Python** (REPL or a `.py` file) | Build graphs, save/load `.nodebridge.json` |
| **Blender** Geometry/Shader/Compositor editor | Export a node tree — *not available yet* (Milestone 2 / 6) |
| **Houdini** Python Source Editor | Run generated SOP scripts — *not available yet* (Milestone 3) |
| **Unreal** Python console | Run generated material / PCG scripts — *not available yet* (Milestone 7) |

You do **not** need Blender, Houdini, or Unreal installed for anything on
this page.

---

## Step 1 — Open a terminal in the repo

1. Clone or open the NodeBridge repository.
2. `cd` into the repo root (the folder that contains `pyproject.toml`).

```bash
cd /path/to/NodeBridge
```

3. Confirm you are in the right place:

```bash
ls pyproject.toml src/nodebridge README.md
```

You should see those three paths.

---

## Step 2 — Install NodeBridge

Requires **Python 3.11 or newer**.

1. (Optional but recommended) create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
```

2. Install the package in editable mode, with test tools:

```bash
python3 -m pip install -e ".[dev]"
```

3. Confirm the CLI:

```bash
python3 -m nodebridge --version
```

Expected output:

```text
NodeBridge 0.1.0 (IR version 1)
```

If `python3 -m nodebridge` cannot find the module, you are not in the
environment where you installed the package. Activate `.venv` and retry.

The console script `nodebridge` is also installed. Use it if it is on
your `PATH`:

```bash
nodebridge --version
```

The rest of this guide uses `python3 -m nodebridge` because it works
without changing `PATH`.

---

## Step 3 — Inspect a sample graph

This is the fastest way to see what an IR document looks like.

1. Stay in the repo root.
2. Run:

```bash
python3 -m nodebridge inspect tests/fixtures/transform_geometry.nodebridge.json
```

3. You should see a summary similar to:

```text
NodeBridge IR 1 (package 0.1.0)
Source: blender
Graph: transform_geometry (graph_0001)
System: geometry
Nodes: 4
Connections: 3
Nested graphs: 0
Operations:
  node_in: graph.input
  node_offset: vector.add
  node_out: graph.output
  node_xform: geometry.transform
```

That file is a stand-in for a Blender Geometry Nodes tree: geometry in,
a vector add, a transform, geometry out.

Open the same file in any text editor if you want to read the JSON.
Do not hand-edit it unless you are debugging — the Python API is the
supported way to build graphs.

More on these files: [tests/fixtures/README.md](tests/fixtures/README.md).

---

## Step 4 — Validate a graph

1. Run:

```bash
python3 -m nodebridge validate tests/fixtures/math_add.nodebridge.json
```

2. Expected first line:

```text
OK
```

Exit code `0` means the graph is structurally valid. Warnings may still
print below `OK` (for example an unknown operation). Exit code `1` means
the graph is invalid (broken connections, missing nodes, and so on).

---

## Step 5 — Run a compatibility report

This classifies every operation against a target. No Houdini or Unreal
code is generated.

1. Report against Houdini:

```bash
python3 -m nodebridge report tests/fixtures/transform_geometry.nodebridge.json --target houdini
```

2. You should see a block starting with:

```text
NodeBridge Translation Report
=============================
Source:
blender geometry
Target:
houdini
```

3. Counts will currently show **Unsupported** for every node. That is
   expected: no backend mappings exist yet. The report is still the
   workflow you will use after Milestone 3 — it will never silently
   pretend a mapping is exact.

4. Try Unreal the same way:

```bash
python3 -m nodebridge report tests/fixtures/transform_geometry.nodebridge.json --target unreal
```

`python3 -m nodebridge translate …` exists as a command name but is
**not implemented**. It will print an error and exit `2`.

---

## Step 6 — Build a graph in Python

**Where:** a Python REPL (`python3`) or any `.py` file. Working directory
does not matter as long as the package is installed.

1. Start Python:

```bash
python3
```

2. Paste:

```python
from nodebridge import GraphBuilder, GraphSystem, DataType, validate_graph, dumps

builder = GraphBuilder(name="example", system=GraphSystem.GEOMETRY)
add = builder.node("math.add")
builder.input(add, "a", DataType.FLOAT, default=1.0)
builder.input(add, "b", DataType.FLOAT, default=2.0)
builder.output(add, "value", DataType.FLOAT)

result = validate_graph(builder.graph)
print("valid:", result.ok)
print(dumps(builder.graph))
```

3. You should see `valid: True` and a JSON document with
   `"ir_version": "1"` and one `math.add` node.

4. Wire two nodes together (transform + translation):

```python
from nodebridge import GraphBuilder, GraphSystem, DataType

b = GraphBuilder(name="move_up", system=GraphSystem.GEOMETRY)

incoming = b.node("graph.input")
geo_in = b.output(incoming, "geometry", DataType.GEOMETRY)

offset = b.node("vector.add")
b.input(offset, "a", DataType.VECTOR3, default=(0.0, 0.0, 1.0))
b.input(offset, "b", DataType.VECTOR3, default=(0.0, 0.0, 0.0))
vec_out = b.output(offset, "vector", DataType.VECTOR3)

xform = b.node("geometry.transform")
geo_sock = b.input(xform, "geometry", DataType.GEOMETRY)
t_sock = b.input(xform, "translation", DataType.VECTOR3)
geo_out = b.output(xform, "geometry", DataType.GEOMETRY)

outgoing = b.node("graph.output")
final = b.input(outgoing, "geometry", DataType.GEOMETRY)

b.connect(incoming, geo_in, xform, geo_sock)
b.connect(offset, vec_out, xform, t_sock)
b.connect(xform, geo_out, outgoing, final)

print(list(b.graph.nodes))
print(b.graph.topological_order())
```

`operation` is a semantic name (`geometry.transform`), not a Blender UI
name (`GeometryNodeTransform`). Source names belong in provenance when
an adapter fills them in.

---

## Step 7 — Save and reload JSON

**Where:** still in Python. The file can live anywhere; this example
writes next to your current working directory.

```python
from pathlib import Path
from nodebridge import load, dump, validate_graph

# `b` is the GraphBuilder from Step 6
path = Path("move_up.nodebridge.json")
dump(b.graph, path)

document = load(path)
print(document.graph.name)
print(validate_graph(document.graph).ok)
```

Or from the terminal, after the file exists:

```bash
python3 -m nodebridge inspect move_up.nodebridge.json
python3 -m nodebridge validate move_up.nodebridge.json
```

Round-trip rule: IR → JSON → IR must keep operations, sockets,
connections, types, and IDs.

---

## Step 8 — Run the test suite

**Where:** repo root, after Step 2.

```bash
python3 -m pytest
```

Expected: all tests passed. Add `-v` if you want the per-file list.

```bash
python3 -m pytest -v
```

---

## Step 9 — (Later) Export from Blender

**Not implemented.** This is the intended click path so you know where
the add-on will live.

1. Open **Blender** (4.2+).
2. Edit → Preferences → Add-ons → Install.
3. Select `blender_addon/` (Milestone 6 will make this installable).
4. Enable **NodeBridge**.
5. Open a node editor:
   - Geometry Nodes workspace, or
   - Shader Editor, or
   - Compositor.
6. Press `N` to open the sidebar.
7. Click the **NodeBridge** tab.
8. Choose source tree and target (Houdini / Unreal).
9. Click **Analyse**, then **Export** / **Generate**.

Until that ships, build or inspect IR files as in Steps 3–7.

Geometry Nodes walkthrough (planned):
[examples/geometry_nodes/README.md](examples/geometry_nodes/README.md)

Shader walkthrough (planned):
[examples/shaders/README.md](examples/shaders/README.md)

Compositor walkthrough (planned):
[examples/compositor/README.md](examples/compositor/README.md)

---

## Step 10 — (Later) Rebuild in Houdini

**Not implemented.** Intended path after Milestone 3:

1. Generate a script (this command fails today):

```bash
python3 -m nodebridge translate graph.nodebridge.json --target houdini --output houdini_output.py
```

2. Open **Houdini**.
3. Windows → Python Source Editor (or a Python SOP).
4. Open `houdini_output.py` and run it.
5. A **NodeBridge** SOP subnet should appear with native, editable nodes.

---

## Step 11 — (Later) Rebuild in Unreal Engine 5

**Not implemented.** Intended path after Milestone 7:

1. Generate a script (this command fails today):

```bash
python3 -m nodebridge translate graph.nodebridge.json --target unreal --output unreal_output.py
```

2. Open the Unreal Editor with Python enabled.
3. Window → Developer Tools → Output Log, or the Python console.
4. Paste or `exec(open(r"unreal_output.py").read())`.
5. The matching Material / PCG / Geometry Script asset should appear.

---

## Command cheat sheet

| Goal | Command |
| --- | --- |
| Version | `python3 -m nodebridge --version` |
| Summarize a file | `python3 -m nodebridge inspect path.json` |
| Check structure | `python3 -m nodebridge validate path.json` |
| Classify vs a target | `python3 -m nodebridge report path.json --target houdini` |
| Generate host code | *not implemented* |
| Tests | `python3 -m pytest` |

---

## What this is / is not

**Is:** a software-independent IR, a growing operation catalog, a
registry for one-to-many translations, and a report that refuses to
hide approximations.

**Is not:** a Blender exporter that string-replaces node names, a live
IPC bridge, or a tool that silently produces a different graph.

Architecture: [docs/architecture.md](docs/architecture.md)
IR details: [docs/intermediate_representation.md](docs/intermediate_representation.md)
Roadmap: [docs/roadmap.md](docs/roadmap.md)
Compatibility: [docs/compatibility.md](docs/compatibility.md)

## License

MIT. See [LICENSE](LICENSE).
