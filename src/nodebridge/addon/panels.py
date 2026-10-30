"""The NodeBridge N-panel, in the node editor and the 3D View.

Both spaces call the same draw functions and the same operators. Scene
settings are shared. Blender's ``layout.label`` does not wrap, so run
instructions are broken to the sidebar width.
"""

import bpy
from bpy.types import Panel

from ..frontend.blender.context import SourceNotFound, resolve_source

KIND_ICONS = {"GEOMETRY": "GEOMETRY_NODES", "SHADER": "MATERIAL", "COMPOSITOR": "NODE_COMPOSITING"}
PREVIEW_LINES = 14
MESH_NOTE = "PCG does not model meshes"


def draw_main(self, context):
    layout = self.layout
    settings = context.scene.nodebridge

    box = layout.box()
    box.label(text="Source", icon="NODETREE")
    box.prop(settings, "source_type", text="")
    try:
        selection = resolve_source(context, settings.source_type)
        box.label(text=selection.kind.label, icon=KIND_ICONS[selection.kind.name])
        box.label(text=selection.label, icon="NODE")
        if selection.owner:
            box.label(text=selection.owner, icon="OBJECT_DATA" if selection.kind.name == "GEOMETRY" else "BLANK1")
    except SourceNotFound as exc:
        box.label(text=str(exc).split(":")[0], icon="ERROR")

    box = layout.box()
    box.label(text="Target", icon="EXPORT")
    box.prop(settings, "target", text="")
    row = layout.row()
    row.scale_y = 1.5
    row.operator("nodebridge.analyze", icon="VIEWZOOM")


def poll_analysis(cls, context):
    return context.scene.nodebridge.analyzed


def draw_analysis(self, context):
    layout = self.layout
    s = context.scene.nodebridge
    col = layout.column(align=True)
    col.label(text=f"{s.analyzed_kind}: {s.analyzed_tree}")
    col.label(text=f"Target: {s.analyzed_target}")
    col.separator()
    col.label(text=f"Nodes analyzed: {s.node_count}")
    col.label(text=f"Operations detected: {s.operation_count}")
    col.separator()
    grid = layout.grid_flow(columns=2, even_columns=True, align=True)
    grid.label(text=f"Exact: {s.exact}", icon="CHECKMARK")
    grid.label(text=f"Equivalent: {s.equivalent}", icon="LINKED")
    grid.label(text=f"Approximate: {s.approximate}", icon="ERROR")
    grid.label(text=f"Unsupported: {s.unsupported}", icon="CANCEL")
    if s.blocked:
        layout.label(text=f"{s.blocked} blocked by strictness (placeholders)", icon="LOCKED")
    if s.analyzed_target.startswith("Unreal") and any(MESH_NOTE in message.text for message in s.messages):
        note = layout.column(align=True)
        for chunk in _wrap_to_region(
            "PCG does not model meshes. Extrude and curves stay unsupported; build that geometry in Houdini.",
            context,
        ):
            note.label(text=chunk)
    info = layout.column(align=True)
    info.label(text="Equivalent means same intent, not identical", icon="INFO")
    info.label(text="output: random samples and noise patterns differ.")
    row = layout.row(align=True)
    row.operator("nodebridge.open_text", text="Open Report", icon="TEXT").which = "REPORT"
    row.operator("nodebridge.copy_report", text="Copy Report", icon="COPYDOWN")


def poll_warnings(cls, context):
    settings = context.scene.nodebridge
    return settings.analyzed and len(settings.messages) > 0


def draw_warnings_header(self, context):
    self.layout.label(text=f"({len(context.scene.nodebridge.messages)})")


def draw_warnings(self, context):
    settings = context.scene.nodebridge
    col = self.layout.column(align=True)
    if settings.warning_total > len(settings.messages):
        col.label(text=f"Showing {len(settings.messages)} of {settings.warning_total}. Open the report for the rest.")
    for message in settings.messages:
        parts = [p.strip() for p in message.text.split("|")]
        icon = "CANCEL" if message.level == "ERROR" else "ERROR"
        col.label(text=parts[0], icon=icon)
        for part in parts[1:]:
            col.label(text=f"    {part}")
        col.separator(factor=0.5)


