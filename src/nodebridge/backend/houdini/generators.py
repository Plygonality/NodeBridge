"""Render a HoudiniBuild into pasteable ``hou`` Python."""

from __future__ import annotations

from nodebridge.backend.houdini.sop import HoudiniBuild, SopNode, SpareParm, SubnetNode
from nodebridge.translation.confidence import Confidence

def render_network(build: HoudiniBuild) -> str:
    """Render a top-level geometry container or a shader/COP script header plus nodes."""

    name = _container_name(build.graph.name)
    lines = [_header(build), "", "import hou", ""]
    lines.extend(
        [
            "def build(parent=None):",
            '    """Create a NodeBridge SOP network under parent. Existing nodes are left alone."""',
            "    parent = parent or hou.node('/obj')",
            "    if parent is None:",
            '        raise hou.Error("NodeBridge could not find /obj. Pass parent= to build().")',
            f"    name = {_unique_name_expr(name)}",
            "    container = parent.createNode('geo', name)",
            "    for child in list(container.children()):",
            "        child.destroy()",
        ]
    )
    if build.options.embed_metadata:
        lines.append(
            f"    container.setComment({_metadata_comment(build)!r})"
        )
        lines.append("    container.setGenericFlag(hou.nodeFlag.DisplayComment, True)")
    lines.extend(_spare_lines(build.spares, "container"))
    for line in build.prelude:
        lines.append(f"    {line}")
    for note in build.notes:
        for line in note.splitlines():
            lines.append(f"    {line}")
    lines.extend(render_nodes(build, "container", indent="    "))
    if build.options.organized_layout:
        lines.append("    container.layoutChildren()")
    lines.extend(_sticky(build))
    lines.extend(["    return container", "", "", "if __name__ == '__main__':", "    build()", ""])
    return "\n".join(lines)


def render_nodes(build: HoudiniBuild, parent: str, *, indent: str) -> list[str]:
    lines: list[str] = []
    for item in build.nodes:
        if isinstance(item, SubnetNode):
            lines.extend(_subnet(item, build, parent, indent))
            continue
        lines.extend(_sop(item, build, parent, indent))
    return lines


def _marker_lines(build: HoudiniBuild, operation, indent: str) -> list[str]:
    """Always emit the operation id. Extra explanation follows the comment option."""

    if operation is None:
        return []
    marker = build.marker(operation).splitlines()
    if build.options.include_comments:
        return [f"{indent}{line}" for line in marker]
    return [f"{indent}{marker[0]}"] if marker else []


def _sop(node: SopNode, build: HoudiniBuild, parent: str, indent: str) -> list[str]:
    operation = build.graph.try_get(node.op_id)
    lines = []
    lines.extend(_marker_lines(build, operation, indent))
    lines.append(f"{indent}{node.var} = {parent}.createNode({node.node_type!r}, {node.name!r})")
    for index, source in enumerate(node.inputs):
        if source:
            lines.append(f"{indent}{node.var}.setInput({index}, {source})")
    for parm, value in node.parms:
        lines.append(f"{indent}{node.var}.parm({parm!r}).set({value!r})")
    for parm, value in node.parm_tuples:
        lines.append(f"{indent}{node.var}.parmTuple({parm!r}).set({tuple(value)!r})")
    for parm, expression in node.expressions:
        lines.append(f"{indent}{node.var}.parm({parm!r}).setExpression({expression!r})")
    if node.snippet:
        lines.append(f"{indent}{node.var}.parm('class').set(2)")
        lines.append(f"{indent}{node.var}.parm('snippet').set(")
        lines.append(f'{indent}    """')
        for snippet_line in node.snippet.splitlines():
            lines.append(f"{indent}    {snippet_line}")
        lines.append(f'{indent}    """')
        lines.append(f"{indent})")
    if node.comment and build.options.include_comments:
        lines.append(f"{indent}{node.var}.setComment({node.comment!r})")
        lines.append(f"{indent}{node.var}.setGenericFlag(hou.nodeFlag.DisplayComment, True)")
    if node.display:
        lines.append(f"{indent}{node.var}.setDisplayFlag(True)")
    if node.render:
        lines.append(f"{indent}{node.var}.setRenderFlag(True)")
    if build.options.organized_layout:
        lines.append(f"{indent}{node.var}.moveToGoodPosition()")
    return lines


