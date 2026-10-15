"""The NodeBridge N-panel (Node Editor > Sidebar > NodeBridge)."""

import bpy
from bpy.types import Panel

from ..frontend.blender.context import SourceNotFound, resolve_source

KIND_ICONS = {"GEOMETRY": "GEOMETRY_NODES", "SHADER": "MATERIAL", "COMPOSITOR": "NODE_COMPOSITING"}
PREVIEW_LINES = 14


class NodeBridgePanel:
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "NodeBridge"


class NODEBRIDGE_PT_main(NodeBridgePanel, Panel):
    bl_label = "NodeBridge"
    bl_idname = "NODEBRIDGE_PT_main"

    def draw(self, context):
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


class NODEBRIDGE_PT_analysis(NodeBridgePanel, Panel):
    bl_label = "Analysis"
    bl_parent_id = "NODEBRIDGE_PT_main"

    @classmethod
    def poll(cls, context):
        return context.scene.nodebridge.analyzed

    def draw(self, context):
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
        info = layout.column(align=True)
        info.label(text="Equivalent means same intent, not identical", icon="INFO")
        info.label(text="output: random samples and noise patterns differ.")
        row = layout.row(align=True)
        row.operator("nodebridge.open_text", text="Open Report", icon="TEXT").which = "REPORT"
        row.operator("nodebridge.copy_report", text="Copy Report", icon="COPYDOWN")


class NODEBRIDGE_PT_warnings(NodeBridgePanel, Panel):
    bl_label = "Warnings"
    bl_parent_id = "NODEBRIDGE_PT_main"

    @classmethod
    def poll(cls, context):
        settings = context.scene.nodebridge
        return settings.analyzed and len(settings.messages) > 0

    def draw_header(self, context):
        self.layout.label(text=f"({len(context.scene.nodebridge.messages)})")

    def draw(self, context):
        col = self.layout.column(align=True)
        for message in context.scene.nodebridge.messages:
            parts = [p.strip() for p in message.text.split("|")]
            icon = "CANCEL" if message.level == "ERROR" else "ERROR"
            col.label(text=parts[0], icon=icon)
            for part in parts[1:]:
                col.label(text=f"    {part}")
            col.separator(factor=0.5)


class NODEBRIDGE_PT_generate(NodeBridgePanel, Panel):
    bl_label = "Generate"
    bl_parent_id = "NODEBRIDGE_PT_main"

    def draw(self, context):
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
            for chunk in _wrap(s.run_instructions, 46):
                col.label(text=chunk)


class NODEBRIDGE_PT_advanced(NodeBridgePanel, Panel):
    bl_label = "Advanced"
    bl_parent_id = "NODEBRIDGE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        s = context.scene.nodebridge
        layout.prop(s, "strictness", text="Strictness")
        col = layout.column(align=True)
        for prop in ("include_comments", "preserve_names", "organize_graph", "embed_metadata", "deterministic_random", "include_materials", "debug_output"):
            col.prop(s, prop)


def _wrap(text: str, width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


CLASSES = (NODEBRIDGE_PT_main, NODEBRIDGE_PT_analysis, NODEBRIDGE_PT_warnings, NODEBRIDGE_PT_generate, NODEBRIDGE_PT_advanced)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
