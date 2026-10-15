"""Blender N-panel, operators, and properties.

Classes are built when Blender calls ``register``. Importing this module
does not import ``bpy``.
"""

from __future__ import annotations

from nodebridge.addon.context import resolve_source
from nodebridge.addon.session import SESSION
from nodebridge.addon.settings import options_from_settings
from nodebridge.compiler.pipeline import compile_source


def build_classes(bpy):
    """Return classes in registration order."""

    class NodeBridgeSettings(bpy.types.PropertyGroup):
        target: bpy.props.EnumProperty(
            name="Target",
            items=[
                ("houdini", "Houdini", "Houdini Python that builds a native SOP, material, or COP network"),
                ("unreal", "Unreal Engine 5", "Unreal Editor Python for a PCG graph or material"),
            ],
            default="houdini",
        )
        source_mode: bpy.props.EnumProperty(
            name="Source",
            items=[
                ("auto", "Automatic", "Use the open editor, then the active modifier, material, or compositor"),
                ("geometry_nodes", "Geometry Nodes", "Use the Geometry Nodes editor or the active modifier"),
                ("shader", "Shader", "Use the Shader Editor or the active material"),
                ("compositor", "Compositor", "Use the Compositor"),
            ],
            default="auto",
        )
        strictness: bpy.props.EnumProperty(
            name="Translation Strictness",
            items=[
                ("exact_only", "Exact only", "Passthrough anything that is not exact"),
                ("allow_equivalent", "Allow equivalent", "Allow equivalent implementations"),
                ("allow_approximate", "Allow approximate", "Allow approximate implementations"),
            ],
            default="allow_approximate",
        )
        include_comments: bpy.props.BoolProperty(name="Include Comments", default=True)
        preserve_names: bpy.props.BoolProperty(name="Preserve Source Node Names", default=True)
        organized_layout: bpy.props.BoolProperty(name="Create Organized Target Graph", default=True)
        embed_metadata: bpy.props.BoolProperty(name="Embed NodeBridge Metadata", default=True)
        deterministic_random: bpy.props.BoolProperty(name="Deterministic Randomness", default=True)
        debug_output: bpy.props.BoolProperty(name="Debug Output", default=False)
        show_advanced: bpy.props.BoolProperty(name="Advanced", default=False)

    class NODEBRIDGE_OT_analyze(bpy.types.Operator):
        bl_idname = "nodebridge.analyze"
        bl_label = "Analyze Graph"
        bl_description = "Inspect the active node tree and classify every semantic operation"

        def execute(self, context):
            result = _compile(self, context)
            if result is None:
                return {"CANCELLED"}
            SESSION.store(result, generated=False)
            self.report({"INFO"}, SESSION.message)
            return {"FINISHED"}

    class NODEBRIDGE_OT_generate(bpy.types.Operator):
        bl_idname = "nodebridge.generate"
        bl_label = "Generate Code"
        bl_description = "Generate a script that builds a native graph in the target DCC"

        def execute(self, context):
            return _generate(self, context, bpy)

    class NODEBRIDGE_OT_regenerate(bpy.types.Operator):
        bl_idname = "nodebridge.regenerate"
        bl_label = "Regenerate"
        bl_description = "Compile the active tree again and replace the script"

        def execute(self, context):
            return _generate(self, context, bpy)

    class NODEBRIDGE_OT_copy(bpy.types.Operator):
        bl_idname = "nodebridge.copy_code"
        bl_label = "Copy Code"
        bl_description = "Copy the generated script to the clipboard"

        def execute(self, context):
            if not SESSION.code:
                self.report({"WARNING"}, "Generate code before copying.")
                return {"CANCELLED"}
            context.window_manager.clipboard = SESSION.code
            self.report({"INFO"}, "Copied the generated script.")
            return {"FINISHED"}

    class NODEBRIDGE_OT_copy_report(bpy.types.Operator):
        bl_idname = "nodebridge.copy_report"
        bl_label = "Copy Report"
        bl_description = "Copy the translation report to the clipboard"

        def execute(self, context):
            if not SESSION.report_text:
                self.report({"WARNING"}, "Analyze the graph before copying the report.")
                return {"CANCELLED"}
            context.window_manager.clipboard = SESSION.report_text
            self.report({"INFO"}, "Copied the translation report.")
            return {"FINISHED"}

    class NODEBRIDGE_OT_save(bpy.types.Operator, _export_helper()):
        bl_idname = "nodebridge.save_code"
        bl_label = "Save Script"
        bl_description = "Save the generated script as a Python file"
        filename_ext = ".py"
        filter_glob: bpy.props.StringProperty(default="*.py", options={"HIDDEN"})

        def execute(self, context):
            if not SESSION.code:
                self.report({"WARNING"}, "Generate code before saving.")
                return {"CANCELLED"}
            path = bpy.path.abspath(self.filepath)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(SESSION.code)
            self.report({"INFO"}, f"Saved {path}")
            return {"FINISHED"}

    class NODEBRIDGE_OT_clear(bpy.types.Operator):
        bl_idname = "nodebridge.clear"
        bl_label = "Clear"
        bl_description = "Clear the analysis and the generated script"

        def execute(self, context):
            SESSION.clear()
            return {"FINISHED"}

    def draw_nodebridge(layout, context):
        settings = context.scene.nodebridge
        selection = resolve_source(context, settings.source_mode)
        layout.label(text="Source")
        layout.prop(settings, "source_mode", text="")
        layout.label(text=selection.label)
        layout.label(text=selection.detail)
        layout.separator()
        layout.label(text="Target")
        layout.prop(settings, "target", text="")
        layout.separator()
        layout.operator("nodebridge.analyze", icon="VIEWZOOM")
        result = SESSION.result
        if result is not None:
            counts = result.report.counts
            column = layout.column(align=True)
            column.label(text=f"{result.report.node_count} Nodes")
            column.label(text=f"{result.report.operation_count} Operations")
            column.label(text=f"Exact: {counts.get('exact', 0)}")
            column.label(text=f"Equivalent: {counts.get('equivalent', 0)}")
            column.label(text=f"Approximate: {counts.get('approximate', 0)}")
            column.label(text=f"Unsupported: {counts.get('unsupported', 0)}")
            warnings = [item.message for item in result.diagnostics if item.severity in {"warning", "error"}][:6]
            for message in warnings:
                layout.label(text=message[:80])
            layout.operator("nodebridge.copy_report", icon="COPYDOWN")
        layout.separator()
        layout.operator("nodebridge.generate", icon="PLAY")
        if SESSION.generated and SESSION.code:
            box = layout.box()
            for line in SESSION.code.splitlines()[:14]:
                box.label(text=line[:88])
            layout.label(text="Full script: Text Editor / NodeBridge.py")
            row = layout.row(align=True)
            row.operator("nodebridge.copy_code", icon="COPYDOWN")
            row.operator("nodebridge.save_code", icon="FILE_TICK")
            row = layout.row(align=True)
            row.operator("nodebridge.regenerate", icon="FILE_REFRESH")
            row.operator("nodebridge.clear", icon="X")
        layout.separator()
        layout.prop(settings, "show_advanced", icon="TRIA_DOWN" if settings.show_advanced else "TRIA_RIGHT", emboss=False)
        if settings.show_advanced:
            advanced = layout.box()
            advanced.prop(settings, "strictness", text="")
            advanced.prop(settings, "include_comments")
            advanced.prop(settings, "preserve_names")
            advanced.prop(settings, "organized_layout")
            advanced.prop(settings, "embed_metadata")
            advanced.prop(settings, "deterministic_random")
            advanced.prop(settings, "debug_output")

    class NODEBRIDGE_PT_view3d(bpy.types.Panel):
        bl_idname = "NODEBRIDGE_PT_view3d"
        bl_label = "NodeBridge"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "NodeBridge"

        def draw(self, context):
            draw_nodebridge(self.layout, context)

    class NODEBRIDGE_PT_nodes(bpy.types.Panel):
        bl_idname = "NODEBRIDGE_PT_nodes"
        bl_label = "NodeBridge"
        bl_space_type = "NODE_EDITOR"
        bl_region_type = "UI"
        bl_category = "NodeBridge"

        def draw(self, context):
            draw_nodebridge(self.layout, context)

    return [
        NodeBridgeSettings,
        NODEBRIDGE_OT_analyze,
        NODEBRIDGE_OT_generate,
        NODEBRIDGE_OT_regenerate,
        NODEBRIDGE_OT_copy,
        NODEBRIDGE_OT_copy_report,
        NODEBRIDGE_OT_save,
        NODEBRIDGE_OT_clear,
        NODEBRIDGE_PT_view3d,
        NODEBRIDGE_PT_nodes,
    ]


def _export_helper():
    from bpy_extras.io_utils import ExportHelper

    return ExportHelper


def _generate(operator, context, bpy):
    result = _compile(operator, context)
    if result is None:
        return {"CANCELLED"}
    SESSION.store(result, generated=True)
    _write_text(bpy, "NodeBridge.py", result.code)
    _write_text(bpy, "NodeBridge Report.txt", result.report.text)
    operator.report({"INFO"}, "Generated script is in the Text Editor as NodeBridge.py")
    return {"FINISHED"}


def _compile(operator, context):
    settings = context.scene.nodebridge
    selection = resolve_source(context, settings.source_mode)
    if selection.source is None:
        operator.report({"WARNING"}, selection.detail)
        return None
    try:
        return compile_source(selection.source, settings.target, options_from_settings(settings))
    except Exception as exc:
        operator.report({"ERROR"}, str(exc))
        return None


def _write_text(bpy, name: str, content: str) -> None:
    block = bpy.data.texts.get(name)
    if block is None:
        block = bpy.data.texts.new(name)
    block.clear()
    block.write(content)
