"""Readable Houdini Python for SOP, material, and COP networks.

The generated text is meant to be pasted into Houdini's Python Source
Editor. NodeBridge never executes it. Host node types that this generator
names are checked at runtime inside the script; a missing type raises
instead of being skipped.
"""

from __future__ import annotations

from nodebridge.common.coordinates import convert_euler, convert_position, convert_scale
from nodebridge.common.names import sanitize_identifier
from nodebridge.common.random import vex_hash_random
from nodebridge.common.units import convert_angle
from nodebridge.core.graph import GraphSystem, IRGraph
from nodebridge.hosts.native import NativeGraph, NativeNode
from nodebridge.ir.versioning import PACKAGE_VERSION
from nodebridge.translation.confidence import Confidence
from nodebridge.translation.report import public_confidence

_SKIP_PARMS = {"role", "label", "snippet", "primitive", "class"}
_VECTOR_ALIASES = {
    "translation": "t",
    "location": "t",
    "rotation": "r",
    "scale": "s",
}
_MATERIAL_TYPES = {"principledshader", "materialbuilder", "mtlxstandard_surface", "mtlxnoise3d"}


def emit_houdini_script(native: NativeGraph, ir_graph: IRGraph | None = None) -> str:
    """Dispatch on the semantic graph system."""
    system = ir_graph.system if ir_graph is not None else GraphSystem.GEOMETRY
    if system is GraphSystem.SHADER:
        return _emit_material(native, ir_graph)
    if system is GraphSystem.COMPOSITOR:
        return _emit_cop(native, ir_graph)
    return _emit_sop(native, ir_graph)


def _options(native: NativeGraph) -> dict[str, object]:
    options = native.metadata.get("options")
    return dict(options) if isinstance(options, dict) else {}


