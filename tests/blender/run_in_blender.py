"""Blender integration checks. Runs *inside* Blender:

    blender --background --factory-startup --python tests/blender/run_in_blender.py -- [--export-fixtures DIR]

* imports the installed NodeBridge extension (or ``src/`` as a fallback)
* builds the four example systems with real bpy calls
* drives the real operators: Analyze, Generate, Copy Code, Copy Report
* executes generated Houdini scripts against the recording fake ``hou``
* optionally exports Graph IR fixtures for the pure-Python test suite

Exits with status 1 on any failure.
"""

import importlib
import io
import json
import os
import sys
import contextlib
import traceback

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "examples", "blender"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

FAILURES = []


def check(condition, message):
    if not condition:
        FAILURES.append(message)
        print("FAIL:", message)


def load_nodebridge():
    for name in ("bl_ext.user_default.nodebridge", "nodebridge"):
        try:
            module = importlib.import_module(name)
            if hasattr(bpy.types.Scene, "nodebridge"):
                return module, name
        except ImportError:
            continue
    sys.path.insert(0, os.path.join(ROOT, "src"))
    module = importlib.import_module("nodebridge")
    module.register()
    return module, "nodebridge (src)"


def run_case(label, source_type, target, select=None, expect_kinds=()):
    scene = bpy.context.scene
    settings = scene.nodebridge
    if select is not None:
        bpy.context.view_layer.objects.active = select
    settings.source_type = source_type
    settings.target = target
    assert bpy.ops.nodebridge.analyze() == {"FINISHED"}, f"{label}: analyze failed"
    check(settings.analyzed, f"{label}: analysis stored")
    check(settings.operation_count > 0, f"{label}: operations detected")
    total = settings.exact + settings.equivalent + settings.approximate + settings.unsupported
    check(total == settings.operation_count, f"{label}: classification counts add up ({total} vs {settings.operation_count})")
    assert bpy.ops.nodebridge.generate() == {"FINISHED"}, f"{label}: generate failed"
    text = bpy.data.texts.get(settings.code_text)
    check(text is not None and len(text.as_string()) > 200, f"{label}: code text block exists")
    code = text.as_string() if text else ""
    check(("import hou" in code) if target == "houdini" else ("import unreal" in code), f"{label}: imports target API")
    check(bpy.ops.nodebridge.copy_code() == {"FINISHED"}, f"{label}: copy code")
    check(bpy.context.window_manager.clipboard == code or bpy.app.background, f"{label}: clipboard holds code")
    check(bpy.ops.nodebridge.copy_report() == {"FINISHED"}, f"{label}: copy report")
    for kind in expect_kinds:
        check(kind in bpy.data.texts[settings.report_text].as_string(), f"{label}: report mentions {kind}")
    result = {
        "case": label,
        "nodes": settings.node_count,
        "operations": settings.operation_count,
        "exact": settings.exact,
        "equivalent": settings.equivalent,
        "approximate": settings.approximate,
        "unsupported": settings.unsupported,
        "lines": settings.code_lines,
    }
    if target == "houdini":
        result["houdini_nodes"] = execute_with_fake("hou", code, label)
    else:
        result["unreal_calls"] = execute_with_fake("unreal", code, label)
    return result


def execute_with_fake(module_name, code, label):
    fake = importlib.import_module(f"fakes.fake_{module_name}")
    fake.reset()
    sys.modules[module_name] = fake
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            exec(compile(code, f"<{label}>", "exec"), {"__name__": "__main__"})
    except Exception:  # noqa: BLE001
        FAILURES.append(f"{label}: generated {module_name} script raised:\n{traceback.format_exc()}")
        return -1
    finally:
        sys.modules.pop(module_name, None)
    return fake.summary()


def export_fixtures(directory, built):
    from nodebridge.frontend.blender.context import add_referenced_materials
    from nodebridge.frontend.blender.parser import parse_document
    from nodebridge.ir.serialization import dumps_graph

    os.makedirs(directory, exist_ok=True)
    version = f"Blender {bpy.app.version_string}"
    ground, building_obj = built["ground"], built["building_object"]
    cases = {
        "scatter": (built["scatter"], built["scatter"].name, {"object": "Ground", "modifier": ground.modifiers[0].name, "object_dimensions": [round(v, 4) for v in ground.dimensions]}, ground.modifiers[0]),
        "building": (built["building"], built["building"].name, {"object": "Building", "modifier": building_obj.modifiers[0].name, "object_dimensions": [round(v, 4) for v in building_obj.dimensions]}, building_obj.modifiers[0]),
        "shader": (built["material"].node_tree, "ProceduralRock", {"material": "ProceduralRock"}, None),
        "compositor": (built["compositor"], "Scene Compositor", {"scene": bpy.context.scene.name}, None),
    }
    for key, (tree, root, extra, modifier) in cases.items():
        source = {"application": version, "display_name": root, "unit_scale": 1.0, "fps": 24.0, **extra}
        document = parse_document(tree, root_name=root, source=source, modifier=modifier)
        if key in ("scatter", "building"):
            add_referenced_materials(document, tree)
        path = os.path.join(directory, f"{key}.graph.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(dumps_graph(document))
        print("exported", path)


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    module, name = load_nodebridge()
    print("NodeBridge loaded from", name, "in Blender", bpy.app.version_string)
    import build_examples

    built = build_examples.build_all()
    if "--export-fixtures" in argv:
        export_fixtures(argv[argv.index("--export-fixtures") + 1], built)
    results = []
    for target in ("houdini", "unreal"):
        try:
            bpy.context.scene.nodebridge.target = target
        except TypeError:
            continue
        results.append(run_case(f"scatter/{target}", "GEOMETRY", target, built["ground"], ("SCATTER", "RANDOM_TRANSFORM")))
        results.append(run_case(f"building/{target}", "GEOMETRY", target, built["building_object"], ("EXTRUDE",)))
        results.append(run_case(f"shader/{target}", "SHADER", target, built["ground"], ("SHADER_BSDF",)))
        results.append(run_case(f"compositor/{target}", "COMPOSITOR", target, None, ("GLARE",)))
    print("NODEBRIDGE_RESULTS " + json.dumps(results))
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S)")
        sys.exit(1)
    print("ALL BLENDER CHECKS PASSED")


try:
    main()
except SystemExit:
    raise
except Exception:  # noqa: BLE001
    traceback.print_exc()
    sys.exit(1)
