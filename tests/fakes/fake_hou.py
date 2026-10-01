"""A recording stand-in for Houdini's ``hou`` module.

It implements only the API surface NodeBridge's generated scripts use,
with the same call signatures, and records the resulting network so tests
can assert on node types, parameters and wiring. It validates script
*structure*; it cannot validate Houdini's behaviour or parameter names.
"""

from __future__ import annotations

import types


class Error(Exception):
    pass


class OperationFailed(Error):
    pass


class Vector2(tuple):
    def __new__(cls, x=0.0, y=0.0):
        return super().__new__(cls, (float(x), float(y)))

    def __add__(self, other):
        return Vector2(self[0] + other[0], self[1] + other[1])


class _Enum:
    def __init__(self, *names):
        for name in names:
            setattr(self, name, f"{self.__class__.__name__}.{name}")


parmData = types.SimpleNamespace(Int="Int", Float="Float", String="String")
exprLanguage = types.SimpleNamespace(Hscript="Hscript", Python="Python")
folderType = types.SimpleNamespace(Tabs="Tabs", Simple="Simple")
parmLook = types.SimpleNamespace(ColorSquare="ColorSquare", Regular="Regular")
parmNamingScheme = types.SimpleNamespace(RGBA="RGBA", XYZW="XYZW")
nodeFlag = types.SimpleNamespace(DisplayComment="DisplayComment")


class ParmTemplate:
    def __init__(self, kind, name, label, *args, **kwargs):
        self.kind, self.name, self.label, self.args, self.kwargs = kind, name, label, args, kwargs
        self.children = []

    def addParmTemplate(self, template):
        self.children.append(template)

    def dataType(self):
        return parmData.String


def FloatParmTemplate(name, label, num_components, default_value=(), **kwargs):
    assert isinstance(default_value, tuple) and len(default_value) == num_components, (name, default_value)
    return ParmTemplate("float", name, label, num_components, default_value=default_value, **kwargs)


def IntParmTemplate(name, label, num_components, default_value=(), **kwargs):
    assert all(isinstance(v, int) for v in default_value), (name, default_value)
    return ParmTemplate("int", name, label, num_components, default_value=default_value, **kwargs)


def ToggleParmTemplate(name, label, default_value=False, **kwargs):
    return ParmTemplate("toggle", name, label, default_value=default_value, **kwargs)


def StringParmTemplate(name, label, num_components, default_value=(), **kwargs):
    return ParmTemplate("string", name, label, num_components, default_value=default_value, **kwargs)


def FolderParmTemplate(name, label, parm_templates=(), folder_type=None, **kwargs):
    folder = ParmTemplate("folder", name, label, folder_type=folder_type)
    folder.children.extend(parm_templates)
    return folder


class ParmTemplateGroup:
    def __init__(self):
        self.entries = []

    def append(self, template):
        self.entries.append(template)


class _Menu(list):
    """Accepts any token: the fake cannot know real menu contents."""

    def __contains__(self, item):
        return True

    def index(self, item, *args):
        return 0


class Parm:
    def __init__(self, node, name):
        self.node, self.name = node, name

    def set(self, value):
        self.node.parm_values[self.name] = value

    def eval(self):
        return self.node.parm_values.get(self.name)

    def setExpression(self, expression, language=None, replace_expression=True):
        assert isinstance(expression, str) and expression.strip(), (self.name, expression)
        self.node.expressions[self.name] = expression

    def menuItems(self):
        return _Menu()

    def parmTemplate(self):
        return ParmTemplate("menu", self.name, self.name)


class ParmTuple(list):
    def __init__(self, node, name):
        super().__init__(Parm(node, f"{name}[{i}]") for i in range(4))
        self.node, self.name = node, name

    def set(self, values):
        self.node.parm_values[self.name] = tuple(values)


class NetworkItem:
    def __init__(self):
        self._position = Vector2()

    def position(self):
        return self._position

    def setPosition(self, position):
        self._position = Vector2(*position)


class StickyNote(NetworkItem):
    def __init__(self, parent):
        super().__init__()
        self.parent, self.text, self.size = parent, "", None

    def setText(self, text):
        self.text = text

    def setSize(self, size):
        self.size = size


class NetworkBox(NetworkItem):
    def __init__(self, parent):
        super().__init__()
        self.parent, self.items, self.comment = parent, [], ""

    def addItem(self, item):
        self.items.append(item)

    def setComment(self, text):
        self.comment = text

    def fitAroundContents(self):
        pass