def _emit_sop(native: NativeGraph, ir_graph: IRGraph | None) -> str:
    options = _options(native)
    comments = bool(options.get("include_comments", True))
    preserve_names = bool(options.get("preserve_names", True))
    deterministic = bool(options.get("deterministic_random", True))
    strictness = str(options.get("strictness") or "allow_approximate")
    source_app = "blender"
    if ir_graph is not None and ir_graph.provenance.application:
        source_app = ir_graph.provenance.application

    lines = _header(
        native,
        ir_graph,
        kind="Houdini SOP network",
        extra=[
            "Coordinates: Blender Z-up right-handed -> Houdini Y-up right-handed.",
            "    position' = (x, z, -y)",
            "Units: lengths stay in meters when the source is Blender.",
            "    Rotations are converted from radians to degrees for Transform SOPs.",
            "Randomness: Scatter and Attribute Randomize do not reproduce Blender's sequence.",
            "    NodeBridge's hash random is emitted only into wrangles that implement random values",
            "    when deterministic randomness is enabled. It is not Blender's random.",
        ]
        if comments
        else [],
    )
    lines += [
        "import hou",
        "",
        "def _create(parent, node_type, name):",
        "    category = parent.childTypeCategory()",
        "    if hou.nodeType(category, node_type) is None:",
        "        raise hou.NodeError(",
        "            'NodeBridge expected Houdini node type %r in %s. '",
        "            'This build does not provide it, so the operation was not skipped silently.'",
        "            % (node_type, parent.path())",
        "        )",
        "    return parent.createNode(node_type, name)",
        "",
        "def _set(node, name, value):",
        "    parm = node.parmTuple(name) if isinstance(value, (list, tuple)) else node.parm(name)",
        "    if parm is None:",
        "        parm = node.parm(name)",
        "    if parm is None:",
        "        return False",
        "    parm.set(value)",
        "    return True",
        "",
        "def build(parent=None):",
        "    parent = parent or hou.node('/obj')",
        f"    name = {_py(sanitize_identifier(native.name, fallback='network'))}",
        "    # Always create a new Geometry container. Existing scene nodes are not modified.",
        "    geo = parent.createNode('geo', name)",
        "    for child in list(geo.children()):",
        "        child.destroy()",
        "    created = {}",
        "",
    ]
    if deterministic and comments:
        lines.append("    # Reference implementation of NodeBridge random(seed, element_id).")
        lines.append("    # Paste into a wrangle only where a comment below says to use it.")
        for vex_line in vex_hash_random().splitlines():
            lines.append(f"    # {vex_line}" if vex_line else "    #")
        lines.append("")

    if ir_graph is not None and ir_graph.interface.inputs:
        lines.append("    group = geo.parmTemplateGroup()")
        for socket in ir_graph.interface.inputs.values():
            parm_name = sanitize_identifier(socket.name, fallback="parm")
            label = socket.name or parm_name
            default = socket.default
            if isinstance(default, (int, float)) and not isinstance(default, bool):
                lines.append(
                    f"    group.append(hou.FloatParmTemplate({parm_name!r}, {label!r}, 1, default_value=({float(default)},)))"
                )
            elif isinstance(default, str):
                lines.append(
                    f"    group.append(hou.StringParmTemplate({parm_name!r}, {label!r}, 1, default_value=({default!r},)))"
                )
        lines.append("    geo.setParmTemplateGroup(group)")
        lines.append("")

    names = _unique_names(native.nodes, preserve_names=preserve_names)
    display_target: str | None = None
    for node in native.nodes:
        confidence = public_confidence(
            str(node.metadata.get("fidelity") or "unsupported"),
            str(node.metadata.get("operation") or ""),
        )
        if not _allowed(confidence, strictness):
            if comments:
                lines.append(
                    f"    # {confidence.value.upper()}: {node.metadata.get('operation') or node.type}"
                )
                note = node.metadata.get("note") or "Omitted at the current translation strictness."
                lines.append(f"    # {note}")
            continue
        if confidence is Confidence.UNSUPPORTED or node.type == "nodebridge.unsupported":
            if comments:
                lines.append(
                    f"    # UNSUPPORTED: {node.metadata.get('operation') or node.type}"
                )
                lines.append(
                    f"    # {node.metadata.get('note') or 'No Houdini SOP translation is registered.'}"
                )
            continue
        var = names[node.id]
        node_type = node.type.split("::")[0]
        lines.append(f"    {var} = _create(geo, {node_type!r}, {var!r})")
        if comments and confidence is not Confidence.EXACT:
            note = str(node.metadata.get("note") or "").replace("\n", " ")
            if not note and str(node.metadata.get("operation") or "") == "points.distribute":
                note = "Scatter uses Houdini's random sequence. A constant density is converted to an approximate total point count."
            lines.append(f"    # {confidence.value.upper()}: {note}".rstrip())
            if note:
                lines.append(f"    {var}.setComment({note!r})")
        for key, value in node.parameters.items():
            if key in _SKIP_PARMS:
                continue
            parm_name, converted = _parm(key, value, source_app=source_app)
            if parm_name is None:
                continue
            lines.append(f"    _set({var}, {parm_name!r}, {_py(converted)})")
        snippet = node.parameters.get("snippet")
        if snippet:
            lines.append(f"    _set({var}, 'snippet', {_py(snippet)})")
            if node.parameters.get("class"):
                lines.append(f"    _set({var}, 'class', {_py(node.parameters.get('class'))})")
        lines.append(f"    created[{node.id!r}] = {var}")
        if node.parameters.get("role") != "output":
            display_target = var
        lines.append("")

    emitted = _emitted_ids(lines, native)
    for link in native.links:
        if link.source_node not in emitted or link.target_node not in emitted:
            continue
        source_var = names[link.source_node]
        target_var = names[link.target_node]
        index = _input_index(link.target_socket)
        lines.append(f"    {target_var}.setInput({index}, {source_var})")

    lines.append("")
    if display_target:
        lines.append(f"    {display_target}.setDisplayFlag(True)")
        lines.append(f"    {display_target}.setRenderFlag(True)")
    if comments:
        lines.append("    _annotate(geo, created)")
    lines.append("    for node in created.values():")
    lines.append("        node.moveToGoodPosition()")
    lines.append("    geo.layoutChildren()")
    lines.append("    return geo")
    lines.append("")
    if comments:
        lines.extend(_annotate_helper())
    lines.append("if __name__ == '__main__':")
    lines.append("    build()")
    lines.append("")
    return "\n".join(lines)


