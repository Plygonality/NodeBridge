"""VEX helper library emitted into wrangles on demand.

Field expressions are evaluated in Blender's frame (Z-up) so Blender math
keeps its meaning (e.g. ``Separate XYZ -> Z`` is height). Conversions at
the boundary match :data:`nodebridge.common.coordinates.HOUDINI`:
``(x, y, z)_blender -> (x, z, -y)_houdini``.
"""

from ...common.random import VEX_SOURCE as RANDOM

COORDINATES = """\
// NodeBridge coordinate conversion (Blender Z-up <-> Houdini Y-up).
vector nb_b(vector h) { return set(h.x, -h.z, h.y); }
vector nb_h(vector b) { return set(b.x, b.z, -b.y); }
vector nb_bs(vector h) { return set(h.x, h.z, h.y); }
vector nb_hs(vector b) { return set(b.x, b.z, b.y); }
vector4 nb_orient_h(vector euler_b) {
    vector4 qb = eulertoquaternion(euler_b, XFORM_XYZ);
    vector4 c = quaternion(radians(-90.0), {1, 0, 0});
    return qmultiply(qmultiply(c, qb), qinvert(c));
}
"""

NOISE = """\
// Fractal noise in the spirit of Blender's fBm Noise Texture (not numerically identical).
float nb_fbm(vector p; float detail; float roughness; float lacunarity) {
    float fscale = 1.0;
    float amp = 1.0;
    float maxamp = 0.0;
    float sum = 0.0;
    int octaves = int(floor(clamp(detail, 0.0, 15.0)));
    for (int i = 0; i <= octaves; i++) {
        sum += (noise(p * fscale) * 2.0 - 1.0) * amp;
        maxamp += amp;
        amp *= clamp(roughness, 0.0, 1.0);
        fscale *= lacunarity;
    }
    float rmd = detail - floor(detail);
    if (rmd > 0.0) {
        sum += (noise(p * fscale) * 2.0 - 1.0) * amp * rmd;
        maxamp += amp * rmd;
    }
    return maxamp > 0.0 ? 0.5 * sum / maxamp + 0.5 : 0.5;
}
"""

PRIMITIVES = """\
vector nb_prim_center(int geo; int prim) {
    int pts[] = primpoints(geo, prim);
    vector c = {0, 0, 0};
    foreach (int pt; pts) c += point(geo, "P", pt);
    return len(pts) > 0 ? c / len(pts) : c;
}
"""

ROTATION = """\
vector nb_euler_from_normal(vector n_b) {
    vector4 q = dihedral({0, 0, 1}, normalize(n_b));
    return quaterniontoeuler(q, XFORM_XYZ);
}
vector nb_align_euler(vector euler_b; vector axis; vector target; float factor) {
    if (length(target) == 0.0) return euler_b;
    vector4 q = eulertoquaternion(euler_b, XFORM_XYZ);
    vector current = qrotate(q, axis);
    vector4 d = dihedral(normalize(current), normalize(target));
    vector4 r = qmultiply(slerp({0, 0, 0, 1}, d, clamp(factor, 0.0, 1.0)), q);
    return quaterniontoeuler(r, XFORM_XYZ);
}
"""

SAFE = """\
vector nb_safe_div3(vector a; vector b) {
    return set(b.x != 0 ? a.x / b.x : 0.0, b.y != 0 ? a.y / b.y : 0.0, b.z != 0 ? a.z / b.z : 0.0);
}
"""

LIBRARIES = {
    "coordinates": COORDINATES,
    "random": RANDOM,
    "noise": NOISE,
    "primitives": PRIMITIVES,
    "rotation": ROTATION,
    "safe": SAFE,
}
ORDER = ["coordinates", "random", "noise", "primitives", "rotation", "safe"]
