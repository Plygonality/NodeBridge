# Repository audit (0.2 → 0.3 rebuild)

This records what existed before the 0.3 rebuild, what was kept, and why
the rest was removed. 0.3 repositions NodeBridge as a Blender add-on that
compiles Blender node trees into native Houdini / Unreal Engine 5 code.

## What 0.2 contained

| Area | State in 0.2 | Decision |
| --- | --- | --- |
| `core/` (graph, node, socket, types, catalog, operations) | One string-keyed IR mixing graph structure and semantics | Replaced by separate Graph IR (`ir/graph.py`) and Semantic IR (`ir/semantic.py`) |
| `adapters/blender/*` | Older duplicate of `hosts/blender` mappings | Removed (duplicated mapping system) |
| `translators/*` | Third mapping layer (rules, compatibility, registry) | Removed; replaced by `translation/registry.py` |
| `hosts/*/frontend.py`, `hosts/*/runtime.py` | Fixture / duck-typed parsers for Blender, Houdini, Unreal | Blender parser rewritten against the real `bpy` API; Houdini/Unreal frontends removed (no real API coverage) and left as a documented extension point (`frontend/base.py`) |
| `hosts/*/backend.py`, `backends/*` | Two parallel backend trees; generated scripts had wiring defects (e.g. Copy to Points input 1 assigned twice, unconnected Attribute Randomize, Blender sockets wired to wrong inputs) | Replaced by `backend/houdini` and `backend/unreal` translator registries |
| `hosts/blender/backend.py` (IR → Blender) | Blender as a target | Removed: 0.3 uses Blender as the source application |
| `compiler/*` | validate → normalize → plan → lower | Rebuilt: dependency analysis, Graph IR normalization, lifting, rewrite engine, capability resolution |
| `cli/main.py` | Worked on fixtures | Kept as a concept; rewritten for Graph IR documents |
| `blender_addon/` | `register()` was a no-op; panels/operators were docstrings | Replaced by the real add-on in `src/nodebridge/addon/` |
| `export/*` | Unused | Removed |
| `examples/*` | One real fixture pair, three placeholder READMEs | Replaced by four example graphs built in real Blender, with expected reports |
| `tests/*` | Tested the removed architecture | Replaced |

## Checks performed

* No secrets, API keys, or credentials were found.
* No hardcoded absolute paths were found.
* No AI / LLM integration existed. 0.3 adds an optional
  `TranslationFallbackProvider` interface that defaults to `None`.
* The package had no runtime dependencies and still has none.