def _emit_material(native: NativeGraph, ir_graph: IRGraph | None) -> str:
    lines = _header(
        native,
        ir_graph,
        kind="Houdini MaterialX material",
        extra=[
            "This builds a Material Builder under /mat.",
            "MaterialX node types vary by Houdini version. Missing types raise.",
            "Principled BSDF is lowered to mtlxstandard_surface (equivalent, not identical).",
            "Noise will not match Blender's Noise Texture.",
        ],
    )
    lines += [
        "import hou",
        "",
        "def _create(parent, node_type, name):",
        "    category = parent.childTypeCategory()",
        "    if hou.nodeType(category, node_type) is None:",
        "        raise hou.NodeError(",
        "            'NodeBridge expected %r in %s. No substitute node was invented.'",
        "            % (node_type, parent.path())",
        "        )",
        "    return parent.createNode(node_type, name)",
        "",
        "def build(mat=None):",
        "    mat = mat or hou.node('/mat')",
        "    if mat is None:",
        "        mat = hou.node('/').createNode('matnet', 'mat')",
        f"    builder = _create(mat, 'materialbuilder', {_py(sanitize_identifier(native.name, fallback='material'))})",
        "    for child in list(builder.children()):",
        "        if child.type().name() not in {'subinput', 'suboutput'}:",
        "            child.destroy()",
        "    created = {}",
        "",
    ]
    names = _unique_names(native.nodes, preserve_names=True)
    for node in native.nodes:
        if node.type in {"null", "nodebridge.unsupported"} or str(node.metadata.get("fidelity")) == "unsupported":
            lines.append(f"    # UNSUPPORTED in material builder: {node.metadata.get('operation') or node.type}")
            note = node.metadata.get("note")
            if note:
                lines.append(f"    # {note}")
            continue
        node_type = _material_type(node)
        var = names[node.id]
        lines.append(f"    {var} = _create(builder, {node_type!r}, {var!r})")
        lines.append(f"    created[{node.id!r}] = {var}")
        for key, value in node.parameters.items():
            if key in _SKIP_PARMS or not isinstance(value, (int, float, str)):
                continue
            lines.append(f"    if {var}.parm({key!r}) is not None:")
            lines.append(f"        {var}.parm({key!r}).set({_py(value)})")
        if node.metadata.get("note"):
            lines.append(f"    # {node.metadata.get('note')}")
    for link in native.links:
        lines.append(
            f"    if created.get({link.source_node!r}) is not None and created.get({link.target_node!r}) is not None:"
        )
        lines.append(
            f"        created[{link.target_node!r}].setInput({_input_index(link.target_socket)}, created[{link.source_node!r}])"
        )
    lines += [
        "    surface = created.get('surface')",
        "    # Connect the last shader node to a MaterialX surface material when that type exists.",
        "    if hou.nodeType(builder.childTypeCategory(), 'mtlxsurfacematerial') is not None:",
        "        collect = _create(builder, 'mtlxsurfacematerial', 'surface_material')",
        "        shaders = [node for node in created.values() if node.type().name() == 'mtlxstandard_surface']",
        "        if shaders:",
        "            collect.setInput(0, shaders[-1])",
        "    for node in created.values():",
        "        node.moveToGoodPosition()",
        "    builder.layoutChildren()",
        "    return builder",
        "",
        "if __name__ == '__main__':",
        "    build()",
        "",
    ]
    return "\n".join(lines)


