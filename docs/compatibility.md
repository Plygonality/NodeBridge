# Compatibility

Confidence is one of exact, equivalent, approximate, or unsupported. There is no compatibility percentage.

Host-wide availability is `Host.implementation_for`. A shader or compositor operation can still lower when the graph system matches, even if the geometry SOP table does not list it. The translation report for a real graph is the source of truth.

## Geometry, both targets

| Operation | Houdini | Unreal PCG |
| --- | --- | --- |
| Transform | Exact | Exact |
| Join | Exact | Exact |
| Scatter | Equivalent | Equivalent |
| Instance | Equivalent | Approximate |
| Realize instances | Equivalent | Approximate |
| Math / vector math | Equivalent (VEX) | Unsupported |
| Noise | Equivalent | Unsupported in PCG, equivalent in materials |
| Raycast | Equivalent | Unsupported |
| Subdivide | Approximate | Unsupported |
| Simulation | Unsupported | Unsupported |

## Shaders

Houdini MaterialX and Unreal Materials cover Principled, noise, mix, math, texcoord, and image sample at equivalent or approximate confidence. Color ramps and bump are approximate.

## Compositor

Houdini COP2 covers input, color correction, blur, and mix. Glare is approximate. Masks are unsupported. Unreal is unsupported for the compositor system.

## Coordinates

| | Up | Handedness |
| --- | --- | --- |
| Blender | Z | Right |
| Houdini | Y | Right |
| Unreal | Z | Left |

Blender → Houdini position: `(x, z, -y)`.
Blender → Unreal position: `(y, x, z)`.
Blender meters → Unreal centimeters: multiply by 100.
Blender radians → Houdini and Unreal degrees.

## Random

`random_unit(seed, element_id)` is NodeBridge's sequence. It is stable in Python. The VEX source in `nodebridge.common.random` is a line-by-line port and is not executed in CI. Host scatter nodes do not use it, and the report says the samples may differ.
