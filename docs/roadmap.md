# Roadmap

Do not attempt every node in every DCC. Build vertically: a complete
path for a small semantic subset, then widen.

This roadmap is reconciled with the repository. Milestone 1 (core IR)
shipped in 0.1. Version 0.2 implements the many-to-many compiler
architecture and a Blender ↔ Houdini construction-plan slice — work that
spans several of the originally numbered milestones.

## Completed

### Milestone 1 — Semantic compiler core (0.1, evolved in 0.2)

IR, types, validation, JSON, diagnostics, operation catalog, package
skeleton.

### Milestone 2–7 (architecture + vertical slice in 0.2)

* Host plugin contract with frontend **and** backend per host
* Capability model and translation planner
* Blender Geometry Nodes frontend + backend (fixtures / construction plans)
* Houdini SOP frontend + backend (fixtures / construction plans / VEX)
* Bidirectional Blender ↔ Houdini slice for scattering + transforms
* Unreal PCG frontend + backend contracts, fixtures, experimental scripts
* Structured fidelity reports (`EXACT` … `UNSUPPORTED`)
* CLI: inspect, validate, capabilities, plan, report, translate

Live DCC execution is still optional and not CI-covered.

## Next

### Milestone 8 — Real Blender ↔ Houdini runtime slice

Run the scattering subset against actual `bpy` and `hou` sessions.
Verify editable Graphs in both applications. This is the highest-leverage
next step for real-world usefulness.

### Milestone 9 — Unreal PCG editor integration

Where the experimental Python API permits: create a PCG graph asset,
add Surface Sampler / Transform Points / Static Mesh Spawner, wire pins
with verified labels. Keep fixture tests as the CI path.

### Milestone 10 — Expanded semantic operation catalog

Incrementally: more primitives, curves, attributes, selections, noise,
deletes, joins. Each operation needs frontend + backend + tests + a
fidelity label.

### Milestone 11 — Round-trip metadata

Richer provenance, translation history on generated nodes, and tools to
diff two IR graphs semantically after an artist edit in the target DCC.
Perfect equivalence is still not the goal.

### Milestone 12 — Additional DCC host SDK

Maya/Bifrost, Substance Designer, or Nuke as a fourth host implemented
only through the host contract.

## Explicitly later

* Live localhost / IPC bridge
* Simulation and repeat zones
* Full shader / compositor coverage
* Baking evaluators
* USD / MaterialX interchange
