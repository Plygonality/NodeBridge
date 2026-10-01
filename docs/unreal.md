# Unreal Engine 5 backend

Generated scripts run inside the Unreal Editor with the Python Script Plugin. They are not a standalone "UE5 code window."

## PCG

For Geometry Nodes the script:

1. Checks that `unreal.PCGGraphFactory` exists.
2. Creates a PCG graph asset under `/Game/NodeBridge`.
3. Checks that `add_node_of_type` exists, and raises if it does not.
4. Adds documented settings classes such as `PCGSurfaceSamplerSettings`, `PCGStaticMeshSpawnerSettings`, and `PCGTransformPointsSettings`.
5. Calls `add_edge` only for nodes that were actually created.
6. Saves the asset.

Surface sampling is equivalent: the point set will not match Blender. Static mesh spawning is approximate. Extrude, subdivide, curves, raycast, proximity, and general math are unsupported and stay in the script as comments plus the translation report.

Pin names are the labels NodeBridge recorded. They are version-sensitive. The script does not probe private pin APIs.

## Materials

Shader graphs use `AssetTools` and `MaterialEditingLibrary` to create a Material and expression nodes (`MaterialExpressionNoise`, `MaterialExpressionLinearInterpolate`, math expressions, texture sample, normal map). Principled BSDF is approximate. Noise does not match Blender.

## Compositor

The generated script raises `RuntimeError` and lists the source operations. It does not create a post-process material as a stand-in for the compositor.
