# Example: procedural shader

Noise → color ramp → roughness and bump → Principled BSDF → material output.

Houdini builds a Material Builder. Unreal builds a Material asset with `MaterialEditingLibrary`.

Noise and the Principled closure are not numerically identical to Blender. The color ramp is approximate.
