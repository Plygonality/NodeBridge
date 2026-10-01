"""Helper functions embedded at the top of every generated Houdini script.

They only use documented ``hou`` APIs: ``Node.createNode``, ``Node.parm``,
``Node.parmTuple``, ``Parm.set``, ``Parm.setExpression``, ``Parm.menuItems``,
``ParmTemplate.dataType``, ``Node.parmTemplateGroup`` /
``setParmTemplateGroup``, ``Node.createStickyNote``, ``Node.setComment``,
``Node.setUserData``. A parameter that does not exist in the user's Houdini
version is reported in ``NB_WARNINGS`` instead of raising, because SOP
parameter names occasionally change between Houdini releases.
"""

HELPERS = '''
NB_WARNINGS = []
NB_NOTES = []


def nb_unique_name(parent, name):
    """Never overwrite existing nodes: append a number if the name is taken."""
    candidate, index = name, 1
    while parent.node(candidate) is not None:
        index += 1
        candidate = "%s%d" % (name, index)
    return candidate


def nb_create(parent, node_type, name, **kwargs):
    return parent.createNode(node_type, nb_unique_name(parent, name), **kwargs)


def nb_set(node, parm_name, value):
    """Set a parameter (or parameter tuple) if this Houdini version has it."""
    if isinstance(value, (tuple, list)):
        parm_tuple = node.parmTuple(parm_name)
        if parm_tuple is not None:
            parm_tuple.set(value)
            return True
    parm = node.parm(parm_name)
    if parm is not None:
        parm.set(value)
        return True
    NB_WARNINGS.append("%s: parameter '%s' not found" % (node.path(), parm_name))
    return False


def nb_set_menu(node, parm_name, token):
    """Set a menu parameter by token, whether the menu stores strings or indices."""
    parm = node.parm(parm_name)
    if parm is None:
        NB_WARNINGS.append("%s: parameter '%s' not found" % (node.path(), parm_name))
        return False
    tokens = parm.menuItems()
    if token not in tokens:
        NB_WARNINGS.append("%s: '%s' is not an option of '%s' (%s)" % (node.path(), token, parm_name, ", ".join(tokens)))
        return False
    if parm.parmTemplate().dataType() == hou.parmData.String:
        parm.set(token)
    else:
        parm.set(tokens.index(token))
    return True


def nb_expr(node, parm_name, expression, index=None):
    """Drive a parameter with an HScript expression (e.g. a channel reference)."""
    if index is None:
        parm = node.parm(parm_name)
    else:
        parm_tuple = node.parmTuple(parm_name)
        parm = parm_tuple[index] if parm_tuple is not None else None
    if parm is None:
        NB_WARNINGS.append("%s: parameter '%s' not found for expression" % (node.path(), parm_name))
        return False
    parm.setExpression(expression, hou.exprLanguage.Hscript)
    return True


def nb_add_parameters(node, folder_label, templates):
    """Expose controls as spare parameters on a container node."""
    if not templates:
        return
    group = node.parmTemplateGroup()
    folder = hou.FolderParmTemplate("nodebridge_controls", folder_label, folder_type=hou.folderType.Tabs)
    for template in templates:
        folder.addParmTemplate(template)
    group.append(folder)
    node.setParmTemplateGroup(group)


def nb_note(parent, text, near=None):
    note = parent.createStickyNote()
    note.setText(text)
    NB_NOTES.append((note, near))
    return note


def nb_place_notes():
    for note, near in NB_NOTES:
        if near is not None:
            note.setPosition(near.position() + hou.Vector2(2.0, -0.5))
        note.setSize(hou.Vector2(5.0, 1.6))


def nb_connect(node, input_name, source, output=0):
    """Connect by input name (VOP networks); report instead of failing."""
    try:
        node.setNamedInput(input_name, source, output)
        return True
    except hou.Error as exc:
        NB_WARNINGS.append("%s: could not connect '%s' (%s)" % (node.path(), input_name, exc))
        return False


def nb_meta(node, comment, data):
    node.setComment(comment)
    node.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    node.setUserData("nodebridge", data)
'''
