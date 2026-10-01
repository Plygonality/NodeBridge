"""Shader and compositor recipes.

These are consulted only when the source graph system matches. A geometry
SOP network does not pretend to be a material or a compositing network.
"""

from __future__ import annotations

from nodebridge.core.diagnostics import TranslationStatus
from nodebridge.hosts.recipes import NodeTemplate, Recipe


def _one(
    operation: str,
    native_type: str,
    *,
    fidelity: TranslationStatus,
    note: str,
) -> Recipe:
    return Recipe(
        operation=operation,
        fidelity=fidelity,
        nodes=(NodeTemplate(local_id="node", native_type=native_type, inputs=("input0",), outputs=("output0",)),),
        note=note,
    )


SHADER_RECIPES = {
    "shader.principled_surface": _one(
        "shader.principled_surface",
        "mtlxstandard_surface",
        fidelity=TranslationStatus.LOWERED,
        note="MaterialX Standard Surface approximates Principled BSDF. Closures are not numerically identical.",
    ),
    "shader.output": _one(
        "shader.output",
        "mtlxsurfacematerial",
        fidelity=TranslationStatus.LOWERED,
        note="The material output is a MaterialX surface material inside a Material Builder.",
    ),
    "shader.normal": _one(
        "shader.normal",
        "mtlxnormalmap",
        fidelity=TranslationStatus.APPROXIMATE,
        note="A normal map is not Blender's Bump node.",
    ),
    "shader.texcoord": _one(
        "shader.texcoord",
        "mtlxtexcoord",
        fidelity=TranslationStatus.LOWERED,
        note="Texture coordinates are a MaterialX texcoord. UV V is not flipped unless a backend asks.",
    ),
    "procedural.noise": _one(
        "procedural.noise",
        "mtlxnoise3d",
        fidelity=TranslationStatus.LOWERED,
        note="MaterialX noise is not Blender's Noise Texture. The pattern will not match.",
    ),
    "procedural.voronoi": _one(
        "procedural.voronoi",
        "mtlxnoise3d",
        fidelity=TranslationStatus.APPROXIMATE,
        note="Voronoi is approximated with MaterialX noise.",
    ),
    "color.mix": _one(
        "color.mix",
        "mtlxmix",
        fidelity=TranslationStatus.LOWERED,
        note="Mix is a MaterialX mix.",
    ),
    "color.ramp": _one(
        "color.ramp",
        "mtlxmix",
        fidelity=TranslationStatus.APPROXIMATE,
        note="A color ramp is not reproduced. A mix stands in for a two-stop blend.",
    ),
    "texture.sample": _one(
        "texture.sample",
        "mtlximage",
        fidelity=TranslationStatus.LOWERED,
        note="Image texture becomes a MaterialX image node. The image file is not copied.",
    ),
    "math.add": _one("math.add", "mtlxadd", fidelity=TranslationStatus.LOWERED, note="Scalar add as a MaterialX node."),
    "math.multiply": _one(
        "math.multiply", "mtlxmultiply", fidelity=TranslationStatus.LOWERED, note="Scalar multiply as a MaterialX node."
    ),
    "math.subtract": _one(
        "math.subtract", "mtlxsubtract", fidelity=TranslationStatus.LOWERED, note="Scalar subtract as a MaterialX node."
    ),
}

COP_RECIPES = {
    "compositor.input": _one(
        "compositor.input",
        "null",
        fidelity=TranslationStatus.EXACT,
        note="Render-layer inputs become a COP null. The render pass itself is not imported.",
    ),
    "compositor.output": _one(
        "compositor.output",
        "null",
        fidelity=TranslationStatus.LOWERED,
        note="Composite output is a COP null the artist can wire to a ROP.",
    ),
    "compositor.color_correct": _one(
        "compositor.color_correct",
        "colorcorrect",
        fidelity=TranslationStatus.LOWERED,
        note="Color correction uses COP2 colorcorrect. Lift/gamma/gain controls may differ.",
    ),
    "compositor.blur": _one(
        "compositor.blur",
        "blur",
        fidelity=TranslationStatus.LOWERED,
        note="Blur uses the COP2 blur node.",
    ),
    "compositor.mix": _one(
        "compositor.mix",
        "blend",
        fidelity=TranslationStatus.LOWERED,
        note="Mix uses the COP2 blend node.",
    ),
    "compositor.glare": _one(
        "compositor.glare",
        "blur",
        fidelity=TranslationStatus.APPROXIMATE,
        note="Glare has no direct COP2 node. A blur is a stand-in, not a glare kernel.",
    ),
}
