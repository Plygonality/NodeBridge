# Support matrix

Generated from translator metadata by `tools/regenerate_examples.py` (do not edit by hand).
Each cell shows the default confidence and implementation; some translators downgrade the
confidence for specific configurations (see the translation report).

| Operation | Category | Houdini | Unreal Engine 5 |
| --- | --- | --- | --- |
| `BLUR` | compositor | equivalent (cop2: blur COP) | unsupported |
| `BRIGHT_CONTRAST` | compositor | approximate (cop2: bright COP) | approximate (postprocess: Color contrast / offset) |
| `COLOR_BALANCE` | compositor | approximate (cop2: colorcorrect COP) | approximate (postprocess: Color grading gain / gamma / offset) |
| `COLOR_CORRECTION` | compositor | unsupported | approximate (postprocess: Color grading saturation / contrast / gamma / gain) |
| `COMPOSITE_OUTPUT` | compositor | equivalent (cop2: null OUT (display)) | equivalent (postprocess: unbound Post Process Volume) |
| `COMPOSITOR_OPERATION` | compositor | unsupported | unsupported |
| `ELLIPSE_MASK` | compositor | unsupported | unsupported |
| `EXPOSURE` | compositor | exact (cop2: bright COP) | equivalent (postprocess: Exposure compensation) |
| `GAMMA` | compositor | exact (cop2: gamma COP) | equivalent (postprocess: Color gamma) |
| `GLARE` | compositor | unsupported | approximate (postprocess: Bloom intensity / threshold) |
| `HUE_SATURATION` | compositor | equivalent (cop2: hsv COP) | approximate (postprocess: Color saturation) |
| `IMAGE_INPUT` | compositor | equivalent (cop2: file COP) | unsupported |
| `INVERT` | compositor | exact (cop2: invert COP) | unsupported |
| `LENS_DISTORTION` | compositor | unsupported | approximate (postprocess: Chromatic aberration) |
| `RENDER_LAYER` | compositor | approximate (cop2: file COP) | equivalent (postprocess: rendered scene) |
| `VIGNETTE` | compositor | unsupported | approximate (postprocess: Vignette intensity) |
| `ALIGN_ROTATION` | field | equivalent (sop: VEX dihedral()) | unsupported (pcg: none) |
| `ATTRIBUTE_READ` | field | exact (sop: VEX point()/prim()) | unsupported (pcg: none) |
| `BOOLEAN_MATH` | field | exact (sop: VEX logic) | unsupported (pcg: none) |
| `COLOR_OPERATION` | field | exact (mtlx: mtlxsubtract (invert)) | exact (material: OneMinus / Desaturation) |
| `COLOR_RAMP` | field | exact (mtlx: mtlxremap + mtlxclamp + mtlxmix chain)<br>exact (sop: VEX piecewise interpolation) | exact (material: Lerp chain with saturated remaps)<br>unsupported (pcg: none) |
| `COMBINE_VECTOR` | field | exact (mtlx: mtlxcombine3)<br>exact (sop: VEX set()) | exact (material: AppendVector)<br>unsupported (pcg: none) |
| `COMPARE` | field | exact (sop: VEX comparison) | unsupported (pcg: none) |
| `FIELD_INPUT` | field | equivalent (mtlx: mtlxposition / mtlxnormal / mtlxtexcoord)<br>exact (sop: VEX @P / @N / @ptnum / id) | equivalent (material: TextureCoordinate / LocalPosition / WorldPosition / VertexNormalWS)<br>unsupported (pcg: none) |
| `INTERPOLATE` | field | unsupported | unsupported (pcg: none) |
| `MAP_RANGE` | field | exact (mtlx: mtlxremap (+ mtlxclamp))<br>exact (sop: VEX fit()/efit()) | exact (material: Subtract / Divide / Lerp)<br>unsupported (pcg: none) |
| `MATH` | field | exact (mtlx: MaterialX math nodes)<br>exact (sop: VEX arithmetic) | exact (material: Material arithmetic expressions)<br>unsupported (pcg: none) |
| `MIX` | field | approximate (cop2: over / multiply / add COP)<br>exact (mtlx: mtlxmix)<br>exact (sop: VEX lerp()) | exact (material: LinearInterpolate)<br>unsupported (pcg: none) |
| `NOISE` | field | approximate (mtlx: mtlxfractal3d)<br>approximate (sop: VEX fractal noise()) | approximate (material: MaterialExpressionNoise)<br>unsupported (pcg: none) |
| `PROCEDURAL_TEXTURE` | field | unsupported | unsupported |
| `PROXIMITY` | field | exact (sop: VEX xyzdist()/nearpoint()) | unsupported (pcg: none) |
| `RANDOM` | field | equivalent (sop: VEX nb_random(seed, id)) | unsupported (pcg: none) |
| `RAYCAST` | field | equivalent (sop: VEX intersect()) | unsupported (pcg: none) |
| `SAMPLE` | field | unsupported | unsupported (pcg: none) |
| `SEPARATE_VECTOR` | field | exact (mtlx: mtlxseparate3)<br>exact (sop: VEX components) | exact (material: ComponentMask)<br>unsupported (pcg: none) |
| `SPATIAL_NOISE_MASK` | field | approximate (sop: VEX fractal noise mask) | approximate (pcg: folded into Spatial Noise + Density Filter) |
| `VECTOR_MATH` | field | exact (mtlx: MaterialX vector nodes)<br>exact (sop: VEX vector math) | exact (material: Material vector expressions)<br>unsupported (pcg: none) |
| `VORONOI` | field | approximate (mtlx: mtlxworleynoise3d)<br>approximate (sop: VEX vnoise()) | approximate (material: MaterialExpressionNoise (Voronoi))<br>unsupported (pcg: none) |
| `ATTRIBUTE_WRITE` | geometry | exact (sop: attribwrangle) | unsupported (pcg: none) |
| `BOOLEAN` | geometry | equivalent (sop: boolean SOP) | unsupported (pcg: none) |
| `COLLECTION_REFERENCE` | geometry | approximate (sop: object_merge SOP) | unsupported |
| `CURVE` | geometry | equivalent (sop: line / circle SOP / VEX spiral) | unsupported (pcg: none) |
| `CURVE_RESAMPLE` | geometry | equivalent (sop: resample SOP) | unsupported (pcg: none) |
| `CURVE_TO_MESH` | geometry | approximate (sop: sweep SOP) | unsupported (pcg: none) |
| `DELETE_GEOMETRY` | geometry | exact (sop: attribwrangle removepoint()/removeprim()) | approximate (pcg: PCGSpatialNoiseSettings + PCGDensityFilterSettings) |
| `EXTRUDE` | geometry | exact (sop: polyextrude SOP) | unsupported (pcg: none) |
| `FILTER` | geometry | unsupported | unsupported |
| `GEOMETRY_INPUT` | geometry | equivalent (sop: object_merge + placeholder grid + switch) | equivalent (pcg: PCG graph Input node) |
| `GEOMETRY_OUTPUT` | geometry | exact (sop: null OUT (display/render)) | equivalent (pcg: PCG graph Output node) |
| `INSTANCE` | geometry | exact (sop: copytopoints SOP (Pack and Instance)) | approximate (pcg: PCGStaticMeshSpawnerSettings) |
| `INSTANCE_TRANSFORM` | geometry | equivalent (sop: attribwrangle on packed primitive transforms) | unsupported (pcg: none) |
| `MATERIAL_ASSIGNMENT` | geometry | equivalent (sop: material SOP) | unsupported (pcg: none) |
| `MERGE` | geometry | exact (sop: merge SOP) | equivalent (pcg: PCGMergeSettings) |
| `MESH_TO_CURVE` | geometry | equivalent (sop: convertline SOP) | unsupported (pcg: none) |
| `MESH_TO_POINTS` | geometry | exact (sop: attribwrangle removeprim()) | unsupported (pcg: none) |
| `OBJECT_REFERENCE` | geometry | approximate (sop: object_merge SOP) | unsupported (pcg: none) |
| `PRIMITIVE` | geometry | exact (sop: box / grid / sphere / tube / line / circle SOP) | unsupported (pcg: none) |
| `RANDOM_TRANSFORM` | geometry | equivalent (sop: attribwrangle writing orient / scale) | equivalent (pcg: PCGTransformPointsSettings) |
| `REALIZE_INSTANCES` | geometry | exact (sop: unpack SOP) | approximate (pcg: none (pass-through)) |
| `SCATTER` | geometry | equivalent (sop: scatter SOP) | equivalent (pcg: PCGSurfaceSamplerSettings) |
| `SELECTION` | geometry | unsupported | unsupported |
| `SEPARATE` | geometry | exact (sop: two attribwrangles (keep / remove selection)) | approximate (pcg: Spatial Noise + Density Filter (x2)) |
| `SET_POSITION` | geometry | exact (sop: attribwrangle writing @P) | equivalent (pcg: PCGTransformPointsSettings (offset)) |
| `SUBDIVIDE` | geometry | equivalent (sop: subdivide SOP) | unsupported (pcg: none) |
| `SWITCH` | geometry | exact (sop: switch SOP / VEX ternary) | unsupported (pcg: none) |
| `TRANSFORM` | geometry | exact (sop: xform SOP) | equivalent (pcg: PCGTransformPointsSettings (fixed values)) |
| `TRANSFORM_POINTS` | geometry | exact (sop: attribwrangle) | equivalent (pcg: PCGTransformPointsSettings) |
| `BUMP` | shader | equivalent (mtlx: mtlxheighttonormal) | approximate (material: DDX/DDY screen-space bump) |
| `MAPPING` | shader | exact (mtlx: mtlxmultiply + mtlxadd) | exact (material: Multiply + Add) |
| `MATERIAL_OUTPUT` | shader | exact (mtlx: material path /mat/<name>) | exact (material: Material output pins) |
| `NORMAL_MAP` | shader | equivalent (mtlx: mtlxnormalmap) | equivalent (material: Normal map with green flip) |
| `SHADER_BSDF` | shader | equivalent (mtlx: mtlxstandard_surface) | equivalent (material: Default Lit material attributes) |
| `SHADER_MIX` | shader | approximate (mtlx: first shader only) | approximate (material: first shader only) |
| `SHADER_OPERATION` | shader | unsupported | unsupported |
| `TEXTURE_COORDINATE` | shader | unsupported | unsupported |
| `TEXTURE_SAMPLE` | shader | equivalent (mtlx: mtlximage) | equivalent (material: TextureSample) |
| `SUBGRAPH` | structural | exact (sop: subnet SOP with promoted parameters) | unsupported |
