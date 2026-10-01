# Example: compositor

Render Layers → Glare → Color Balance → Composite, plus an ellipse mask.

Houdini targets COP2. Glare is an approximate blur. The ellipse mask is unsupported.

Unreal does not receive a fake post-process graph. `unreal_generated.py` raises and lists the operations.
