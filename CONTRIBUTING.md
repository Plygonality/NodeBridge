# Contributing to NodeBridge

## Setup

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

The compiler has no dependencies and must stay importable without Blender, Houdini or Unreal. Only `src/nodebridge/addon/` and `src/nodebridge/frontend/blender/context.py` may import `bpy`. Use relative imports inside the package: Blender loads it as `bl_ext.<repo>.nodebridge`.

## Tests

* `python -m pytest` runs the pure-Python suite.
* `NODEBRIDGE_BLENDER=/path/to/blender python -m pytest tests/test_blender_integration.py` builds the extension zip, installs it into a temporary Blender user directory, and runs `tests/blender/run_in_blender.py`. That script builds the examples and drives the real operators. Separate several Blender executables with `:`.
* `tests/fakes/fake_hou.py` and `fake_unreal.py` are recording stand-ins. They check the structure of generated scripts (call shapes, wiring, pin labels), **not** real Houdini or Unreal behaviour. When you learn something from a live session, encode it in the backend, not only in the fake.

## Golden files

`examples/<name>/expected_report_<target>.txt` and `generated_<target>.py` are compared verbatim by the tests. After an intentional change, run:

```bash
python tools/regenerate_examples.py
```

and review the diff. The same script regenerates `docs/support_matrix.md`.

To refresh the Graph IR fixtures from Blender:

```bash
blender --background --python tests/blender/run_in_blender.py -- --export-fixtures /tmp/fixtures
cp /tmp/fixtures/<name>.graph.json examples/<name>/
```

## Adding support

1. **Operation:** register an `OperationSpec` in `ir/operations.py`, with ports and value roles.
2. **Lifter:** add a function decorated with `@lifts("<bl_idname>", kinds=...)` in `frontend/blender/*_nodes.py`. Look sockets up by name, and read node properties from `node.parameters`.
3. **Translator:** decorate a function with `@translator("<KIND>", target=..., context=..., confidence=..., implementation=..., explanation=..., limitations=...)` in the backend. Add `classify=` when the confidence depends on the configuration.
4. **Rewrite rule:** use `@rewrite_rule(name, description, pattern=... | matcher=...)` in `compiler/rules.py`. A rule must preserve meaning, and its tests must show both when it fires and when it must not.
5. **Tests:** add a lifting test and a backend test that executes the generated code against the fake. Update the golden files.

Rules for backends:

* Use only documented target APIs. If something cannot be built, classify it as UNSUPPORTED or APPROXIMATE, report it, and generate a placeholder or fallback. Never invent an API call.
* Keep generated code readable: one block per operation, meaningful names, comments that explain approximations.
* Never modify or delete existing content in the target application.

## Releasing the add-on

```bash
python tools/build_addon.py                       # dist/nodebridge-<version>.zip
blender --command extension validate dist/nodebridge-<version>.zip
```

Keep the version in `pyproject.toml`, `src/nodebridge/__init__.py` (`__version__` and `bl_info`) and `blender_manifest.toml` in sync.
