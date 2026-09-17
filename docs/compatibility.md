# Compatibility matrix

Statuses use the IR fidelity vocabulary. This table describes the
**implemented construction-plan mappings** for the vertical slice, not
live DCC execution.

There is no compatibility percentage.

| Operation | Blender GN | Houdini SOP | Unreal PCG |
| --- | --- | --- | --- |
| `graph.input` / `graph.output` | EXACT | EXACT | EXACT |
| `geometry.transform` | EXACT | EXACT | EXACT |
| `geometry.join` | EXACT | EXACT | EXACT |
| `geometry.primitive` | EXACT | EXACT | APPROXIMATE |
| `points.distribute` | EXACT | EXACT | EXACT |
| `geometry.instance` | EXACT | LOWERED | APPROXIMATE |
| `geometry.realize_instances` | EXACT | LOWERED | APPROXIMATE |
| `random.float` | EXACT | EXACT | EXACT |
| `random.vector` | EXACT | LOWERED | APPROXIMATE |
| `math.add` (and siblings) | EXACT | CUSTOM_CODE (VEX) | UNSUPPORTED |
| `vector.add` (and siblings) | EXACT | CUSTOM_CODE (VEX) | UNSUPPORTED |
| `math.clamp` | EXACT | CUSTOM_CODE | UNSUPPORTED |
| `geometry.modify_position` | EXACT | CUSTOM_CODE | UNSUPPORTED |
| `attribute.read` / `write` | EXACT | APPROXIMATE | APPROXIMATE |
| `shader.principled_surface` | mapped, not in slice | UNSUPPORTED | UNSUPPORTED |

Unregistered operations compile to a visible `nodebridge.unsupported`
placeholder plus an error diagnostic. They are never silently dropped.

Shader, compositor, and most Geometry Nodes / SOP / PCG catalogs are
**out of scope** for 0.2.
