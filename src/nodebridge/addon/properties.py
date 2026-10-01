"""Window-manager properties for the NodeBridge panel."""

from __future__ import annotations

import bpy


class NodeBridgeProperties(bpy.types.PropertyGroup):
    """Session state for analyze / generate / copy."""

    target: bpy.props.EnumProperty(
        name="Target",
        items=(
            ("houdini", "Houdini", "Generate Houdini Python that builds a native network"),
            ("unreal", "Unreal Engine 5", "Generate Unreal Editor Python"),
        ),
        default="houdini",
    )
    strictness: bpy.props.EnumProperty(
        name="Translation Strictness",
        items=(
            ("exact_only", "Exact only", "Emit only operations classified exact"),
            ("allow_equivalent", "Allow equivalent", "Emit exact and equivalent operations"),
            ("allow_approximate", "Allow approximate", "Emit exact, equivalent, and approximate operations"),
        ),
        default="allow_approximate",
    )
    include_comments: bpy.props.BoolProperty(name="Include Comments", default=True)
    preserve_names: bpy.props.BoolProperty(name="Preserve Source Node Names", default=True)
    organized_graph: bpy.props.BoolProperty(name="Create Organized Target Graph", default=True)
    embed_metadata: bpy.props.BoolProperty(name="Embed NodeBridge Metadata", default=True)
    deterministic_random: bpy.props.BoolProperty(name="Deterministic Randomness", default=True)
    debug_output: bpy.props.BoolProperty(name="Debug Output", default=False)
    show_advanced: bpy.props.BoolProperty(name="Advanced", default=False)

    source_kind: bpy.props.StringProperty(name="Source Type", default="")
    source_label: bpy.props.StringProperty(name="Active Tree", default="")
    node_count: bpy.props.IntProperty(name="Nodes", default=0)
    operation_count: bpy.props.IntProperty(name="Operations", default=0)
    exact_count: bpy.props.IntProperty(default=0)
    equivalent_count: bpy.props.IntProperty(default=0)
    approximate_count: bpy.props.IntProperty(default=0)
    unsupported_count: bpy.props.IntProperty(default=0)
    analyzed: bpy.props.BoolProperty(default=False)
    code: bpy.props.StringProperty(name="Code", default="")
    report: bpy.props.StringProperty(name="Report", default="")
    warnings: bpy.props.StringProperty(name="Warnings", default="")
