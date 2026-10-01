"""Operators: Analyze, Generate, Copy Code, Copy Report, Save Script, Clear, Open Text."""

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper

from ..compiler.pipeline import CompileOptions, analyze, generate
from ..frontend.blender.context import SourceNotFound, build_document, resolve_source
from ..ir.serialization import dumps_graph, dumps_semantic
from ..translation.confidence import Confidence, Strictness

REPORT_TEXT = "NodeBridge Report.txt"
MAX_MESSAGES = 40


def _options(settings) -> CompileOptions:
    return CompileOptions(
        strictness=Strictness(settings.strictness),
        include_comments=settings.include_comments,
        preserve_names=settings.preserve_names,
        organize_graph=settings.organize_graph,
        embed_metadata=settings.embed_metadata,
        deterministic_random=settings.deterministic_random,
        debug=settings.debug_output,
        include_materials=settings.include_materials,
    )


def _text(name: str, content: str):
    text = bpy.data.texts.get(name) or bpy.data.texts.new(name)
    text.clear()
    text.write(content)
    return text


def _compile(context, settings, *, with_code: bool):
    selection = resolve_source(context, settings.source_type)
    document = build_document(selection, include_materials=settings.include_materials)
    result = analyze(document, settings.target, _options(settings))
    if with_code:
        generate(result)
    _store(settings, selection, result)
    if settings.debug_output:
        _text(f"NodeBridge {selection.root_name} graph.json", dumps_graph(document))
        _text(f"NodeBridge {selection.root_name} semantic.json", dumps_semantic(result.semantic))
    return selection, result


def _store(settings, selection, result) -> None:
    report = result.report
    settings.analyzed = True
    settings.analyzed_tree = selection.label
    settings.analyzed_kind = report.source_kind
    settings.analyzed_target = report.target_label
    settings.node_count = report.node_count
    settings.operation_count = report.operation_count
    settings.exact = report.count(Confidence.EXACT)
    settings.equivalent = report.count(Confidence.EQUIVALENT)
    settings.approximate = report.count(Confidence.APPROXIMATE)
    settings.unsupported = report.count(Confidence.UNSUPPORTED)
    settings.blocked = len(report.blocked)
    settings.messages.clear()
    for line in report.warnings()[:MAX_MESSAGES]:
        item = settings.messages.add()
        item.text = line
        item.level = "ERROR" if " | Unsupported | " in line or line.startswith("Error") else "WARNING"
    settings.report_text = _text(REPORT_TEXT, report.to_text()).name


class NODEBRIDGE_OT_analyze(Operator):
    bl_idname = "nodebridge.analyze"
    bl_label = "Analyze Graph"
    bl_description = "Inspect the node tree and classify how each operation translates to the target"

    def execute(self, context):
        settings = context.scene.nodebridge
        try:
            selection, result = _compile(context, settings, with_code=False)
        except SourceNotFound as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        r = result.report
        self.report({"INFO"}, f"{r.node_count} nodes, {r.operation_count} operations: {settings.exact} exact, {settings.equivalent} equivalent, {settings.approximate} approximate, {settings.unsupported} unsupported")
        return {"FINISHED"}


class NODEBRIDGE_OT_generate(Operator):
    bl_idname = "nodebridge.generate"
    bl_label = "Generate Code"
    bl_description = "Generate target-DCC code that rebuilds this procedural system natively"

    def execute(self, context):
        settings = context.scene.nodebridge
        try:
            selection, result = _compile(context, settings, with_code=True)
        except SourceNotFound as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        if result.code is None:
            self.report({"WARNING"}, f"{result.report.target_label}: nothing to generate for this tree type")
            return {"CANCELLED"}
        name = f"{result.code.filename}"
        text = _text(name, result.code.code)
        settings.code_text = text.name
        settings.code_language = "Unreal Editor Python" if result.target == "unreal" else "Houdini Python"
        settings.code_lines = result.code.code.count("\n")
        settings.run_instructions = result.code.run_instructions
        errors = [d for d in result.diagnostics.errors if d.code.startswith("script.")]
        if errors:
            self.report({"ERROR"}, errors[0].message)
            return {"FINISHED"}
        self.report({"INFO"}, f"Generated {settings.code_lines} lines of {settings.code_language} ({text.name})")
        return {"FINISHED"}


