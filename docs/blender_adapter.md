# Blender adapter

Status: **contract only (Milestone 1)**. Extraction starts in Milestone 2.

## Role

The Blender adapter is a *source adapter*. It inspects `bpy` node trees
and emits NodeBridge IR. It must not generate Houdini or Unreal code.

```
bpy node tree → BlenderExtractor.extract() → IRDocument
```

`import bpy` is allowed only inside `nodebridge.adapters.blender`.

## Planned extraction

### Geometry Nodes (Milestone 2 subset)

* nodes, sockets, links
* default values and socket types
* node properties, positions, labels, mute
* group inputs / outputs
* nested groups with cycle guards

Initial operations:

* Math
* Vector Math
* Transform Geometry
* Join Geometry
* Set Position

### Later

Shader nodes, compositor nodes, modifiers, simulation / repeat zones,
attributes, fields, frames.

## Mapping rule

Blender `bl_idname` values become provenance, not IR operations.

| Blender type | IR operation | Provenance |
| --- | --- | --- |
| `GeometryNodeTransform` | `geometry.transform` | `original_type=GeometryNodeTransform` |
| `ShaderNodeMath` (ADD) | `math.add` | `original_type=ShaderNodeMath` |
| unknown | `unknown` or pass-through name | always preserved |

## Add-on

`blender_addon/` is a UI shell for Milestone 6. Operators and panels must
call the library; they must not reimplement translation.
