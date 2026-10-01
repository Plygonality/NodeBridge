"""A recording stand-in for Unreal's ``unreal`` Python module.

Implements the API surface NodeBridge's generated scripts use, with the
same call shapes, and records assets, PCG nodes/edges, material
expressions and post-process settings. PCG ``add_edge`` returns ``None``
for unknown pin labels (as the real API does), so pin fallbacks are
exercised. It validates script structure, not Unreal behaviour.
"""

from __future__ import annotations

import types

STATE: dict = {}

PCG_PINS = {
    "PCGSurfaceSamplerSettings": (["Surface", "Bounding Shape"], ["Out"]),
    "PCGTransformPointsSettings": (["In"], ["Out"]),
    "PCGStaticMeshSpawnerSettings": (["In"], ["Out"]),
    "PCGMergeSettings": (["In"], ["Out"]),
    "PCGSpatialNoiseSettings": (["In"], ["Out"]),
    "PCGDensityFilterSettings": (["In"], ["Out"]),
    "_input": ([], ["Input", "Landscape", "Landscape Height", "Actor", "Original Actor"]),
    "_output": (["Out"], []),
}


def reset():
    STATE.clear()
    STATE.update(assets={}, edges=[], nodes=[], expressions=[], links=[], outputs=[], warnings=[], actors=[], recompiled=[], saved=[])


reset()


def summary() -> dict:
    return {
        "assets": sorted(STATE["assets"]),
        "pcg_nodes": len(STATE["nodes"]),
        "pcg_edges": len(STATE["edges"]),
        "expressions": len(STATE["expressions"]),
        "actors": len(STATE["actors"]),
    }


class _Object:
    def __init__(self, **props):
        self._props = dict(props)

    def set_editor_property(self, name, value):
        self._props[name] = value

    def get_editor_property(self, name):
        if name not in self._props:
            self._props[name] = _Object()
        return self._props[name]

    def get_path_name(self):
        return self._props.get("path", "/Game/fake")


def _struct(name):
    return type(name, (_Object,), {"__init__": lambda self, *args, **kwargs: _Object.__init__(self, args=args, **kwargs)})


Vector = _struct("Vector")
Vector4 = _struct("Vector4")
Rotator = _struct("Rotator")
LinearColor = _struct("LinearColor")
PCGMeshSelectorWeightedEntry = _struct("PCGMeshSelectorWeightedEntry")


class _Class(type):
    pass


def _uclass(name):
    return _Class(name, (_Object,), {})


class PCGNode(_Object):
    def __init__(self, kind):
        super().__init__()
        self.kind = kind

    def set_node_position(self, x, y):
        self._props["position"] = (x, y)


class PCGSettings(_Object):
    def set_mesh_selector_type(self, selector):
        self._props["mesh_selector_type"] = selector


class PCGGraph(_Object):
    def __init__(self, path=""):
        super().__init__(path=path)
        self.input = PCGNode("_input")
        self.output = PCGNode("_output")

    def get_input_node(self):
        return self.input

    def get_output_node(self):
        return self.output

    def add_node_of_type(self, settings_class):
        assert isinstance(settings_class, type), settings_class
        node = PCGNode(settings_class.__name__)
        settings = PCGSettings()
        STATE["nodes"].append((node, settings))
        return node, settings

    def add_edge(self, source, source_pin, target, target_pin):
        assert isinstance(source, PCGNode) and isinstance(target, PCGNode)
        outputs = PCG_PINS.get(source.kind, ([], ["Out"]))[1]
        inputs = PCG_PINS.get(target.kind, (["In"], []))[0]
        if source_pin not in outputs or target_pin not in inputs:
            return None
        STATE["edges"].append((source.kind, source_pin, target.kind, target_pin))
        return target


class Material(_Object):
    pass


class PostProcessVolume(_Object):
    def set_actor_label(self, label):
        self._props["label"] = label

    def get_actor_label(self):
        return self._props.get("label", "")


class PCGVolume(_Object):
    def get_component_by_class(self, cls):
        component = _Object()
        component.set_graph = lambda graph: component.set_editor_property("graph", graph)
        return component


PCGComponent = _uclass("PCGComponent")
PCGGraphFactory = _uclass("PCGGraphFactory")
MaterialFactoryNew = _uclass("MaterialFactoryNew")
PCGMeshSelectorWeighted = _uclass("PCGMeshSelectorWeighted")


class _AssetTools:
    def create_asset(self, name, path, asset_class, factory):
        full = f"{path}/{name}"
        assert full not in STATE["assets"], f"asset {full} overwritten"
        asset = asset_class(path=full) if asset_class is PCGGraph else asset_class()
        asset.set_editor_property("path", full)
        STATE["assets"][full] = asset
        return asset


class AssetToolsHelpers:
    @staticmethod
    def get_asset_tools():
        return _AssetTools()


class EditorAssetLibrary:
    @staticmethod
    def does_asset_exist(path):
        return path in STATE["assets"]

    @staticmethod
    def make_directory(path):
        return True

    @staticmethod
    def load_asset(path):
        return _Object(path=path) if path.startswith("/Engine/") else None

    @staticmethod
    def save_loaded_asset(asset):
        STATE["saved"].append(asset)
        return True


class MaterialEditingLibrary:
    @staticmethod
    def create_material_expression(material, expression_class, x=0, y=0):
        assert isinstance(material, Material)
        expression = expression_class()
        STATE["expressions"].append(expression_class.__name__)
        return expression

    @staticmethod
    def connect_material_expressions(source, source_output, target, target_input):
        assert isinstance(source_output, str) and isinstance(target_input, str)
        STATE["links"].append((type(source).__name__, source_output, type(target).__name__, target_input))
        return True

    @staticmethod
    def connect_material_property(source, source_output, material_property):
        STATE["outputs"].append((type(source).__name__, material_property))
        return True

    @staticmethod
    def recompile_material(material):
        STATE["recompiled"].append(material)


MaterialProperty = types.SimpleNamespace(**{name: name for name in ("MP_BASE_COLOR", "MP_METALLIC", "MP_ROUGHNESS", "MP_SPECULAR", "MP_NORMAL", "MP_EMISSIVE_COLOR", "MP_OPACITY")})
NoiseFunction = types.SimpleNamespace(NOISEFUNCTION_GRADIENT_ALU="gradient", NOISEFUNCTION_VORONOI_ALU="voronoi")
PCGSpatialNoiseMode = types.SimpleNamespace(FRACTIONAL_BROWNIAN2D="fbm")


class EditorActorSubsystem:
    def spawn_actor_from_class(self, actor_class, location):
        actor = actor_class()
        STATE["actors"].append(actor)
        return actor


def get_editor_subsystem(cls):
    return cls()


def log_warning(message):
    STATE["warnings"].append(message)


def __getattr__(name):
    if name.startswith("PCG") and name.endswith("Settings"):
        cls = _uclass(name)
        globals()[name] = cls
        return cls
    if name.startswith("MaterialExpression"):
        cls = _uclass(name)
        globals()[name] = cls
        return cls
    raise AttributeError(name)
