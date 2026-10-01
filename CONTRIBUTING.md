# Contributing

NodeBridge is a compiler. A change should add or adjust one of these, and a test that locks the behavior:

- a graph-IR parse
- a semantic operation
- a rewrite rule
- a host recipe with a confidence label
- generated-script structure

Do not add a direct `Blender node → Houdini node` table as the architecture. Source types belong in the Blender resolver. Semantic names belong in the catalog. Target node types belong in recipes.

Do not import `bpy`, `hou`, or `unreal` from the compiler, IR, or common modules. The Blender panel may import `bpy`. Generated scripts may mention `hou` and `unreal` as text.

Unsupported behavior stays in the report and in script comments. Do not omit it.

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

Classify new translations as exact, equivalent, approximate, or unsupported, and say why in the recipe note. Do not claim identical random samples or identical noise.
