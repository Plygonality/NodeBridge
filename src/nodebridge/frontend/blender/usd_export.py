"""Export an evaluated Blender object to a NodeBridge USD bundle.

This module is Blender-specific. It is not imported by the compiler.
``bpy`` is imported inside functions. The USD file comes from
``bpy.ops.wm.usd_export``; arguments are taken from that operator's RNA
for the running Blender version. pxr is never required to publish the
basic bundle. A headless call with only a Graph IR file cannot evaluate
Geometry Nodes, and this module does not pretend otherwise.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...compiler.pipeline import CompileOptions, analyze, generate
from ...interchange.bundle import PackageInputs, publish_package
from ...interchange.errors import BundleError
from ...ir.graph import TreeKind
from ...ir.serialization import dumps_graph, dumps_semantic
from ...translation.confidence import Strictness
from .context import SourceNotFound, build_document, resolve_source


class UsdExportError(Exception):
    """The Blender USD export could not run, or the source is not a geometry generator."""


@dataclass
class _Snapshot:
    mode: str
    active: str | None
    selected: set[str]
    hide_viewport: dict[str, bool]
    hide_get: dict[str, bool]


@dataclass
class ExportSummary:
    path: str
    artifacts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    scene_file: str = ""


_MODE_FOR_CONTEXT = {
    "OBJECT": "OBJECT",
    "EDIT_MESH": "EDIT",
    "EDIT_CURVE": "EDIT",
    "EDIT_SURFACE": "EDIT",
    "EDIT_TEXT": "EDIT",
    "EDIT_METABALL": "EDIT",
    "EDIT_LATTICE": "EDIT",
    "EDIT_ARMATURE": "EDIT",
    "POSE": "POSE",
    "SCULPT": "SCULPT",
    "PAINT_WEIGHT": "WEIGHT_PAINT",
    "PAINT_VERTEX": "VERTEX_PAINT",
    "PAINT_TEXTURE": "TEXTURE_PAINT",
}


def export_usd_bundle(context, settings, output: Path) -> ExportSummary:
    """Publish a bundle for the resolved Geometry Nodes object.

    Selection, the active object, mode, and viewport visibility are
    restored even when the export fails.
    """
    output = Path(output)
    snapshot = _capture(context)
    staging = tempfile.TemporaryDirectory(prefix="nodebridge-usd-")
    try:
        return _export(context, settings, output, Path(staging.name))
    finally:
        _restore(context, snapshot)
        staging.cleanup()


def _export(context, settings, output: Path, staging: Path) -> ExportSummary:
    try:
        selection = resolve_source(context, settings.source_type)
    except SourceNotFound as exc:
        raise UsdExportError(str(exc)) from exc
    if selection.kind != TreeKind.GEOMETRY:
        raise UsdExportError(
            "OpenUSD bundle export publishes evaluated scene geometry from a Geometry Nodes object. "
            f"The current source is {selection.kind.label}. Generate a native {settings.target} script for that tree instead. "
            "USD is not a procedural compilation target."
        )
    if selection.modifier is None:
        raise UsdExportError("Select an object with a Geometry Nodes modifier. NodeBridge exports that object's evaluated output, not the node tree alone.")
    obj = _object_for(context, selection)
    if obj is None:
        raise UsdExportError("The Geometry Nodes object is not in the active view layer, so its evaluated mesh cannot be exported.")

    available, reason = usd_exporter_available()
    if not available:
        raise UsdExportError(reason)

    document = build_document(selection, include_materials=settings.include_materials)
    result = analyze(document, settings.target, _compile_options(settings))
    script_path = None
    warnings: list[str] = []
    if settings.usd_include_script:
        generate(result)
        errors = list(result.diagnostics.errors)
        if errors:
            raise UsdExportError(errors[0].message)
        if result.code is None:
            raise UsdExportError(
                f"{result.report.target_label} did not generate a script for this tree. "
                "Turn off Include Native Target Script to publish the USD scene and IR sidecars without one."
            )
        script_path = staging / ("houdini.py" if result.target == "houdini" else f"{result.target}.py")
        script_path.write_text(result.code.code, encoding="utf-8")

    graph_file = staging / "source.graph.json"
    semantic_file = staging / "generator.semantic.json"
    report_file = staging / "report.json"
    report_text = staging / "report.txt"
    graph_file.write_text(dumps_graph(document), encoding="utf-8")
    semantic_file.write_text(dumps_semantic(result.semantic), encoding="utf-8")
    report_file.write_text(json.dumps(result.report.as_dict(), indent=2, default=str) + "\n", encoding="utf-8")
    report_text.write_text(result.report.to_text(), encoding="utf-8")

    scene_file = staging / "scene.usdc"
    kwargs, skipped = _export_scene(context, settings, obj, scene_file)
    if skipped:
        warnings.append("This Blender version has no USD export property for: " + ", ".join(skipped) + ".")
    warnings.append(
        "The USD file is Blender's evaluated export of the generator object. Instancing, shaders, custom attributes, and animation may be baked, partial, or omitted."
    )
    if settings.usd_scope == "SCENE":
        warnings.append("Visible scene scope can include objects that are not part of this generator.")
    elif settings.usd_scope == "OBJECT":
        warnings.append("Only the generator object was exported. Geometry that depends on other objects or collections may be missing.")

    layered = bool(settings.usd_layered)
    if layered:
        from ...interchange.usd.availability import pxr_available

        if not pxr_available():
            raise UsdExportError(
                "Layered USD was requested, but the optional pxr bindings are not available in this Python. "
                "Install nodebridge[usd] in Blender's Python, or turn off Layered USD. A basic bundle still uses Blender's exporter."
            )

    meters = float(context.scene.unit_settings.scale_length)
    scripts = {}
    if script_path is not None:
        scripts[result.target] = script_path
    try:
        manifest = publish_package(
            PackageInputs(
                scene=scene_file,
                graph=graph_file,
                semantic=semantic_file,
                output=output,
                report_json=report_file,
                report_text=report_text,
                scripts=scripts,
                layered=layered,
                replace=bool(settings.usd_replace),
                publisher="blender",
                annotate=True,
                procedural=False,
                up_axis="Z",
                meters_per_unit=meters,
                export_settings={
                    "tool": "bpy.ops.wm.usd_export",
                    "scope": settings.usd_scope,
                    "blender": _blender_version(),
                    "requested": {key: _jsonable(value) for key, value in kwargs.items() if key != "filepath"},
                    "preview_surface_requested": bool(settings.usd_preview_surface),
                },
                extra_warnings=warnings,
            )
        )
    except BundleError as exc:
        raise UsdExportError(str(exc)) from exc
    return ExportSummary(
        path=str(output),
        artifacts=sorted(artifact.path for artifact in manifest.artifacts),
        warnings=list(manifest.warnings),
        scene_file=str(manifest.scene.get("usd_path", "")),
    )


def usd_exporter_available() -> tuple[bool, str]:
    import bpy

    window_manager = getattr(bpy.ops, "wm", None)
    operator = getattr(window_manager, "usd_export", None)
    if operator is None:
        return False, "This Blender build has no wm.usd_export operator, so NodeBridge cannot write a USD scene."
    return True, ""


def exporter_property_names() -> set[str]:
    import bpy

    rna = bpy.ops.wm.usd_export.get_rna_type()
    return {prop.identifier for prop in rna.properties if prop.identifier not in {"rna_type"}}


def _export_scene(context, settings, obj, filepath: Path) -> tuple[dict[str, Any], list[str]]:
    names = _safe_property_names()
    _apply_scope(context, settings, obj)
    mode = "RENDER"
    modifier = getattr(obj, "modifiers", None)
    # Prefer the evaluation mode the modifier is enabled for.
    nodes = None
    if modifier is not None:
        active = getattr(modifier, "active", None)
        candidates = [item for item in modifier if getattr(item, "type", "") == "NODES" and getattr(item, "node_group", None) is not None]
        nodes = active if active in candidates else (candidates[0] if candidates else None)
    if nodes is not None and not getattr(nodes, "show_render", True) and getattr(nodes, "show_viewport", True):
        mode = "VIEWPORT"
    requested: dict[str, Any] = {
        "filepath": str(filepath),
        "selected_objects_only": settings.usd_scope != "SCENE",
        "visible_objects_only": settings.usd_scope == "SCENE",
        "export_animation": False,
        "export_hair": False,
        "export_uvmaps": True,
        "export_normals": True,
        "export_materials": True,
        "use_instancing": True,
        "evaluation_mode": mode,
        "generate_preview_surface": bool(settings.usd_preview_surface),
        "export_textures": False,
        "overwrite_textures": False,
        "relative_paths": True,
        "check_existing": False,
        "convert_orientation": False,
    }
    if names is None:
        kwargs = {"filepath": str(filepath)}
        skipped = sorted(key for key in requested if key != "filepath")
    else:
        kwargs = {}
        skipped = []
        for key, value in requested.items():
            if key not in names:
                if key != "filepath":
                    skipped.append(key)
                continue
            if not _enum_accepts(names, key, value):
                skipped.append(key)
                continue
            kwargs[key] = value
        kwargs["filepath"] = str(filepath)
    if not filepath.parent.exists():
        filepath.parent.mkdir(parents=True, exist_ok=True)
    result = _call_export(context, kwargs)
    if result != {"FINISHED"}:
        raise UsdExportError(
            "Blender's USD exporter did not finish. The bundle was not written. "
            "Check the system console for the exporter message. Selection and mode were restored."
        )
    if not filepath.is_file() or filepath.stat().st_size == 0:
        raise UsdExportError("Blender reported a finished USD export, but the file is missing or empty.")
    return kwargs, skipped


def _enum_accepts(names: set[str] | dict, key: str, value: Any) -> bool:
    if not isinstance(value, str):
        return True
    import bpy

    try:
        prop = bpy.ops.wm.usd_export.get_rna_type().properties[key]
    except Exception:
        return True
    enum_items = getattr(prop, "enum_items", None)
    if not enum_items:
        return True
    return value in {item.identifier for item in enum_items}


def _safe_property_names() -> set[str] | None:
    try:
        return exporter_property_names()
    except Exception:
        return None


def _call_export(context, kwargs: dict):
    import bpy

    found = _find_view3d(context)
    if found is None:
        return bpy.ops.wm.usd_export(**kwargs)
    window, area, region = found
    with context.temp_override(window=window, area=area, region=region):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        return bpy.ops.wm.usd_export(**kwargs)


def _find_view3d(context):
    manager = getattr(context, "window_manager", None)
    if manager is None:
        return None
    for window in manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                region = next((item for item in area.regions if item.type == "WINDOW"), None)
                if region is not None:
                    return window, area, region
    return None


def _apply_scope(context, settings, generator) -> None:
    """Select the objects the exporter should see. The caller restores selection afterwards."""
    view_layer = context.view_layer
    scope = settings.usd_scope
    if scope == "SCENE":
        return
    chosen = {generator}
    if scope == "SELECTED":
        chosen.update(obj for obj in view_layer.objects if obj.select_get())
        chosen.add(generator)
    for obj in view_layer.objects:
        obj.select_set(obj in chosen)
        if obj in chosen and (obj.hide_viewport or obj.hide_get()):
            obj.hide_viewport = False
            obj.hide_set(False)
    view_layer.objects.active = generator


def _object_for(context, selection):
    active = getattr(context, "active_object", None)
    if active is not None and selection.modifier is not None and selection.modifier in list(getattr(active, "modifiers", [])):
        return active
    name = selection.source.get("object")
    if not name:
        return active
    return context.view_layer.objects.get(name)


def _capture(context) -> _Snapshot:
    view_layer = context.view_layer
    active = view_layer.objects.active
    return _Snapshot(
        mode=str(getattr(context, "mode", "OBJECT")),
        active=active.name if active is not None else None,
        selected={obj.name for obj in view_layer.objects if obj.select_get()},
        hide_viewport={obj.name: bool(obj.hide_viewport) for obj in view_layer.objects},
        hide_get={obj.name: bool(obj.hide_get()) for obj in view_layer.objects},
    )


def _restore(context, snapshot: _Snapshot) -> None:
    import bpy

    try:
        view_layer = context.view_layer
        for obj in view_layer.objects:
            desired = obj.name in snapshot.selected
            if obj.select_get() != desired:
                obj.select_set(desired)
            if obj.name in snapshot.hide_viewport and obj.hide_viewport != snapshot.hide_viewport[obj.name]:
                obj.hide_viewport = snapshot.hide_viewport[obj.name]
            if obj.name in snapshot.hide_get and obj.hide_get() != snapshot.hide_get[obj.name]:
                obj.hide_set(snapshot.hide_get[obj.name])
        if snapshot.active:
            active = view_layer.objects.get(snapshot.active)
            if active is not None:
                view_layer.objects.active = active
        target = _MODE_FOR_CONTEXT.get(snapshot.mode)
        if target and getattr(context, "mode", "OBJECT") != snapshot.mode and context.active_object is not None:
            window = _find_view3d(context)
            if window is None:
                bpy.ops.object.mode_set(mode=target)
            else:
                win, area, region = window
                with context.temp_override(window=win, area=area, region=region):
                    bpy.ops.object.mode_set(mode=target)
    except Exception:
        # Restoration is best-effort only after the original error is already in flight.
        return


def _compile_options(settings) -> CompileOptions:
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


def _blender_version() -> str:
    import bpy

    return str(bpy.app.version_string)


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
