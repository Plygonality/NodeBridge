"""NodeBridge N-panel."""

from __future__ import annotations

import bpy

from nodebridge.frontend.blender.context import infer_source


def _draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
    props = context.window_manager.nodebridge
    system, _tree, label = infer_source(context)
    source = layout.box()
    source.label(text="Source")
    source.label(text=_kind(system if label else props.source_kind or "—"))
    source.label(text=label or props.source_label or "No active tree")

    target = layout.box()
    target.label(text="Target")
    target.prop(props, "target", text="")

    layout.operator("nodebridge.analyze", icon="VIEWZOOM")

    if props.analyzed:
        stats = layout.box()
        stats.label(text="Analysis")
        stats.label(text=f"{props.node_count} Nodes")
        stats.label(text=f"{props.operation_count} Operations")
        stats.label(text=f"✓ {props.exact_count} Exact")
        stats.label(text=f"≈ {props.equivalent_count} Equivalent")
        stats.label(text=f"~ {props.approximate_count} Approximate")
        stats.label(text=f"✕ {props.unsupported_count} Unsupported")
        if props.warnings:
            warnings = stats.box()
            for line in props.warnings.splitlines()[:8]:
                warnings.label(text=line[:80])
        stats.operator("nodebridge.copy_report", icon="COPYDOWN")

    layout.operator("nodebridge.generate", icon="EXPORT")

    if props.code:
        output = layout.box()
        output.label(text="Output")
        preview = output.column(align=True)
        for line in props.code.splitlines()[:24]:
            preview.label(text=line[:96])
        if len(props.code.splitlines()) > 24:
            output.label(text="… full script is on the clipboard and in NodeBridge.py")
        row = output.row(align=True)
        row.operator("nodebridge.copy", icon="COPYDOWN")
        row.operator("nodebridge.save", icon="FILE_TICK")
        row = output.row(align=True)
        row.operator("nodebridge.generate", text="Regenerate", icon="FILE_REFRESH")
        row.operator("nodebridge.clear", icon="X")

    advanced = layout.box()
    advanced.prop(props, "show_advanced", icon="TRIA_DOWN" if props.show_advanced else "TRIA_RIGHT", emboss=False)
    if props.show_advanced:
        advanced.prop(props, "strictness")
        advanced.prop(props, "include_comments")
        advanced.prop(props, "preserve_names")
        advanced.prop(props, "organized_graph")
        advanced.prop(props, "embed_metadata")
        advanced.prop(props, "deterministic_random")
        advanced.prop(props, "debug_output")
        advanced.label(text="Equivalent means the intent is preserved.")
        advanced.label(text="Samples and pixels may still differ.")


def _kind(system: str) -> str:
    return {
        "geometry_nodes": "Geometry Nodes",
        "shader": "Shader",
        "compositor": "Compositor",
        "Geometry Nodes": "Geometry Nodes",
        "Shader": "Shader",
        "Compositor": "Compositor",
    }.get(system, system or "—")


class NODEBRIDGE_PT_node_editor(bpy.types.Panel):
    """Sidebar panel in the node editor."""

    bl_label = "NodeBridge"
    bl_idname = "NODEBRIDGE_PT_node_editor"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "NodeBridge"

    def draw(self, context: bpy.types.Context) -> None:
        _draw(self.layout, context)


class NODEBRIDGE_PT_view3d(bpy.types.Panel):
    """The same panel in the 3D viewport sidebar."""

    bl_label = "NodeBridge"
    bl_idname = "NODEBRIDGE_PT_view3d"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "NodeBridge"

    def draw(self, context: bpy.types.Context) -> None:
        _draw(self.layout, context)


CLASSES = (NODEBRIDGE_PT_node_editor, NODEBRIDGE_PT_view3d)
