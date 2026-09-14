"""The only translation between pysepal types and domain types.

``sdg1531`` imports no pysepal: ``InfoFetcher`` is a Protocol declared in
``sdg1531.ports`` over nothing but ``typing``. This module is where the real
``GEEInterface`` is made to satisfy it, and where pysepal's AOI selection
becomes the domain's ``AoiSpec`` union.

Keeping both in one file is deliberate. If a pysepal signature changes, one
file fails and the domain never notices.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from sdg1531.spec import AoiSpec, AssetAoi, GeoJsonAoi

__all__ = ("GeeInfoFetcher", "to_domain_aoi")


class GeeInfoFetcher:
    """Adapts pysepal's ``GEEInterface`` to :class:`sdg1531.ports.InfoFetcher`.

    The parameter names are copied from the Protocol deliberately: a Protocol
    matches positional-or-keyword parameters by NAME, so renaming ``ee_object``
    here would silently stop satisfying it.
    """

    def __init__(self, gee_interface: Any) -> None:
        self._interface = gee_interface

    async def get_info_async(self, ee_object: Any = None, tag: Any = None) -> Any:
        return await self._interface.get_info_async(ee_object, tag)

    async def get_info_batch_async(self, ee_objects: list[Any]) -> list[Any]:
        return cast("list[Any]", await self._interface.get_info_batch_async(ee_objects))


def to_domain_aoi(selection: Mapping[str, Any] | None) -> AoiSpec | None:
    """pysepal's AOI selection -> the domain's ``AoiSpec`` union.

    The two libraries both define a type called ``AoiSpec`` and they are NOT the
    same: pysepal's is a serializable descriptor of how the user picked, and the
    domain's is a union of what was picked (``AssetAoi | GeoJsonAoi``). This is
    the conversion.

    ``None`` in means ``None`` out: an unselected AOI is a normal state before
    the user has chosen, and ``validate()`` is what reports it.
    """
    if not selection:
        return None

    name = str(selection.get("name") or "aoi")

    asset_id = selection.get("asset_id")
    if asset_id:
        return AssetAoi(asset_id=str(asset_id), name=name)

    geojson = selection.get("geojson")
    if geojson:
        return GeoJsonAoi(geojson=geojson, name=name)

    return None
