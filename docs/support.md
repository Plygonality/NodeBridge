# Support matrix

This is the default classification in NodeBridge 0.3. A graph report can downgrade a single node. For example a cube primitive is exact in Houdini, while a UV sphere is equivalent, and Poisson-disk scatter is approximate.

`yes` in the Blender column means a lowerer or a rewrite rule can produce that operation. `no` means the kind exists for future frontends or targets but the Blender frontend does not emit it today. Reroutes are wiring, not operations.

| Operation | Blender | Houdini | Unreal |
| --- | --- | --- | --- |
| primitive | yes | exact | approximate |
| geometry_input | no | no | unsupported |
| geometry_output | no | no | unsupported |
| transform | yes | exact | approximate |
| transform_points | yes | equivalent | unsupported |
| merge | yes | exact | unsupported |
| separate | yes | approximate | unsupported |
| scatter | yes | equivalent | equivalent |
| instance | yes | equivalent | equivalent |
| realize_instances | yes | equivalent | equivalent |
| attribute_read | yes | exact | unsupported |
| attribute_write | no | approximate | unsupported |
| field | yes | exact | unsupported |
| sample | no | approximate | unsupported |
| interpolate | no | approximate | unsupported |
| noise | yes | approximate | approximate |
| random | yes | equivalent | unsupported |
| map_range | yes | exact | unsupported |
| math | yes | exact | approximate |
| vector_math | yes | exact | unsupported |
| compare | yes | exact | unsupported |
| boolean_math | yes | exact | unsupported |
| selection | no | equivalent | unsupported |
| filter | no | approximate | unsupported |
| delete_geometry | yes | equivalent | unsupported |
| extrude | yes | equivalent | unsupported |
| subdivide | yes | equivalent | unsupported |
| curve | yes | equivalent | unsupported |
| curve_resample | yes | equivalent | unsupported |
| curve_to_mesh | yes | equivalent | unsupported |
| mesh_to_curve | yes | approximate | unsupported |
| raycast | yes | equivalent | unsupported |
| proximity | yes | equivalent | unsupported |
| boolean | yes | equivalent | unsupported |
| material_assignment | yes | equivalent | unsupported |
| texture_sample | yes | approximate | unsupported |
| color_operation | yes | approximate | unsupported |
| shader_operation | yes | equivalent | equivalent |
| compositor_operation | yes | approximate | approximate |
| group_input | yes | equivalent | equivalent |
| group_output | yes | exact | exact |
| reroute | no | no | unsupported |
| subgraph | yes | equivalent | approximate |
| custom_expression | no | equivalent | unsupported |
| unsupported | yes | unsupported | unsupported |
| switch | yes | equivalent | unsupported |
| spatial_noise_mask | yes | approximate | unsupported |
| random_transform | yes | equivalent | approximate |

Houdini `math` is exact when the expression is inlined into a wrangle. The Unreal PCG backend does not build a matching attribute-math node, so the same operation is approximate there and is usually only a comment.

## Blender nodes the parser lowers

Geometry Nodes:

- Group Input, Group Output, node groups
- Join Geometry, Transform Geometry, Set Position
- Position, Normal, Index, ID
- Math, Vector Math, Map Range, Compare, Boolean Math, Switch
- Noise Texture, Voronoi Texture, Random Value
- Distribute Points on Faces, Instance on Points, Realize Instances
- Rotate Instances, Scale Instances, Set Material
- Mesh Cube, Grid, UV Sphere, Ico Sphere, Cylinder, Cone, Circle, Line
- Curve Circle, Line, Quadrilateral, Bezier Segment, Star, Spiral, Arc
- Curve to Mesh, Mesh to Curve, Resample Curve
- Extrude Mesh, Subdivide Mesh, Delete Geometry, Separate Geometry
- Geometry Proximity, Raycast, Mesh Boolean

Shader nodes:

- Principled BSDF, Diffuse BSDF, Glossy BSDF, Emission, Material Output
- Noise, Voronoi, Image, Checker, Mix, Color Ramp
- Bump, Normal Map, Fresnel, Hue/Saturation, Bright/Contrast, Invert
- Math, Vector Math, Map Range, Mapping, RGB, Value, Separate/Combine Color, Texture Coordinate

Compositor nodes:

- Render Layers, Image, Composite, Viewer, File Output
- Glare, Color Balance, Bright/Contrast, Color Correction, Hue Saturation, Exposure, Tonemap
- Ellipse Mask, Box Mask, Mix, Transform, Scale, Blur, Filter
- Compositor node groups

Simulation zones and repeat zones are parsed and reported unsupported. Unknown node types become `unsupported` and stay in the report.

## Houdini implementations

| Confidence | What is generated |
| --- | --- |
| Exact | Group output null, cube as Box, transform as Transform SOP, join as Merge, inlined scalar math, map range via `fit`, compare and boolean math, position/normal/index/id attribute reads |
| Equivalent | Object Merge for a geometry input, Scatter SOP in density mode, Copy to Points, Unpack, extrude, subdivide, delete, resample, sweep, ray, xyzdist proximity, boolean, material path, switch, subnet for a node group, hash-based random, curve generators, set position wrangle |
| Approximate | Noise and spatial noise masks, separate geometry, mesh to curve, shader noise and ramps inside a material builder, COP2 color and blur with a runtime type lookup |
| Unsupported | Simulation and repeat zones, glare, ellipse and box masks, compositor filters, any node without a lowerer, shader nodes that appear inside a SOP graph |

Poisson-disk distribution is approximate density scatter. `booleanop` menu indices are written with a comment because that menu is version-sensitive. Circle SOPs do not set a guessed type menu.

## Unreal implementations

| Confidence | What is generated |
| --- | --- |
| Exact | PCG graph output pin connection for a group output. Material output connection when the expression exists |
| Equivalent | PCG graph input, Surface Sampler, Static Mesh Spawner, realize as the spawner output, Principled material parameters |
| Approximate | Primitive meshes (no PCG cube node; the graph input is the surface and the spawner mesh is assigned by hand), Transform Points for random scale and rotation, noise and ramps in materials, compositor color operations as an emissive material fallback, PCG subgraphs only when `PCGSubgraphSettings` exists |
| Unsupported | Extrude, subdivide, join, delete, curves, raycast, proximity, booleans, simulation, glare, masks, and other operations with no checked Python API |

Missing Unreal classes are resolved with `getattr`. The script logs the gap and does not call a class that is not there.
