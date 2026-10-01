# Translation fidelity

The add-on and the translation report use four public classes: **exact**,
**equivalent**, **approximate**, and **unsupported**. Equivalent covers
internal statuses `LOWERED` and `CUSTOM_CODE`. Approximate covers
`APPROXIMATE` and `BAKED`. Stochastic operations such as scatter and noise
are not reported as exact even when a native node exists, because the
samples are not the same sequence.

Every translated semantic operation is classified. Silence is not a
success. There is **no compatibility percentage**.

Internal statuses, used by recipes:

| Status | Meaning |
| --- | --- |
| `EXACT` | The target implementation preserves the relevant source semantics. |
| `LOWERED` | Equivalent behavior is reconstructed using multiple target-native operations. |
| `APPROXIMATE` | The target cannot exactly reproduce the behavior, but a documented approximation exists. |
| `CUSTOM_CODE` | Native graph nodes alone are insufficient; host-native code (VEX, Python, expressions) is generated. |
| `BAKED` | Some procedural behavior cannot survive translation and must be evaluated or frozen. |
| `UNSUPPORTED` | No defensible translation exists. |

Milestone 1 aliases: `EQUIVALENT` → `LOWERED`; `APPROXIMATED` / `PARTIAL` → `APPROXIMATE`.

## Reports

Human-readable:

```
Translation:
    blender geometry_nodes
    → houdini sop

Operations:
    7 total
    4 EXACT
    2 LOWERED
    0 APPROXIMATE
    1 CUSTOM_CODE
    0 BAKED
    0 UNSUPPORTED
```

JSON is available from `TranslationReport.as_dict()` and
`nodebridge report --json`.

Non-exact conversions always produce diagnostics. Generated host code is
listed separately and is never executed by IR load.

## Baking

Baking is a fallback classification, not the default solution, and not
an implemented evaluator in 0.2.
