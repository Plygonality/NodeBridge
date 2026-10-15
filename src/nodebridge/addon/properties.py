"""Add-on settings and analysis results stored on the scene."""

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import PropertyGroup

from ..backend.registry import list_backends

SOURCE_TYPES = [
    ("AUTO", "Auto", "Use the tree shown in the current node editor"),
    ("GEOMETRY", "Geometry Nodes", "Active object's Geometry Nodes modifier"),
    ("SHADER", "Shader", "Active object's active material"),
    ("COMPOSITOR", "Compositor", "Scene compositor"),
]
STRICTNESS = [
    ("ALLOW_APPROXIMATE", "Allow approximate", "Generate everything NodeBridge can translate"),
    ("ALLOW_EQUIVALENT", "Allow equivalent", "Replace approximate operations with annotated placeholders"),
    ("EXACT_ONLY", "Exact only", "Replace anything that is not exact with annotated placeholders"),
]
TARGET_LABELS = {"houdini": "Houdini", "unreal": "Unreal Engine 5"}
_TARGET_ITEMS: list = []


def target_items(self, context):
    if not _TARGET_ITEMS:
        for backend in list_backends():
            _TARGET_ITEMS.append((backend.id, TARGET_LABELS.get(backend.id, backend.display_name), f"Generate {backend.language_label}"))
    return _TARGET_ITEMS


class NODEBRIDGE_PG_message(PropertyGroup):
    text: StringProperty()
    level: EnumProperty(items=[("INFO", "Info", ""), ("WARNING", "Warning", ""), ("ERROR", "Error", "")], default="INFO")


class NODEBRIDGE_PG_settings(PropertyGroup):
    source_type: EnumProperty(name="Source Type", items=SOURCE_TYPES, default="AUTO")
    target: EnumProperty(name="Target", items=target_items)
    strictness: EnumProperty(name="Translation Strictness", items=STRICTNESS, default="ALLOW_APPROXIMATE")
    include_comments: BoolProperty(name="Include Comments", default=True, description="Comments in the code and sticky notes / notes on approximations")
    preserve_names: BoolProperty(name="Preserve Source Node Names", default=True)
    organize_graph: BoolProperty(name="Create Organized Target Graph", default=True, description="Lay out the generated network")
    embed_metadata: BoolProperty(name="Embed NodeBridge Metadata", default=True, description="Store source node types and confidence on generated nodes")
    deterministic_random: BoolProperty(name="Deterministic Randomness", default=True, description="Use NodeBridge's reproducible random(seed, id) instead of the target's generator")
    include_materials: BoolProperty(name="Include Materials", default=True, description="Also translate node-based materials used by Set Material")
    debug_output: BoolProperty(name="Debug Output", default=False, description="Write Graph IR and Semantic IR JSON to text blocks")
    show_advanced: BoolProperty(default=False)
    show_warnings: BoolProperty(default=True)

    analyzed: BoolProperty(default=False)
    analyzed_tree: StringProperty()
    analyzed_kind: StringProperty()
    analyzed_target: StringProperty()
    node_count: IntProperty()
    operation_count: IntProperty()
    exact: IntProperty()
    equivalent: IntProperty()
    approximate: IntProperty()
    unsupported: IntProperty()
    blocked: IntProperty()
    messages: CollectionProperty(type=NODEBRIDGE_PG_message)
    report_text: StringProperty()
    code_text: StringProperty()
    code_language: StringProperty()
    code_lines: IntProperty()
    run_instructions: StringProperty()


CLASSES = (NODEBRIDGE_PG_message, NODEBRIDGE_PG_settings)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.nodebridge = PointerProperty(type=NODEBRIDGE_PG_settings)


def unregister() -> None:
    del bpy.types.Scene.nodebridge
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