def _subnet(node: SubnetNode, build: HoudiniBuild, parent: str, indent: str) -> list[str]:
    operation = build.graph.try_get(node.op_id)
    lines = []
    lines.extend(_marker_lines(build, operation, indent))
    lines.append(f"{indent}{node.var} = {parent}.createNode('subnet', {node.name!r})")
    for index, source in enumerate(node.inputs):
        if source:
            lines.append(f"{indent}{node.var}.setInput({index}, {source})")
    lines.append(f"{indent}for _child in list({node.var}.children()):")
    lines.append(f"{indent}    _child.destroy()")
    inner = indent + "    "
    for line in node.inner_lines:
        lines.append(f"{inner}{line}" if line else "")
    if node.comment and build.options.include_comments:
        lines.append(f"{indent}{node.var}.setComment({node.comment!r})")
    if build.options.organized_layout:
        lines.append(f"{indent}{node.var}.layoutChildren()")
        lines.append(f"{indent}{node.var}.moveToGoodPosition()")
    return lines


def _spare_lines(spares: list[SpareParm], parent: str) -> list[str]:
    if not spares:
        return []
    lines = [f"    templates = {parent}.parmTemplateGroup()"]
    for spare in spares:
        if spare.kind == "int":
            template = f"hou.IntParmTemplate({spare.name!r}, {spare.label!r}, 1, default_value=({int(spare.default or 0)},))"
        elif spare.kind == "toggle":
            template = f"hou.ToggleParmTemplate({spare.name!r}, {spare.label!r}, default_value={bool(spare.default)!r})"
        elif spare.kind == "string":
            template = f"hou.StringParmTemplate({spare.name!r}, {spare.label!r}, 1, default_value=({str(spare.default or '')!r},))"
        elif spare.kind == "vector":
            values = tuple(spare.default) if isinstance(spare.default, (list, tuple)) else (0.0, 0.0, 0.0)
            template = f"hou.FloatParmTemplate({spare.name!r}, {spare.label!r}, 3, default_value={tuple(float(v) for v in values)!r})"
        else:
            template = f"hou.FloatParmTemplate({spare.name!r}, {spare.label!r}, 1, default_value=({float(spare.default or 0.0)!r},))"
        lines.append(f"    if templates.find({spare.name!r}) is None:")
        lines.append(f"        templates.append({template})")
    lines.append(f"    {parent}.setParmTemplateGroup(templates)")
    return lines


def _sticky(build: HoudiniBuild) -> list[str]:
    messages = []
    for classification in build.classifications.values():
        if classification.confidence in {Confidence.APPROXIMATE, Confidence.UNSUPPORTED}:
            messages.append(classification.explanation)
    if not messages or not build.options.include_comments:
        return []
    text = "NodeBridge\n" + "\n".join(messages[:8])
    return [
        "    if hasattr(container, 'createStickyNote'):",
        "        note = container.createStickyNote()",
        f"        note.setText({text!r})",
        "        note.setPosition(hou.Vector2(0, 4))",
    ]


def _header(build: HoudiniBuild) -> str:
    counts = {item: 0 for item in Confidence}
    for classification in build.classifications.values():
        counts[classification.confidence] += 1
    return "\n".join(
        [
            '"""NodeBridge Houdini SOP network.',
            "",
            f"Source: {build.graph.system.value} / {build.graph.name}",
            "Target: Houdini",
            (
                f"Confidence: {counts[Confidence.EXACT]} exact, "
                f"{counts[Confidence.EQUIVALENT]} equivalent, "
                f"{counts[Confidence.APPROXIMATE]} approximate, "
                f"{counts[Confidence.UNSUPPORTED]} unsupported."
            ),
            "",
            "Paste into the Houdini Python Source Editor and run.",
            "The script creates a new geometry container and does not modify other nodes.",
            "Equivalent and approximate operations are semantically related, not numerically identical.",
            '"""'
        ]
    )


def _metadata_comment(build: HoudiniBuild) -> str:
    from nodebridge import __version__

    return f"NodeBridge {__version__}\\nSource: {build.graph.name}"


def _container_name(name: str) -> str:
    from nodebridge.common.names import sanitize_identifier

    return "NB_" + sanitize_identifier(name or "graph")


def _unique_name_expr(name: str) -> str:
    return (
        f"'{name}' if parent.node('{name}') is None else "
        f"'{name}_' + str(sum(1 for item in parent.children() if item.name().startswith('{name}')) + 1)"
    )
