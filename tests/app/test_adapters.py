"""The one seam between pysepal and the domain."""

from __future__ import annotations

import inspect

import pytest
from pysepal.scripts.gee_interface import GEEInterface
from pysepal.solara.components.aoi.aoi_result import AoiResult
from pysepal.solara.components.aoi.aoi_spec import AoiSpec as PysepalAoiSpec

from app.adapters import to_domain_aoi
from sdg1531.ports import InfoFetcher
from sdg1531.spec import AdminAoi, AssetAoi, GeoJsonAoi


def _params(func) -> list[str]:
    return [
        name
        for name, p in inspect.signature(func).parameters.items()
        if name != "self" and p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    ]


def test_the_real_gee_interface_satisfies_the_protocol_by_parameter_name():
    """A Protocol matches positional-or-keyword parameters BY NAME, so the
    declared names are load-bearing. Checked as a prefix, not an equality:
    pysepal's real ``get_info_async`` carries a third defaulted parameter
    (``serialized_object``) that satisfies the Protocol, and an equality
    check would reject the real implementor.

    This asserts against the class, not an instance: constructing a
    ``GEEInterface`` with no session resolves machine credentials, which
    this test has no business doing. Inspecting the unbound methods needs
    neither a session nor a running event loop."""
    for name in ("get_info_async", "get_info_batch_async"):
        declared = _params(getattr(InfoFetcher, name))
        implemented = _params(getattr(GEEInterface, name))
        assert implemented[: len(declared)] == declared, name
        assert inspect.iscoroutinefunction(getattr(GEEInterface, name)), name


def test_an_asset_result_becomes_the_asset_arm():
    """Shaped exactly as ``pysepal.solara.components.aoi.asset.process_asset``
    builds a real ASSET result: the asset id lives on ``spec``, the name on
    the result itself."""
    spec = PysepalAoiSpec(method="ASSET", asset_id="users/x/aoi", asset_type="TABLE")
    result = AoiResult(method="ASSET", name="aoi", spec=spec)
    assert to_domain_aoi(result) == AssetAoi(asset_id="users/x/aoi", name="aoi")


def test_a_drawn_result_becomes_the_geojson_arm():
    """Shaped exactly as ``...aoi.draw.process_draw`` builds a real DRAW
    result: the geometry is ``spec.geo_json`` (no underscore-free alias)."""
    geometry = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}}],
    }
    spec = PysepalAoiSpec(method="DRAW", name="drawn", geo_json=geometry)
    result = AoiResult(method="DRAW", name="drawn", spec=spec)
    aoi = to_domain_aoi(result)
    assert isinstance(aoi, GeoJsonAoi)
    assert aoi.geojson == geometry


@pytest.mark.parametrize("method", ["ADMIN0", "ADMIN1", "ADMIN2"])
# "3431" and "04321" differ in both length and leading zero: the adapter
# never validates against pygaul (see the docstring below), so unlike the
# domain-side context test these need not be real GAUL entries, and can be
# picked specifically to kill a shape-preserving transform -- `[:4]` or
# `.lstrip("0")` -- that a same-length, no-leading-zero pair would miss.
@pytest.mark.parametrize("code", ["3431", "04321"])
def test_an_admin_selection_becomes_an_admin_aoi(method, code):
    result = AoiResult(method=method, name="COL_Cundinamarca", admin=code, gee=True)
    assert to_domain_aoi(result) == AdminAoi(admin_code=code, name="COL_Cundinamarca")


def test_an_admin_selection_without_a_code_is_not_convertible():
    assert to_domain_aoi(AoiResult(method="ADMIN1", name="x", admin=None, gee=True)) is None


def test_no_selection_is_none_not_an_error():
    """The AOI step renders before the user has chosen anything; that is a
    normal state, and validate() is what reports it as a problem."""
    assert to_domain_aoi(None) is None


@pytest.mark.parametrize("method", ["SHAPE", "POINTS"])
def test_a_local_file_method_has_no_domain_arm(method):
    """SHAPE and POINTS read paths local to the machine that ran the picker,
    which a SEPAL container does not have -- they have no domain arm at all,
    unlike ASSET/DRAW/ADMIN which merely need a non-empty payload to convert.
    A bogus arm for either method would silently persist a path the run can
    never read; this is what stands between that and ``None``."""
    result = AoiResult(
        method=method,
        name="local",
        spec=PysepalAoiSpec(method=method, pathname="/home/user/local.shp"),
    )
    assert to_domain_aoi(result) is None
