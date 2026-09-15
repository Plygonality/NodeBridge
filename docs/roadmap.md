# Roadmap

Do not attempt to support every Blender node immediately. Build
vertically: a complete path for a small semantic subset, then widen.

## Milestone 1 — Core IR (current)

* Graph / node / socket / connection model
* IDs and type system
* Validation
* Versioned JSON
* Diagnostics
* Package skeleton, CLI, docs, tests

No Houdini or Unreal generation.

## Milestone 2 — Blender Geometry Nodes extraction

Support a small subset through `bpy`:

* Math
* Vector Math
* Transform Geometry
* Join Geometry
* Set Position

Verify extraction against IR fixtures.

## Milestone 3 — Houdini prototype

Translate the supported subset into Houdini Python.

```
Blender Geometry Nodes → IR → generated hou script → native SOP network
```

This is the first end-to-end proof of concept.

## Milestone 4 — Translation diagnostics

Compatibility scoring and human-readable reports, already sketched by
`TranslationReport` in Milestone 1.

## Milestone 5 — More Geometry Nodes

Incrementally:

* Mesh primitives
* Curve operations
* Instance on Points
* Realize Instances
* Noise
* Attributes
* Selections
* Raycast
* Geometry proximity

## Milestone 6 — Blender add-on

Sidebar panel: select tree, choose target, analyse, export IR, generate
code, copy, save. UI stays out of the translator.

## Milestone 7 — Unreal prototype

Narrow domain, whichever Unreal Python API is more reliable:

* Shader Nodes → Material graph, or
* Geometry Nodes → PCG

## Milestone 8 — Advanced semantic translation

* Compound mappings
* Optimization / rewrite passes
* Target capability analysis
* Alternative implementations
* Reusable translation recipes

## Explicitly later

* Live localhost / IPC bridge
* Round-trip editing
* Maya, Substance, Unity, Godot, USD, MaterialX adapters
* Simulation and repeat zones
* Full shader / compositor coverage
