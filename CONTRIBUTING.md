# Contributing

NodeBridge translates procedural meaning through an intermediate representation. A change that maps one Blender node name onto one Houdini node name, and stops there, does not belong in the core.

## Layout

- `frontend/` reads a DCC graph into graph IR and semantic IR.
- `ir/` is the DCC-independent representation.
- `compiler/` orders the graph, rewrites patterns, validates, and writes the report.
- `translation/` is the translator registry and confidence model.
- `backend/` generates code.
- `common/` holds coordinates, units, names, and the deterministic hash.
- `addon/` is the Blender N-panel. It is imported only when Blender calls `register`.

## Add a Blender node

1. Add a lowerer in `frontend/blender/geometry_nodes.py`, `shader_nodes.py`, or `compositor_nodes.py`.
2. Store a semantic `OperationKind`, parameters, and ports. Keep the Blender idname on `SourceRef` only.
3. Register a translator for each target that can implement it.
4. If the target cannot implement it, leave it unsupported. The report must name it.
5. Add a duck-typed fixture in `nodebridge/examples/graphs.py` or a test, and assert the generated script with `ast.parse`.

## Add a target

Implement `supports`, `classify`, and `generate`. Register translators with `@translator`. Do not edit the parser to mention the new DCC.

## Tests

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
```

Tests do not start Blender, Houdini, or Unreal. They parse fixtures and check the generated Python. Do not claim those applications were executed unless you ran them.

## Generated code

Scripts must be readable, create new networks, and avoid editing unrelated scene nodes. Houdini SOP scripts destroy children only of the geometry node they just created. Unsupported work stays visible as a comment, a null, or a report entry.
