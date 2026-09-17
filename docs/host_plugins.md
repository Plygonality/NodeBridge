# Host plugins

Adding a DCC should not require editing every core compiler module.

```python
from nodebridge import register_host

register_host(MayaBifrostHost())  # future
```

Builtin hosts register themselves at import:

* `BlenderHost`
* `HoudiniHost`
* `UnrealHost`

## Contract

A host plugin provides:

| Field | Role |
| --- | --- |
| `id` | Canonical id (`blender`, `houdini`, `unreal`) |
| `display_name` | Human name |
| `versions` | Known application versions |
| `graph_systems` | e.g. `geometry_nodes`, `sop`, `pcg` |
| `capabilities` | Centralized feature tokens |
| `frontend` | native → IR |
| `backend` | IR → native plan / script |
| `implementation_for(op)` | How would this host realize `op`? |

## Native graphs

Frontends consume and backends produce `NativeGraph` objects:

* host-native node types
* parameters and sockets
* links
* no executable code

These are the fixtures CI uses when `bpy` / `hou` / `unreal` are absent.

## Capabilities

Declared once per host (`hosts/<name>/capabilities.py`). The compiler
asks “can target X implement semantic operation Y?” rather than
scattering `if houdini` checks through lowering code.

## What not to do

* Do not add pairwise `Blender → Houdini` modules.
* Do not import `bpy` from a Houdini or Unreal package.
* Do not assume one source node equals one target node.
* Do not silently substitute a “close enough” node.
* Do not put canonical semantics in a host mapping table — mappings
  *reference* catalog operations, they do not define them.

## Adding a host (checklist)

1. Create `nodebridge/hosts/<id>/` with `capabilities.py`, `mappings.py`,
   `frontend.py`, `backend.py`, `host.py`, optional `runtime.py`.
2. Map native types → semantic operations (frontend).
3. Map semantic operations → native fragments (backend recipes).
4. Isolate SDK imports behind importlib in `runtime.py`.
5. Register the host.
6. Add fixture tests. Do not require the DCC in CI.
7. Update `docs/compatibility.md`.
