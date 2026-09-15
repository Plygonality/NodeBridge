# Adding backends

A backend realizes IR operations as a native host graph. It does not
parse Blender files and it does not sit inside `nodebridge.core`.

## Checklist

1. Create `nodebridge/backends/<host>/`.
2. Implement `TargetBackend` (`name`, `capabilities`, `translate_node`, `generate`).
3. Return `GraphFragment` objects — one IR node may become many host nodes.
4. Register translation handlers with `@register_translation`.
5. Keep host SDK imports inside the backend package.
6. Emit readable, deterministic scripts with a NodeBridge header.
7. Attach `SourceMapping` so generated nodes trace back to IR / source.
8. Classify every operation (`EXACT` … `UNSUPPORTED`). Never swallow gaps.
9. Add tests that start from IR fixtures, not from the host application.
10. Update `docs/compatibility.md`.

## What not to do

* Do not add `if blender_type == "GeometryNodeX"` in the backend.
* Do not import `bpy` from a backend.
* Do not assume a 1:1 node mapping.
* Do not generate one giant string-building function.
* Do not silently substitute a "close enough" node.

## Recipes

Reusable multi-node realizations should become independently testable
recipes (Milestone 8). Put them next to the backend, not in core.

## Adding source adapters

The same isolation applies in reverse:

1. Create `nodebridge/adapters/<host>/`.
2. Implement `SourceAdapter.extract()` → `IRDocument`.
3. Map host nodes onto IR operations; store host type names in provenance.
4. Guard nested-group recursion.
5. Keep the host SDK import inside the adapter package.