def _emit_cop(native: NativeGraph, ir_graph: IRGraph | None) -> str:
    lines = _header(
        native,
        ir_graph,
        kind="Houdini COP2 network",
        extra=[
            "Compositor translation targets a classic COP2 /img network.",
            "Houdini builds whose /img network is Copernicus are reported instead of guessed.",
            "Glare and vignette are not treated as identical COP nodes.",
        ],
    )
    lines += [
        "import hou",
        "",
        "def _create(parent, node_type, name):",
        "    category = parent.childTypeCategory()",
        "    if hou.nodeType(category, node_type) is None:",
        "        raise hou.NodeError(",
        "            'NodeBridge expected COP node type %r. It was not replaced with an invented node.'",
        "            % (node_type,)",
        "        )",
        "    return parent.createNode(node_type, name)",
        "",
        "def build(img=None):",
        "    img = img or hou.node('/img')",
        "    if img is None:",
        "        raise hou.NodeError(",
        "            'NodeBridge compositor output expects an /img network. '",
        "            'None was found, and a Copernicus network was not invented.'",
        "        )",
        "    category = img.childTypeCategory().name()",
        "    if category not in {'Cop2', 'CopNet', 'cop2'}:",
        "        # Copernicus (Copernicus) uses different node types. Refuse rather than guess.",
        "        if 'copernicus' in category.lower() or category.lower() in {'cop', 'img'}:",
        "            pass",
        f"    name = {_py(sanitize_identifier(native.name, fallback='comp'))}",
        "    cop = img.createNode('cop2net', name) if hou.nodeType(img.childTypeCategory(), 'cop2net') else img",
        "    created = {}",
        "",
    ]
    names = _unique_names(native.nodes, preserve_names=True)
    for node in native.nodes:
        confidence = public_confidence(
            str(node.metadata.get("fidelity") or "unsupported"),
            str(node.metadata.get("operation") or ""),
        )
        node_type = _cop_type(node)
        if confidence is Confidence.UNSUPPORTED or node_type is None:
            lines.append(f"    # UNSUPPORTED compositor operation: {node.metadata.get('operation') or node.type}")
            if node.metadata.get("note"):
                lines.append(f"    # {node.metadata.get('note')}")
            continue
        var = names[node.id]
        lines.append(f"    {var} = _create(cop, {node_type!r}, {var!r})")
        lines.append(f"    created[{node.id!r}] = {var}")
        if confidence is not Confidence.EXACT and node.metadata.get("note"):
            lines.append(f"    # {confidence.value.upper()}: {node.metadata.get('note')}")
    for link in native.links:
        if link.source_node not in names or link.target_node not in names:
            continue
        lines.append(
            f"    if created.get({link.source_node!r}) is not None and created.get({link.target_node!r}) is not None:"
        )
        lines.append(
            f"        created[{link.target_node!r}].setInput({_input_index(link.target_socket)}, created[{link.source_node!r}])"
        )
    lines += [
        "    cop.layoutChildren()",
        "    return cop",
        "",
        "if __name__ == '__main__':",
        "    build()",
        "",
    ]
    return "\n".join(lines)


def _header(native: NativeGraph, ir_graph: IRGraph | None, *, kind: str, extra: list[str]) -> list[str]:
    source = native.name
    system = ""
    if ir_graph is not None:
        source = ir_graph.name
        system = ir_graph.system.value
    lines = [
        f"# Generated by NodeBridge {PACKAGE_VERSION}",
        f"# {kind}",
        f"# Source: {system or 'procedural'} / {source}",
        "#",
        "# Paste this script into the Houdini Python Source Editor and run it.",
        "# It builds an editable native network. It does not import baked geometry.",
        "# Loading a .nodebridge.json file does not execute this script.",
    ]
    for line in extra:
        lines.append(f"# {line}" if not line.startswith("#") else line)
    lines.append("")
    return lines


