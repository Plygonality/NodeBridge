# Compatibility matrix

Statuses use the IR translation vocabulary. `TBD` means the backend path
does not exist yet. `—` means the operation is not extracted yet.

Quality labels, once a backend exists:

* Exact
* Equivalent
* Approximated
* Partial
* Unsupported

| Operation | Blender | Houdini | UE5 |
| --- | --- | --- | --- |
| `math.add` | Planned (M2) | TBD (M3) | TBD |
| `math.subtract` | Planned (M2) | TBD (M3) | TBD |
| `math.multiply` | Planned (M2) | TBD (M3) | TBD |
| `math.divide` | Planned (M2) | TBD (M3) | TBD |
| `vector.add` | Planned (M2) | TBD (M3) | TBD |
| `geometry.transform` | Planned (M2) | TBD (M3) | TBD |
| `geometry.join` | Planned (M2) | TBD (M3) | TBD |
| `geometry.modify_position` | Planned (M2) | TBD (M3) | TBD |
| `geometry.instance` | Later (M5) | TBD | TBD |
| `geometry.realize_instances` | Later (M5) | TBD | TBD |
| `procedural.noise` | Later (M5) | TBD | TBD |
| `shader.principled_surface` | Later | TBD | TBD (M7 candidate) |
| `color.mix` | Later | TBD | TBD |

IR-only operations already have names and validation, but no host
mappings. That is intentional: the catalog must grow faster than the
lookup tables.
