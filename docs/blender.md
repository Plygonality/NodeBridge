# Blender add-on

NodeBridge installs as a Blender add-on. The panel is **NodeBridge** in the node editor sidebar and the 3D viewport sidebar.

## Install

```bash
cd src && zip -r ../nodebridge.zip nodebridge
```

Preferences → Add-ons → Install → `nodebridge.zip` → enable NodeBridge.

Blender 4.2 or newer. The compiler itself is Python 3.11+ and does not need Blender to run tests.

## What the panel does

The add-on infers the active tree:

- Geometry Nodes editor, or the active object's Geometry Nodes modifier
- Shader editor material
- Compositor

**Analyze Graph** parses that tree, including nested groups, builds graph IR and semantic IR, and shows exact / equivalent / approximate / unsupported counts.

**Generate Code** writes the target script into the panel, the clipboard source, and a text block named `NodeBridge.py`.

**Copy Code** assigns `window_manager.clipboard`.

**Save Script** writes a `.py` file.

**Copy Report** copies the translation report on its own.

Advanced options: strictness, comments, source names, organized layout, metadata, deterministic randomness, debug output.

Strictness never hides an omitted operation. Exact-only mode leaves equivalent and approximate operations as comments and report entries.

## Parser

`nodebridge.frontend.blender.parser` reads nodes, sockets, links, interface sockets, object/material/collection references, and nested node groups. It accepts live `bpy` trees and test stand-ins. It does not import `bpy` at library import time.
