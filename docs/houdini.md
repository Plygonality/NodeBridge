# Houdini host

Status: **frontend and backend implemented** for a small SOP subset, at
the construction-plan / fixture level. Live `hou` execution is optional
and not exercised in CI.

```
SOP network  ↕  HoudiniFrontend / HoudiniBackend  ↕  Semantic IR
```

## Frontend

Maps SOP types such as `scatter`, `copytopoints`, `unpack`, `xform`,
`attribrandomize`, `box`, and `null` (input/output) onto semantic
operations. Native type names stay in provenance.

## Backend

Uses native SOPs whenever a defensible mapping exists.

| Semantic operation | Realization | Fidelity |
| --- | --- | --- |
| `geometry.transform` | `xform` | EXACT |
| `points.distribute` | `scatter` | EXACT |
| `geometry.instance` | `copytopoints` | LOWERED |
| `geometry.realize_instances` | `unpack` → `convert` | LOWERED |
| `random.vector` | `attribrandomize` → wrangle bind | LOWERED |
| `math.*` / `vector.*` | Attribute Wrangle + generated VEX | CUSTOM_CODE |
| `geometry.modify_position` | Attribute Wrangle writing `@P` | CUSTOM_CODE |

VEX is not used merely because a SOP mapping would be inconvenient.
Scalar/vector field math has no general SOP; those ops are explicitly
`CUSTOM_CODE`.

Generated VEX is deterministic and covered by tests. It is stored as
data on the construction plan and in the translation report. Loading IR
does not run it.

## Scripts

`HoudiniBackend.generate()` emits `hou` Python that creates a geo
container and SOP nodes. Execute it only inside Houdini.

## Isolation

`hou` is loaded via importlib from `hosts/houdini/runtime.py` only.
