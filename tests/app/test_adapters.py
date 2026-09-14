"""The one seam between pysepal and the domain."""

from __future__ import annotations

import inspect

import pytest

from app.adapters import GeeInfoFetcher, to_domain_aoi
from sdg1531.ports import InfoFetcher
from sdg1531.spec import AssetAoi, GeoJsonAoi


class _FakeInterface:
    async def get_info_async(self, ee_object=None, tag=None, serialized_object=None):
        return {"ok": True}

    async def get_info_batch_async(self, ee_objects):
        return [{"ok": True} for _ in ee_objects]


def _params(func) -> list[str]:
    return [
        name
        for name, p in inspect.signature(func).parameters.items()
        if name != "self" and p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    ]


def test_the_fetcher_satisfies_the_protocol_by_parameter_name():
    """A Protocol matches positional-or-keyword parameters BY NAME, so the
    declared names are load-bearing. Checked as a prefix, not an equality:
    pysepal's get_info_async carries a third defaulted parameter
    (serialized_object) that satisfies the Protocol, and an equality check
    would reject the real implementor."""
    fetcher = GeeInfoFetcher(_FakeInterface())
    for name in ("get_info_async", "get_info_batch_async"):
        declared = _params(getattr(InfoFetcher, name))
        implemented = _params(getattr(fetcher, name))
        assert implemented[: len(declared)] == declared, name
        assert inspect.iscoroutinefunction(getattr(fetcher, name)), name


@pytest.mark.asyncio
async def test_the_fetcher_delegates_to_the_interface():
    fetcher = GeeInfoFetcher(_FakeInterface())
    assert await fetcher.get_info_async(object()) == {"ok": True}
    assert await fetcher.get_info_batch_async([object(), object()]) == [
        {"ok": True},
        {"ok": True},
    ]


def test_an_asset_aoi_becomes_the_asset_arm():
    """pysepal's AOI result for the ASSET method carries an asset id; the
    domain's AssetAoi arm carries that plus the name the run labels itself
    with."""
    aoi = to_domain_aoi({"method": "ASSET", "asset_id": "users/x/aoi", "name": "aoi"})
    assert aoi == AssetAoi(asset_id="users/x/aoi", name="aoi")


def test_a_drawn_aoi_becomes_the_geojson_arm():
    geometry = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
    aoi = to_domain_aoi({"method": "DRAW", "geojson": geometry, "name": "drawn"})
    assert isinstance(aoi, GeoJsonAoi)
    assert aoi.geojson == geometry


def test_no_selection_is_none_not_an_error():
    """The AOI step renders before the user has chosen anything; that is a
    normal state, and validate() is what reports it as a problem."""
    assert to_domain_aoi(None) is None
