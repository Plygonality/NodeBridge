"""Export USD Bundle operator. USD is not a procedural compilation target."""

import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from ..frontend.blender.usd_export import UsdExportError, export_usd_bundle


class NODEBRIDGE_OT_export_usd_bundle(Operator):
    bl_idname = "nodebridge.export_usd_bundle"
    bl_label = "Export USD Bundle"
    bl_description = (
        "Export the evaluated Geometry Nodes object as a USD scene and store Graph IR, Semantic IR, "
        "the translation report, and an optional native script beside it. USD does not replace the Houdini or Unreal target."
    )
    filename_ext = ".nodebridge"
    filter_glob: StringProperty(default="*.nodebridge", options={"HIDDEN"})
    filepath: StringProperty(name="Bundle", subtype="FILE_PATH", default="nodebridge.nodebridge")

    def invoke(self, context, event):
        obj = context.active_object
        stem = obj.name if obj is not None else "nodebridge"
        self.filepath = bpy.path.abspath(f"//{stem}.nodebridge")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        settings = context.scene.nodebridge
        raw = bpy.path.abspath(self.filepath)
        output = _bundle_path(raw)
        try:
            summary = export_usd_bundle(context, settings, output)
        except UsdExportError as exc:
            self.report({"ERROR"}, str(exc))
            settings.usd_last_path = ""
            settings.usd_last_summary = str(exc)
            return {"CANCELLED"}
        settings.usd_last_path = summary.path
        warning_note = f" {len(summary.warnings)} warning(s)." if summary.warnings else ""
        settings.usd_last_summary = f"Wrote {summary.scene_file} and {len(summary.artifacts)} artifacts.{warning_note}"
        self.report({"INFO"}, settings.usd_last_summary)
        return {"FINISHED"}


def _bundle_path(raw: str):
    from pathlib import Path

    path = Path(raw)
    if path.suffix != ".nodebridge":
        path = path.with_suffix(".nodebridge") if path.suffix else path.parent / f"{path.name}.nodebridge"
    return path


CLASSES = (NODEBRIDGE_OT_export_usd_bundle,)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
