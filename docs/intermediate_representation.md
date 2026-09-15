# Intermediate Representation

The IR is the software-independent description of a procedural graph.

It is not Blender Python, not Houdini Python, and not a bag of UI names.

## Document envelope

```json
{
  "nodebridge_version": "0.1.0",
  "ir_version": "1",
  "source": {
    "application": "blender",
    "graph_system": "geometry"
  },
  "graph": {}
}
```

* `nodebridge_version` — package that wrote the file
* `ir_version` — document schema. Currently `"1"`
* `source` — originating application, independent of node internals
* `graph` — the root graph

Unknown future IR versions are rejected unless a migration is registered.

## Core objects

### Graph

A directed graph of operations. It contains:

* nodes
* connections
* nested graphs (reusable groups)
* an interface (exposed inputs/outputs)
* provenance

`GraphSystem` is `geometry`, `shader`, `compositor`, or `unknown`.

### Node

```text
IRNode(
    id="node_0024",
    operation="geometry.transform",
    inputs={...},
    outputs={...},
    parameters={...},
    metadata={...}
)
```

`operation` is a dotted semantic name. Source node types belong in
`metadata.provenance.original_type`.

A group call uses `operation="graph.group"` and `nested_graph_id`.

### Socket

A typed port. Connections refer to socket **IDs**, not display names.

Sockets also record:

* `field_kind` — `value`, `field`, or `unknown`
* `domain` — geometry domain when the value is a field
* `default` — JSON-safe constant when unconnected

### Connection

```text
IRConnection(
    source_node="node_0010",
    source_socket="geometry",
    target_node="node_0024",
    target_socket="geometry"
)
```

Endpoints are explicit. There is no implicit "first socket" wiring.

### Parameter

A typed constant that is not a socket (math mode, flags, enum values).

### Metadata

Split into:

* **provenance** — application, original type/name/id
* **UI hints** — position, mute, frames, labels
* **source mapping** — source → IR → target ids
* **extra** — open-ended, JSON-safe bag

## Data types

Builtin types:

`float`, `integer`, `boolean`, `vector2`, `vector3`, `vector4`, `color`,
`string`, `matrix`, `geometry`, `mesh`, `curve`, `point_cloud`,
`instance`, `material`, `texture`, `image`, `shader`, `unknown`

Custom types use dotted names (`usd.token`) via `TypeRegistry`.

Compatibility:

| Relation | Example |
| --- | --- |
| Identical | `float` → `float` |
| Equivalent | `mesh` → `geometry` |
| Convertible | `float` → `integer`, `vector3` → `color` |
| Incompatible | `shader` → `geometry` |

Unknown types are treated as convertible so they survive extraction, but
they produce diagnostics.

## Operations

Operations live in `OperationRegistry`. The seed catalog includes math,
vector, a few geometry ops, attributes, procedural patterns, shaders,
color, and graph interface ops.

Unknown operations are allowed in the IR. Validation emits `NB-W002`
rather than dropping the node. That is required for honest reporting.

## Validation

`validate_graph` returns structured diagnostics. Errors include missing
endpoints, direction mismatches, duplicate IDs, and broken group
references. Warnings include unknown operations, type mismatches, data-
flow cycles, and multiple connections into one input.

Validation never "fixes" the graph.

## Translation quality

Every translated operation should later carry one of:

* `EXACT`
* `EQUIVALENT`
* `APPROXIMATED`
* `PARTIAL`
* `UNSUPPORTED`

Milestone 1 implements the report objects. Compatibility analysis marks
unregistered operations as `UNSUPPORTED` so silence is impossible.

## Identifiers

IDs are opaque strings (`node_0001`, or a caller-supplied source id).
`IdFactory` mints deterministic sequential IDs for tests and generators.
Round-trips preserve IDs exactly.

## Versioning

`ir_version` is a separate axis from the package version. A
`MigrationRegistry` can walk old documents forward. Milestone 1 supports
only version `"1"` and ships no automatic migrations.
