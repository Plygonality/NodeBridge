# Example: procedural building

Grid → extrude → subdivide → set material.

Houdini lowers extrude to PolyExtrude (equivalent) and subdivide to Subdivide (approximate). Unreal has no PCG extrude or subdivide in this slice, so those operations are unsupported in `unreal_report.txt` and remain comments in `unreal_generated.py`.
