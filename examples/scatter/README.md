# Scattering vertical slice

A minimal procedural scatter:

Mesh → distribute points → random scale → instance → realize instances

This directory holds **native graph fixtures**, not live `.blend` / `.hip`
files. They exercise frontends and backends without Blender or Houdini
installed.

```bash
nodebridge translate examples/scatter/blender_scatter.native.json --source blender --target houdini
nodebridge translate examples/scatter/houdini_scatter.native.json --source houdini --target blender
```

The generated SOP / Geometry Nodes graphs will not have identical
topology. The semantic operations should match the documented slice.
