from nodebridge.ir.graph import (
    GraphEdge,
    GraphNode,
    GraphSocket,
    GraphSystem,
    NodeTree,
    SocketDirection,
)
from nodebridge.ir.semantic import Operation, OperationKind, SemanticGraph, SourceRef
from nodebridge.ir.serialization import IR_VERSION, dumps, loads
from nodebridge.ir.types import DataType


def _tree() -> NodeTree:
    cube = GraphNode(
        id="cube",
        name="Cube",
        node_type="GeometryNodeMeshCube",
        outputs=[
            GraphSocket("Mesh", "Mesh", SocketDirection.OUTPUT, DataType.GEOMETRY),
        ],
        location=(100.0, 40.0),
    )
    output = GraphNode(
        id="output",
        name="Group Output",
        node_type="NodeGroupOutput",
        inputs=[GraphSocket("Geometry", "Geometry", SocketDirection.INPUT, DataType.GEOMETRY)],
    )
    return NodeTree(
        id="tree",
        name="Scatter",
        system=GraphSystem.GEOMETRY,
        nodes=[cube, output],
        edges=[GraphEdge("e0", "cube", "Mesh", "output", "Geometry")],
        metadata={"author": "test"},
    )


def test_graph_ir_json_roundtrip():
    restored = loads(dumps(_tree()))
    assert isinstance(restored, NodeTree)
    assert restored.name == "Scatter"
    assert restored.system is GraphSystem.GEOMETRY
    assert restored.nodes[0].node_type == "GeometryNodeMeshCube"
    assert restored.nodes[0].location == (100.0, 40.0)
    assert restored.edges[0].to_socket == "Geometry"
    assert restored.metadata["author"] == "test"
    assert '"ir_version": "1.0"' in dumps(restored)
    assert IR_VERSION == "1.0"


def test_semantic_ir_json_roundtrip_includes_nested_group():
    inner = SemanticGraph(name="Facade", system=GraphSystem.GEOMETRY, source_tree_id="facade")
    inner.operations.append(
        Operation(
            id="noise",
            kind=OperationKind.NOISE,
            name="Facade Noise",
            parameters={"scale": 4.0},
            source=SourceRef(node_ids=("n1",), node_types=("ShaderNodeTexNoise",), node_names=("Noise",)),
        )
    )
    outer = SemanticGraph(name="Building", system=GraphSystem.GEOMETRY)
    outer.operations.append(
        Operation(id="group", kind=OperationKind.SUBGRAPH, name="Facade", subgraph=inner)
    )
    restored = loads(dumps(outer))
    assert restored.operations[0].kind is OperationKind.SUBGRAPH
    assert restored.operations[0].subgraph.operations[0].parameters["scale"] == 4.0
    assert restored.operations[0].subgraph.operations[0].source.node_types == ("ShaderNodeTexNoise",)


def test_loading_json_does_not_require_a_target_runtime():
    text = dumps(_tree())
    assert "import hou" not in text
    assert "import unreal" not in text
    assert loads(text).nodes[0].id == "cube"