def draw_generate(self, context):
    layout = self.layout
    s = context.scene.nodebridge
    row = layout.row()
    row.scale_y = 1.5
    row.operator("nodebridge.generate", icon="SCRIPT")
    text = bpy.data.texts.get(s.code_text) if s.code_text else None
    if text is None:
        return
    layout.label(text=f"{s.code_language}: {s.code_lines} lines", icon="FILE_SCRIPT")
    preview = layout.box().column(align=True)
    preview.scale_y = 0.75
    for line in text.as_string().splitlines()[:PREVIEW_LINES]:
        preview.label(text=line.replace("\t", "    ") or " ")
    preview.label(text="...")
    row = layout.row(align=True)
    row.scale_y = 1.3
    row.operator("nodebridge.copy_code", icon="COPYDOWN")
    row.operator("nodebridge.save_script", text="Save .py", icon="FILE_TICK")
    row = layout.row(align=True)
    row.operator("nodebridge.generate", text="Regenerate", icon="FILE_REFRESH")
    row.operator("nodebridge.open_text", text="Open", icon="TEXT").which = "CODE"
    row.operator("nodebridge.clear", text="Clear", icon="X")
    if s.run_instructions:
        col = layout.column(align=True)
        for chunk in _wrap_to_region(s.run_instructions, context):
            col.label(text=chunk)


def _pxr_available() -> bool:
    from ..interchange.usd.availability import pxr_available

    return pxr_available()


def draw_openusd(self, context):
    layout = self.layout
    settings = context.scene.nodebridge
    layout.prop(settings, "usd_scope", text="Scope")
    layout.prop(settings, "usd_include_script", text="Include Native Target Script")
    layered = layout.row()
    layered.enabled = _pxr_available()
    layered.prop(settings, "usd_layered", text="Layered USD")
    if not _pxr_available():
        note = layout.column(align=True)
        for chunk in _wrap_to_region("Layered composition needs optional pxr. A basic bundle still uses Blender's USD exporter.", context):
            note.label(text=chunk)
    layout.prop(settings, "usd_replace", text="Replace Existing Bundle")
    layout.prop(settings, "usd_preview_surface", text="UsdPreviewSurface (limited)")
    row = layout.row()
    row.scale_y = 1.4
    row.operator("nodebridge.export_usd_bundle", icon="EXPORT")
    if settings.usd_last_summary:
        col = layout.column(align=True)
        for chunk in _wrap_to_region(settings.usd_last_summary, context):
            col.label(text=chunk)


def draw_advanced(self, context):
    layout = self.layout
    s = context.scene.nodebridge
    layout.prop(s, "strictness", text="Strictness")
    col = layout.column(align=True)
    for prop in ("include_comments", "preserve_names", "organize_graph", "embed_metadata", "deterministic_random", "include_materials", "debug_output"):
        col.prop(s, prop)


def _wrap(text: str, width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        if current and len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def _wrap_to_region(text: str, context) -> list[str]:
    """Fit instructions to the sidebar. ``layout.label`` does not wrap."""
    region = getattr(context, "region", None)
    width = getattr(region, "width", 0) or 320
    characters = max(28, int((width - 36) / 7))
    return _wrap(text, characters)


def _make_panel(idname, space, label, draw, parent=None, poll=None, options=None, header=None):
    namespace = {
        "bl_idname": idname,
        "bl_label": label,
        "bl_space_type": space,
        "bl_region_type": "UI",
        "bl_category": "NodeBridge",
        "draw": draw,
        "__module__": __name__,
    }
    if parent:
        namespace["bl_parent_id"] = parent
    if poll is not None:
        namespace["poll"] = classmethod(poll)
    if options:
        namespace["bl_options"] = options
    if header is not None:
        namespace["draw_header"] = header
    return type(idname, (Panel,), namespace)


_SPECS = (
    ("main", "NodeBridge", draw_main, None, None, None, None),
    ("analysis", "Analysis", draw_analysis, "main", poll_analysis, None, None),
    ("warnings", "Warnings", draw_warnings, "main", poll_warnings, None, draw_warnings_header),
    ("generate", "Generate", draw_generate, "main", None, None, None),
    ("openusd", "OpenUSD", draw_openusd, "main", None, None, None),
    ("advanced", "Advanced", draw_advanced, "main", None, {"DEFAULT_CLOSED"}, None),
)

CLASSES = []
for space, prefix in (("NODE_EDITOR", "NODEBRIDGE_PT"), ("VIEW_3D", "NODEBRIDGE_PT_VIEW3D")):
    ids = {}
    for key, label, draw, parent_key, poll, options, header in _SPECS:
        idname = f"{prefix}_{key}"
        parent = ids[parent_key] if parent_key else None
        cls = _make_panel(idname, space, label, draw, parent, poll, options, header)
        ids[key] = idname
        CLASSES.append(cls)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