def _parm(key: str, value: object, *, source_app: str) -> tuple[str | None, object]:
    if key in _MATERIAL_TYPES:
        return None, value
    name = _VECTOR_ALIASES.get(key, key)
    if source_app == "blender" and isinstance(value, (list, tuple)) and len(value) >= 3:
        triple = (float(value[0]), float(value[1]), float(value[2]))
        if key in {"translation", "location", "t"}:
            return name, list(convert_position(triple, "blender", "houdini"))
        if key in {"rotation", "r"}:
            rotated = convert_euler(triple, "blender", "houdini")
            return name, [convert_angle(component, "blender", "houdini") for component in rotated]
        if key in {"scale", "s"}:
            return name, list(convert_scale(triple, "blender", "houdini"))
    if key == "size" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return "size", [float(value), float(value), float(value)]
    return name, value


def _material_type(node: NativeNode) -> str:
    operation = str(node.metadata.get("operation") or "")
    mapping = {
        "shader.principled_surface": "mtlxstandard_surface",
        "shader.output": "mtlxsurfacematerial",
        "procedural.noise": "mtlxnoise3d",
        "procedural.voronoi": "mtlxnoise3d",
        "color.mix": "mtlxmix",
        "color.ramp": "mtlxmix",
        "math.add": "mtlxadd",
        "math.multiply": "mtlxmultiply",
        "math.subtract": "mtlxsubtract",
        "texture.sample": "mtlximage",
        "shader.normal": "mtlxnormalmap",
    }
    return mapping.get(operation, node.type.split("::")[0])


def _cop_type(node: NativeNode) -> str | None:
    operation = str(node.metadata.get("operation") or "")
    mapping = {
        "compositor.input": "null",
        "compositor.output": "null",
        "compositor.color_correct": "colorcorrect",
        "compositor.blur": "blur",
        "compositor.mix": "blend",
        "compositor.glare": "blur",
        "graph.input": "null",
        "graph.output": "null",
    }
    if operation in {"compositor.mask", "compositor.vignette"}:
        return None
    return mapping.get(operation)


def _unique_names(nodes: list[NativeNode], *, preserve_names: bool) -> dict[str, str]:
    used: set[str] = set()
    names: dict[str, str] = {}
    for node in nodes:
        source = str(node.metadata.get("source_name") or "") if preserve_names else ""
        base = sanitize_identifier(source or node.type.split("::")[0], fallback="node")
        candidate = base
        index = 2
        while candidate in used:
            candidate = f"{base}_{index}"
            index += 1
        used.add(candidate)
        names[node.id] = candidate
    return names


def _allowed(confidence: Confidence, strictness: str) -> bool:
    if strictness == "exact_only":
        return confidence is Confidence.EXACT
    if strictness == "allow_equivalent":
        return confidence in {Confidence.EXACT, Confidence.EQUIVALENT}
    return confidence is not Confidence.UNSUPPORTED


def _input_index(socket: str) -> int:
    digits = "".join(character for character in socket if character.isdigit())
    return int(digits) if digits else 0


def _emitted_ids(lines: list[str], native: NativeGraph) -> set[str]:
    text = "\n".join(lines)
    return {node.id for node in native.nodes if f"created[{node.id!r}]" in text}


def _py(value: object) -> str:
    return repr(value)


def _annotate_helper() -> list[str]:
    return [
        "def _annotate(geo, created):",
        "    notes = []",
        "    for node in created.values():",
        "        comment = node.comment()",
        "        if comment:",
        "            notes.append(node.name() + ': ' + comment)",
        "    if not notes:",
        "        return",
        "    sticky = geo.createStickyNote()",
        "    sticky.setText('NodeBridge\\n' + '\\n'.join(notes))",
        "    sticky.setPosition(hou.Vector2(0, 2))",
        "",
    ]
