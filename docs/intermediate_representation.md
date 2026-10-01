# Intermediate Representation

The IR is the software-independent description of a procedural graph.

It is not Blender Python, not Houdini Python, and not a bag of UI names.

## Document envelope

```json
{
  "nodebridge_version": "0.3.0",
  "ir_version": "1",
  "source": {
    "application": "blender",
    "graph_system": "geometry_nodes"
  },
  "graph": {}
}
```

* `nodebridge_version` — package that wrote the file
* `ir_version` — document schema. Currently `"1"`
* `source` — originating application, independent of node internals
* `graph` — the root graph

Unknown future IR versions are rejected unless a migration is registered.
Additive optional fields (`extracted_at`, `history`) are omitted when empty
so version `"1"` documents remain loadable.

## Core objects

### Graph

A directed graph of operations. It contains nodes, connections, nested
graphs (reusable groups), an interface, and provenance.

`GraphSystem` is `geometry`, `shader`, `compositor`, or `unknown`. Host
graph systems (`geometry_nodes`, `sop`, `pcg`) live on provenance, not
as extra IR graph kinds.

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

### Socket, connection, parameter

Connections refer to socket **IDs**. Sockets record `field_kind`,
`domain`, and a JSON-safe `default`. Parameters are typed constants that
are not sockets.

### Metadata

* **provenance** — application, version, original type/name/id, extraction time
* **UI hints** — position, mute, frames, labels
* **source mapping** — source → IR → target ids
* **history** — translation events (optional)
* **extra** — open-ended JSON-safe bag

## Data types

Builtin types:

`boolean`, `integer`, `float`, `vector2`, `vector3`, `vector4`, `color`,
`string`, `matrix`, `transform`, `geometry`, `mesh`, `curve`,
`point_cloud`, `points`, `instance`, `instances`, `material`, `texture`,
`image`, `shader`, `attribute`, `field`, `object`, `collection`,
`opaque`, `unknown`

Custom types use dotted names (`usd.token`) via `TypeRegistry`.

`opaque` exists for unavoidable host-specific values. It is not a way to
smuggle executable code into the IR.

## Validation

`validate_graph` returns structured diagnostics. It never "fixes" the
graph. Unknown operations are warnings (`NB-W002`), not silent drops.

## Identifiers

IDs are opaque strings. `IdFactory` mints deterministic sequential IDs.
Round-trips preserve IDs exactly.

## Versioning

`ir_version` is a separate axis from the package version. A
`MigrationRegistry` can walk old documents forward. Currently only
version `"1"` is supported.
