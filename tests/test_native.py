"""IR serialization still round-trips; native graphs are a separate format."""

from __future__ import annotations

import json

from nodebridge.hosts.native import NativeGraph
from tests.helpers import make_blender_scatter_native


def test_native_graph_json_round_trip() -> None:
    original = make_blender_scatter_native()
    payload = original.as_dict()
    restored = NativeGraph.from_dict(json.loads(json.dumps(payload)))
    assert restored.host == "blender"
    assert len(restored.nodes) == len(original.nodes)
    assert len(restored.links) == len(original.links)
    assert restored.nodes[1].type == "GeometryNodeDistributePointsOnFaces"
