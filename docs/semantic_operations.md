# Semantic operations

Operations describe *intent*. They are not Blender, Houdini, or Unreal
node type names.

The catalog is intentionally narrow. A coherent vocabulary is more
valuable than a huge collection of unreliable mappings.

## Categories (seed)

### Graph

* `graph.input`, `graph.output`, `graph.group`

### Geometry

* `geometry.transform`, `geometry.join`, `geometry.separate`
* `geometry.instance` (alias: `instance`)
* `geometry.realize_instances`
* `geometry.modify_position`, `geometry.primitive`, `geometry.delete`

### Point processing

* `points.distribute` (aliases: `surface_sample`, `geometry.distribute_points`)

### Math

* `math.add`, `math.subtract`, `math.multiply`, `math.divide`
* `math.min`, `math.max`, `math.clamp`, `math.map_range`, `math.power`

### Vector

* `vector.add`, `vector.subtract`, `vector.scale`, `vector.normalize`
* `vector.dot`, `vector.cross`, `vector.distance`

### Randomness

* `random.float`, `random.integer`, `random.vector`

### Attributes / fields

* `attribute.read`, `attribute.write`, `attribute.evaluate`, `attribute.transfer`

Other seed entries (`procedural.noise`, shader/color ops) exist in the
registry so unknown graphs can round-trip names, but they are **not**
part of the implemented vertical slice.

## Machine-readable schema

Each `OperationSpec` records:

* identifier, category, description, aliases
* input / output / parameter schemas
* determinism and side effects
* domain, field, and instance behavior
* required capabilities

Query the catalog:

```python
from nodebridge.core.operations import DEFAULT_OPERATION_REGISTRY

spec = DEFAULT_OPERATION_REGISTRY.get("points.distribute")
print(spec.as_dict())
```

## Host mappings are not the catalog

`GeometryNodeDistributePointsOnFaces` → `points.distribute` is a Blender
frontend rule. `points.distribute` → Scatter SOP is a Houdini backend
recipe. Neither belongs in the semantic registry.

## Adding an operation

1. Register an `OperationSpec` (name, ports, capabilities).
2. Add frontend resolvers on hosts that can *author* it.
3. Add lowering recipes on hosts that can *implement* it.
4. Classify fidelity. If there is no honest mapping, leave it unsupported.
