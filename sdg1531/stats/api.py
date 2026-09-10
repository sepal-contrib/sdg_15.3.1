"""Async wrappers: build, await through the injected fetcher, decode.

The fetcher is a Protocol (:class:`sdg1531.ports.InfoFetcher`), so nothing here
imports pysepal. The app passes its ``GEEInterface``; the tests pass a
``FakeFetcher``.

Errors arrive in two shapes and only one of them is converted here. pysepal's
single-call ``get_info_async`` logs and RE-RAISES (``gee_interface.py:203-205``),
so an Earth Engine failure propagates out of these functions unchanged -- a caller
must catch that as well as :class:`~sdg1531.errors.StatisticsError`. The batch call
gathers with ``return_exceptions=True`` (``:210``), so there an Exception arrives as
a *value*; :func:`_unwrap` is what turns that into a chained ``StatisticsError``
rather than letting it fail later as an unrelated ``TypeError``.

EXPECTED_DIVERGENCES note -- three divergences from the legacy. Task 17's parity
harness must carry all three:

1. **Behaviour-changing.** :func:`fetch_zonal_areas` REFUSES a zone collection of
   more than 5000 features. ``zonal_statistics_to_geodataframe`` only remarked on
   the limit in a comment (run_15_3_1.py:542) and fetched anyway, usually to a
   timeout or an out-of-memory error further down. The entry is exactly that
   threshold: at or below 5000 features nothing changes, and the size probe that
   measures it is a separate, cheap request that adds one round trip.
2. **Behaviour-changing.** :func:`fetch_band_names` returns Earth Engine's own band
   order. ``widget/select_lc.py:63-65`` fed the same list through ``natsorted``
   before putting it in the dropdown. Display ordering is the app layer's (spec
   §4), so the sort moves there rather than being dropped; the entry covers the
   ORDER of this one function's result and nothing else. (The sibling
   :func:`fetch_distinct_pixel_values` sorts, which is
   ``sdg1531/stats/decode.py``'s EXPECTED_DIVERGENCES note 2, not this module's.)
3. **No legacy counterpart.** :func:`_unwrap` raising a chained ``StatisticsError``
   for an Exception that arrived as a value. The legacy had no batching fetcher at
   all -- every call was a blocking ``getInfo`` or ``urlopen`` -- so there is
   nothing to compare this against.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import ee
import geopandas as gpd
import pandas as pd

from sdg1531.enums import IndicatorLayer
from sdg1531.errors import StatisticsError
from sdg1531.ports import InfoFetcher

if TYPE_CHECKING:  # typing only; see stats/requests.py's note
    from sdg1531.engine.context import ExecutionContext
    from sdg1531.engine.indicator import IndicatorMaps

from .decode import (
    decode_areas_by_land_cover,
    decode_distinct_pixel_values,
    decode_transition_areas,
    decode_zonal_areas,
)
from .requests import (
    build_areas_by_land_cover,
    build_band_names,
    build_distinct_pixel_values,
    build_transition_areas,
    build_zonal_areas,
)

__all__ = [
    "fetch_areas_by_land_cover",
    "fetch_band_names",
    "fetch_distinct_pixel_values",
    "fetch_transition_areas",
    "fetch_zonal_areas",
]

# run_15_3_1.py:542 warns that above this the collection should go to Drive; the
# legacy warned in a comment and fetched anyway. See EXPECTED_DIVERGENCES note 1.
_MAX_ZONAL_FEATURES = 5000

# transcribed from run_15_3_1.py:343-350 - note the legacy spellings "Degrade" and
# "Improve", which name columns in every shapefile shipped so far.
#
# The ORDER is the legacy's too, and is not the natural 0-1-2-3: :343-350 assigns
# Class_0, Class_3, Class_2 then Class_1, and `decode_zonal_areas` adds the named
# columns in this table's iteration order, so this is the field order of the
# shapefile Task 18 writes. Users have tooling keyed on those fields; sorting the
# table would silently reorder them.
_ZONAL_LABELS: Mapping[int, str] = MappingProxyType(
    {
        0: "NoData",  # :343-344
        3: "Improve",  # :345-346
        2: "Stable",  # :347-348
        1: "Degrade",  # :349-350
    }
)


def _unwrap(payload: Any, *, what: str) -> Any:
    """A fetcher may hand back an Exception instead of raising it.

    pysepal's gee_interface.py:210 gathers with ``return_exceptions=True``, so a
    batch element is an Exception *instance*. Chain it rather than letting a
    later ``payload["groups"]`` fail with an unrelated TypeError.
    """
    if isinstance(payload, BaseException):
        raise StatisticsError(f"Earth Engine failed while computing {what}: {payload}") from payload
    return payload


def _require_groups(payload: Any, *, what: str) -> Any:
    payload = _unwrap(payload, what=what)
    if not isinstance(payload, Mapping) or payload.get("groups") is None:
        raise StatisticsError(
            f"Earth Engine returned no 'groups' for {what}; the area table is empty."
        )
    return payload["groups"]


async def fetch_transition_areas(
    fetcher: InfoFetcher, maps: IndicatorMaps, ctx: ExecutionContext
) -> pd.DataFrame:
    payload = await fetcher.get_info_async(build_transition_areas(maps, ctx))
    groups = _require_groups(payload, what="land cover transitions")
    return decode_transition_areas(groups, maps.resolved)


async def fetch_areas_by_land_cover(
    fetcher: InfoFetcher,
    maps: IndicatorMaps,
    ctx: ExecutionContext,
    *,
    layer: IndicatorLayer,
) -> pd.DataFrame:
    request = build_areas_by_land_cover(maps, ctx, layer=layer)
    payload = await fetcher.get_info_async(request)
    groups = _require_groups(payload, what=f"areas by land cover for {layer.value}")
    return decode_areas_by_land_cover(groups, maps.resolved, layer=layer)


async def fetch_zonal_areas(
    fetcher: InfoFetcher, maps: IndicatorMaps, zones: ee.FeatureCollection, *, scale: int
) -> gpd.GeoDataFrame:
    count = _unwrap(await fetcher.get_info_async(zones.size()), what="the zone count")
    if count is not None and int(count) > _MAX_ZONAL_FEATURES:
        raise StatisticsError(
            f"The zone collection has {int(count)} features; zonal statistics are "
            f"fetched in one request and are limited to {_MAX_ZONAL_FEATURES}. "
            "Split the collection or export it from Earth Engine instead."
        )
    payload = await fetcher.get_info_async(build_zonal_areas(maps, zones, scale=scale))
    return decode_zonal_areas(_unwrap(payload, what="zonal statistics"), labels=_ZONAL_LABELS)


async def fetch_distinct_pixel_values(fetcher: InfoFetcher, asset_id: str) -> tuple[int, ...]:
    payload = await fetcher.get_info_async(build_distinct_pixel_values(asset_id))
    return decode_distinct_pixel_values(_unwrap(payload, what=f"the pixel values of {asset_id}"))


async def fetch_band_names(fetcher: InfoFetcher, asset_id: str) -> tuple[str, ...]:
    payload = _unwrap(
        await fetcher.get_info_async(build_band_names(asset_id)),
        what=f"the band names of {asset_id}",
    )
    if payload is None:
        raise StatisticsError(f"Earth Engine returned no band names for {asset_id}.")
    return tuple(str(name) for name in payload)
