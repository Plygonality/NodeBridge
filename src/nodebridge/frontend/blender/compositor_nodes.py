"""Compositor node lowering.

Compositor operations stay generic. A backend emits a target image graph
only when that target has a reasonable equivalent, and reports the rest.
"""

from __future__ import annotations

from nodebridge.frontend.blender.lower import finish, number, vector
from nodebridge.ir.graph import GraphNode, NodeTree
from nodebridge.ir.operations import field_port, make_operation
from nodebridge.ir.semantic import OperationKind
from nodebridge.ir.types import DataType


def register_all(register) -> None:
    for node_type, function in LOWERERS.items():
        register(node_type)(function)


def _compositor(mode: str, *, output: bool = False):
    def lower(node: GraphNode, tree: NodeTree):
        operation = make_operation(
            id=node.id,
            kind=OperationKind.COMPOSITOR_OPERATION,
            name=node.label or node.name,
            parameters={
                "mode": mode,
                "factor": number(node, "Fac", 1.0),
                "translate": vector(node, "Translate" if node.input("Translate") else "X"),
                "scale": vector(node, "Scale", (1.0, 1.0, 1.0)),
                "angle": number(node, "Angle", 0.0),
                "size": number(node, "Size", 0.5),
                "blend": str(node.properties.get("blend_type", "MIX")).lower(),
            },
            inputs={
                "image": field_port("image", DataType.COLOR),
                "image_b": field_port("image_b", DataType.COLOR),
                "fac": field_port("fac", DataType.FLOAT),
            },
            outputs={} if output else {"image": field_port("image", DataType.COLOR)},
        )
        return finish(
            node,
            operation,
            {"Image": "image", "Image_001": "image_b", "Fac": "fac", "Value": "fac"},
            {} if output else {"Image": "image"},
        )

    return lower


LOWERERS = {
    "CompositorNodeRLayers": _compositor("render_layer"),
    "CompositorNodeImage": _compositor("image"),
    "CompositorNodeComposite": _compositor("composite_output", output=True),
    "CompositorNodeViewer": _compositor("viewer", output=True),
    "CompositorNodeOutputFile": _compositor("file_output", output=True),
    "CompositorNodeGlare": _compositor("glare"),
    "CompositorNodeColorBalance": _compositor("color_balance"),
    "CompositorNodeBrightContrast": _compositor("brightness"),
    "CompositorNodeColorCorrection": _compositor("color_correction"),
    "CompositorNodeHueSat": _compositor("hue"),
    "CompositorNodeExposure": _compositor("exposure"),
    "CompositorNodeTonemap": _compositor("tonemap"),
    "CompositorNodeEllipseMask": _compositor("ellipse_mask"),
    "CompositorNodeBoxMask": _compositor("box_mask"),
    "CompositorNodeMixRGB": _compositor("mix"),
    "CompositorNodeTransform": _compositor("transform"),
    "CompositorNodeScale": _compositor("scale"),
    "CompositorNodeBlur": _compositor("blur"),
    "CompositorNodeFilter": _compositor("filter"),
}
