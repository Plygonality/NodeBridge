"""Namespaced custom data on a USD prim.

The key ``nodebridge`` is ordinary USD customData, not a custom schema plugin.
Large graphs stay in sidecar files. The publication hash is intentionally
absent: storing it inside an artifact would change the hash.
"""

from __future__ import annotations

from pathlib import Path

PROVENANCE_KEY = "nodebridge"


def provenance_data(*, generator_id: str, manifest_relative: str, generator_revision: str = "", mapping: str = "asset") -> dict:
    data = {
        "schema": "nodebridge.provenance",
        "schema_version": 1,
        "generator_id": generator_id,
        "manifest": manifest_relative,
        "mapping": mapping,
    }
    if generator_revision:
        data["generator_revision"] = generator_revision
    return data


def apply_provenance(prim, data: dict) -> None:
    prim.SetCustomDataByKey(PROVENANCE_KEY, data)


def read_provenance(prim) -> dict:
    data = prim.GetCustomDataByKey(PROVENANCE_KEY)
    if not data:
        return {}
    return dict(data)


def set_generator_revision(layer_path: Path, revision: str) -> None:
    """Write the Graph IR revision onto the root layer's default prim, if it has NodeBridge data."""
    from pxr import Usd

    stage = Usd.Stage.Open(str(layer_path))
    if not stage:
        return
    prim = stage.GetDefaultPrim()
    if not prim:
        return
    current = read_provenance(prim)
    if not current:
        return
    current["generator_revision"] = revision
    apply_provenance(prim, current)
    stage.GetRootLayer().Save()