class IndirectInput(NetworkItem):
    def __init__(self, subnet, index):
        super().__init__()
        self.subnet, self.index = subnet, index


class Node(NetworkItem):
    def __init__(self, parent, node_type, name):
        super().__init__()
        self.parent = parent
        self.type_name = node_type
        self.name_ = name
        self._children: dict[str, Node] = {}
        self.inputs: dict = {}
        self.named_inputs: dict = {}
        self.parm_values: dict = {}
        self.expressions: dict = {}
        self.flags: dict = {}
        self.comment = ""
        self.user_data: dict = {}
        self.notes: list[StickyNote] = []
        self.boxes: list[NetworkBox] = []
        self.ptg = ParmTemplateGroup()
        self.laid_out = False

    def name(self):
        return self.name_

    def path(self):
        if self.parent is None:
            return self.name_ or "/"
        base = self.parent.path().rstrip("/")
        return f"{base}/{self.name_}"

    def node(self, path):
        if path.startswith("/"):
            return ROOT.node(path[1:]) if self is not ROOT else self._resolve(path.strip("/").split("/"))
        return self._resolve(path.split("/"))

    def _resolve(self, parts):
        current = self
        for part in parts:
            if not part:
                continue
            current = current._children.get(part)
            if current is None:
                return None
        return current

    def createNode(self, node_type, node_name=None, run_init_scripts=True, load_contents=True, exact_type_name=False):
        name = node_name or f"{node_type}1"
        if name in self._children:
            raise OperationFailed(f"name {name!r} already used")
        child = Node(self, node_type, name)
        self._children[name] = child
        return child

    def children(self):
        return tuple(self._children.values())

    def parm(self, name):
        return Parm(self, name)

    def parmTuple(self, name):
        return ParmTuple(self, name)

    def setInput(self, input_index, item_to_become_input, output_index=0):
        assert isinstance(input_index, int) and input_index >= 0
        assert item_to_become_input is None or isinstance(item_to_become_input, (Node, IndirectInput)), item_to_become_input
        assert input_index not in self.inputs, f"{self.path()} input {input_index} connected twice"
        self.inputs[input_index] = (item_to_become_input, output_index)

    def setNamedInput(self, input_name, item_to_become_input, output_name_or_index):
        assert isinstance(item_to_become_input, Node)
        self.named_inputs[input_name] = (item_to_become_input, output_name_or_index)

    def indirectInputs(self):
        return tuple(IndirectInput(self, i) for i in range(4))

    def setDisplayFlag(self, on):
        self.flags["display"] = on

    def setRenderFlag(self, on):
        self.flags["render"] = on

    def layoutChildren(self, items=(), horizontal_spacing=-1.0, vertical_spacing=-1.0):
        self.laid_out = True

    def moveToGoodPosition(self):
        pass

    def createStickyNote(self, name=None):
        note = StickyNote(self)
        self.notes.append(note)
        return note

    def createNetworkBox(self, name=None):
        box = NetworkBox(self)
        self.boxes.append(box)
        return box

    def setComment(self, comment):
        self.comment = comment

    def setGenericFlag(self, flag, value):
        self.flags[flag] = value

    def setUserData(self, name, value):
        assert isinstance(value, str)
        self.user_data[name] = value

    def parmTemplateGroup(self):
        return self.ptg

    def setParmTemplateGroup(self, group):
        self.ptg = group

    def spare_parm_names(self):
        names = []
        for entry in self.ptg.entries:
            names.extend(child.name for child in entry.children)
        return names


def _build_root():
    root = Node(None, "root", "")
    for context, kind in (("obj", "objnet"), ("mat", "matnet"), ("img", "imgnet"), ("out", "ropnet")):
        root._children[context] = Node(root, kind, context)
    return root


ROOT = _build_root()


def node(path):
    return ROOT._resolve(path.strip("/").split("/"))


def reset():
    global ROOT
    ROOT = _build_root()
    return ROOT


def summary() -> int:
    """Number of nodes the script created (excluding the root contexts)."""
    return sum(1 for _ in all_nodes()) - 4


def all_nodes(parent=None):
    parent = parent or ROOT
    for child in parent.children():
        yield child
        yield from all_nodes(child)
