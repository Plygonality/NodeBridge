# Roadmap

The compiler slice in 0.3 is the Blender add-on, graph IR, semantic IR, and generated Houdini and Unreal Python for a documented subset.

## Next

1. Execute the scatter script in Houdini and adjust parameter names (`npts`, `seed`, Copy to Points packing) against that build.
2. Execute the PCG script in one Unreal editor version and record the pin labels that `add_edge` accepts.
3. Fill subnet contents for nested node groups, and bind spare parameters with `ch()` expressions.
4. Add boolean, curve, and attribute operations one at a time, each with a recipe, a confidence label, and a test.
5. Implement a Houdini frontend that is as thorough as the Blender parser, so translation can run back toward Blender.

## Later

Maya, Bifrost, Substance Designer, Godot, Cinema 4D, and Nuke, each as a host plugin.

Simulation zones, repeat zones, and baking stay unsupported until there is a real target representation.

An optional `TranslationFallbackProvider` may explain gaps later. It is not on the translation path today.