class NODEBRIDGE_OT_copy_code(Operator):
    bl_idname = "nodebridge.copy_code"
    bl_label = "Copy Code"
    bl_description = "Copy the generated script to the clipboard"

    @classmethod
    def poll(cls, context):
        settings = context.scene.nodebridge
        return bool(settings.code_text) and settings.code_text in bpy.data.texts

    def execute(self, context):
        settings = context.scene.nodebridge
        context.window_manager.clipboard = bpy.data.texts[settings.code_text].as_string()
        self.report({"INFO"}, f"Copied {settings.code_lines} lines. {settings.run_instructions}")
        return {"FINISHED"}


class NODEBRIDGE_OT_copy_report(Operator):
    bl_idname = "nodebridge.copy_report"
    bl_label = "Copy Report"
    bl_description = "Copy the translation report to the clipboard"

    @classmethod
    def poll(cls, context):
        settings = context.scene.nodebridge
        return bool(settings.report_text) and settings.report_text in bpy.data.texts

    def execute(self, context):
        settings = context.scene.nodebridge
        context.window_manager.clipboard = bpy.data.texts[settings.report_text].as_string()
        self.report({"INFO"}, "Translation report copied")
        return {"FINISHED"}


class NODEBRIDGE_OT_save_script(Operator, ExportHelper):
    bl_idname = "nodebridge.save_script"
    bl_label = "Save Script"
    bl_description = "Save the generated script as a .py file"
    filename_ext = ".py"
    filter_glob: StringProperty(default="*.py", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        settings = context.scene.nodebridge
        return bool(settings.code_text) and settings.code_text in bpy.data.texts

    def invoke(self, context, event):
        self.filepath = context.scene.nodebridge.code_text
        return ExportHelper.invoke(self, context, event)

    def execute(self, context):
        code = bpy.data.texts[context.scene.nodebridge.code_text].as_string()
        with open(self.filepath, "w", encoding="utf-8") as handle:
            handle.write(code)
        self.report({"INFO"}, f"Saved {self.filepath}")
        return {"FINISHED"}


class NODEBRIDGE_OT_clear(Operator):
    bl_idname = "nodebridge.clear"
    bl_label = "Clear"
    bl_description = "Clear the analysis and generated code"

    def execute(self, context):
        settings = context.scene.nodebridge
        for name in (settings.code_text,):
            text = bpy.data.texts.get(name) if name else None
            if text is not None:
                bpy.data.texts.remove(text)
        settings.code_text = ""
        settings.code_lines = 0
        settings.analyzed = False
        settings.messages.clear()
        return {"FINISHED"}


class NODEBRIDGE_OT_open_text(Operator):
    bl_idname = "nodebridge.open_text"
    bl_label = "Open in Text Editor"
    bl_description = "Show the generated code or the report in a Text Editor"
    which: EnumProperty(items=[("CODE", "Code", ""), ("REPORT", "Report", "")], default="CODE")

    def execute(self, context):
        settings = context.scene.nodebridge
        name = settings.code_text if self.which == "CODE" else settings.report_text
        text = bpy.data.texts.get(name) if name else None
        if text is None:
            self.report({"WARNING"}, "Nothing to show yet")
            return {"CANCELLED"}
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "TEXT_EDITOR":
                    area.spaces.active.text = text
                    return {"FINISHED"}
        bpy.ops.wm.window_new()
        window = context.window_manager.windows[-1]
        area = max(window.screen.areas, key=lambda a: a.width * a.height)
        area.type = "TEXT_EDITOR"
        area.spaces.active.text = text
        return {"FINISHED"}


CLASSES = (
    NODEBRIDGE_OT_analyze,
    NODEBRIDGE_OT_generate,
    NODEBRIDGE_OT_copy_code,
    NODEBRIDGE_OT_copy_report,
    NODEBRIDGE_OT_save_script,
    NODEBRIDGE_OT_clear,
    NODEBRIDGE_OT_open_text,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
