# Unreal Engine 5 backend

Status: **contract only (Milestone 1)**. Prototype is Milestone 7.

## Role

Unreal is heterogeneous. NodeBridge must not force every Blender graph
into one Unreal system.

| Source semantics | Candidate Unreal system |
| --- | --- |
| Geometry Nodes | PCG, Geometry Script, Blueprint, procedural mesh |
| Shader Nodes | Material Editor |
| Compositor Nodes | Material / post-process |

Capability tokens:

* `PCG`
* `MATERIAL`
* `GEOMETRY_SCRIPT`
* `BLUEPRINT`
* `POST_PROCESS`

## First prototype (Milestone 7)

Choose the narrower, more reliable Unreal Python surface available at
that time. Likely candidates:

* Blender Shader Nodes → UE5 Material graph
* Blender Geometry Nodes → UE5 PCG

Generated output should start as Python that can be pasted or executed in
Unreal. Direct editor integration comes later.

## Isolation

Unreal Python imports stay inside `nodebridge.backends.unreal`. The rest
of NodeBridge must remain importable without the Unreal editor.
