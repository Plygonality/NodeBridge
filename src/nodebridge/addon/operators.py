"""Operators for the NodeBridge panel."""

from __future__ import annotations

import bpy

from nodebridge.addon.workflow import TranslateOptions, analyze_source, generate_from_document, generate_source
from nodebridge.frontend.blender.context import infer_source


def _options(props: bpy.types.PropertyGroup) -> TranslateOptions:
    return TranslateOptions(
        target=props.target,
        strictness=props.strictness,
        include_comments=props.include_comments,
        preserve_names=props.preserve_names,
        organized_graph=props.organized_graph,
        embed_metadata=props.embed_metadata,
        deterministic_random=props.deterministic_random,
        debug_output=props.debug_output,
    )


def _store(props: bpy.types.PropertyGroup, result: object, *, include_code: bool) -> None:
    props.source_kind = _kind_label(result.source_system)
    props.source_label = result.source_name
    props.node_count = result.node_count
    props.operation_count = result.operation_count
    props.exact_count = result.counts.get("exact", 0)
    props.equivalent_count = result.counts.get("equivalent", 0)
    props.approximate_count = result.counts.get("approximate", 0)
    props.unsupported_count = result.counts.get("unsupported", 0)
    props.warnings = "\n".join(result.warnings)
    props.report = result.report
    props.analyzed = True
    if include_code:
        props.code = result.code
        _text_block("NodeBridge.py", result.code)
    _text_block("NodeBridge Report.txt", result.report)
    window_manager = bpy.context.window_manager
    window_manager["nodebridge_document"] = None
    # The semantic document is kept on the window manager as a Python object.
    # Blender does not serialize it; Analyze again after reloading the file.
    setattr(window_manager, "_nodebridge_document", result.document)


def _text_block(name: str, text: str) -> None:
    block = bpy.data.texts.get(name)
    if block is None:
        block = bpy.data.texts.new(name)
    block.clear()
    block.write(text or "")


def _kind_label(system: str) -> str:
    return {
        "geometry_nodes": "Geometry Nodes",
        "shader": "Shader",
        "compositor": "Compositor",
    }.get(system, system)


class NODEBRIDGE_OT_analyze(bpy.types.Operator):
    """Inspect the active node tree and classify translation coverage."""

    bl_idname = "nodebridge.analyze"
    bl_label = "Analyze Graph"
    bl_options = {"REGISTER"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        system, tree, label = infer_source(context)
        props = context.window_manager.nodebridge
        if tree is None:
            self.report({"ERROR"}, "No Geometry Nodes, Shader, or Compositor tree is active")
            props.analyzed = False
            props.source_label = ""
            return {"CANCELLED"}
        try:
            result = analyze_source(tree, system=system, options=_options(props))
        except Exception as exc:  # noqa: BLE001 — surface parser failures in the UI
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if not result.source_name:
            result.source_name = label
        _store(props, result, include_code=False)
        self.report(
            {"INFO"},
            f"{result.node_count} nodes, {result.operation_count} operations",
        )
        return {"FINISHED"}


class NODEBRIDGE_OT_generate(bpy.types.Operator):
    """Generate target-DCC Python for the active node tree."""

    bl_idname = "nodebridge.generate"
    bl_label = "Generate Code"
    bl_options = {"REGISTER"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        props = context.window_manager.nodebridge
        options = _options(props)
        document = getattr(context.window_manager, "_nodebridge_document", None)
        try:
            if document is not None and props.analyzed:
                result = generate_from_document(document, options, node_count=props.node_count)
            else:
                system, tree, _label = infer_source(context)
                if tree is None:
                    self.report({"ERROR"}, "No node tree is active. Analyze a graph first")
                    return {"CANCELLED"}
                result = generate_source(tree, system=system, options=options)
        except Exception as exc:  # noqa: BLE001
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        _store(props, result, include_code=True)
        self.report({"INFO"}, "Generated code is ready to copy")
        return {"FINISHED"}


class NODEBRIDGE_OT_copy(bpy.types.Operator):
    """Copy the generated script to the Blender clipboard."""

    bl_idname = "nodebridge.copy"
    bl_label = "Copy Code"

    def execute(self, context: bpy.types.Context) -> set[str]:
        code = context.window_manager.nodebridge.code
        if not code:
            self.report({"WARNING"}, "Generate code before copying")
            return {"CANCELLED"}
        context.window_manager.clipboard = code
        self.report({"INFO"}, "Copied NodeBridge script")
        return {"FINISHED"}


class NODEBRIDGE_OT_copy_report(bpy.types.Operator):
    """Copy the translation report to the clipboard."""

    bl_idname = "nodebridge.copy_report"
    bl_label = "Copy Report"

    def execute(self, context: bpy.types.Context) -> set[str]:
        report = context.window_manager.nodebridge.report
        if not report:
            self.report({"WARNING"}, "Analyze a graph before copying the report")
            return {"CANCELLED"}
        context.window_manager.clipboard = report
        self.report({"INFO"}, "Copied translation report")
        return {"FINISHED"}


class NODEBRIDGE_OT_save(bpy.types.Operator):
    """Save the generated script to a Python file."""

    bl_idname = "nodebridge.save"
    bl_label = "Save Script"
    filepath: bpy.props.StringProperty(subtype="FILE_PATH", default="nodebridge_generated.py")
    filter_glob: bpy.props.StringProperty(default="*.py", options={"HIDDEN"})

    def execute(self, context: bpy.types.Context) -> set[str]:
        code = context.window_manager.nodebridge.code
        if not code:
            self.report({"WARNING"}, "Generate code before saving")
            return {"CANCELLED"}
        path = self.filepath
        if not path.lower().endswith(".py"):
            path += ".py"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(code)
        self.report({"INFO"}, f"Saved {path}")
        return {"FINISHED"}

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        del event
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class NODEBRIDGE_OT_clear(bpy.types.Operator):
    """Clear the analysis and generated script."""

    bl_idname = "nodebridge.clear"
    bl_label = "Clear"

    def execute(self, context: bpy.types.Context) -> set[str]:
        props = context.window_manager.nodebridge
        props.code = ""
        props.report = ""
        props.warnings = ""
        props.analyzed = False
        props.node_count = 0
        props.operation_count = 0
        props.exact_count = 0
        props.equivalent_count = 0
        props.approximate_count = 0
        props.unsupported_count = 0
        if hasattr(context.window_manager, "_nodebridge_document"):
            delattr(context.window_manager, "_nodebridge_document")
        return {"FINISHED"}


CLASSES = (
    NODEBRIDGE_OT_analyze,
    NODEBRIDGE_OT_generate,
    NODEBRIDGE_OT_copy,
    NODEBRIDGE_OT_copy_report,
    NODEBRIDGE_OT_save,
    NODEBRIDGE_OT_clear,
)
