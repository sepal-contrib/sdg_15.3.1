"""Build the ee objects the statistics need. No fetching, no decoding.

This module owns half of the STATISTICS vocabulary: :data:`_STATS_BAND`, the band
each layer's areas are counted on. The other half, the legend those classes are
named in, is :data:`~sdg1531.stats.decode._STATS_LABELS` in ``decode.py``, which
must stay free of ``ee``.

**Both tables are written out in full, per layer, and are deliberately NOT derived
from** :class:`~sdg1531.engine.indicator.ClassifiedLayer`. That class carries the
MAP AND EXPORT vocabulary of spec §8; this one carries what
``indicator_n_category_label`` (run_15_3_1.py:425-450) counted. For five layers the
two agree. For two they must not:

===========================  ===================  ======================  ==================
Layer                        Export band (§8)     Statistics band (here)  Statistics legend
===========================  ===================  ======================  ==================
``PRODUCTIVITY_TREND``       ``trajectory``       ``trajectory_5_levels``  6 entries
``PRODUCTIVITY_STATE``       ``state``            ``state_5_levels``       6 entries
===========================  ===================  ======================  ==================

Both are correct, for different consumers: the legacy statistics deliberately
counted trend and state in six categories off the 5-level bands (:437-442), while
§8 gives those layers a 3-class band and a 4-entry legend to draw and export --
something the legacy never rendered at all (see
``sdg1531/engine/indicator.py``'s EXPECTED_DIVERGENCES note 4). Deriving one table
from the other, or "unifying" them, would silently republish the trend and state
statistics with four categories instead of six.
``tests/test_stats_requests.py::test_the_statistics_vocabulary_deliberately_differs_from_the_export_vocabulary``
fails if either drifts onto the other.

EXPECTED_DIVERGENCES note -- one divergence from the legacy. Task 17's parity
harness must carry it:

1. **Behaviour-changing, and scoped to the TRANSPORT of two requests.** The legacy
   fetched the two area tables by wrapping the reduction in ``ee.Feature(None, ...)``
   inside a one-element ``ee.FeatureCollection``, taking a ``getDownloadURL``
   ``geojson`` link and reading it with ``urlopen`` (run_15_3_1.py:236-239,
   :284-287). That blocks the event loop and goes out over an unauthenticated URL
   rather than through the pysepal session. :func:`build_transition_areas` and
   :func:`build_areas_by_land_cover` return the ``ee.Dictionary`` itself and
   ``sdg1531/stats/api.py`` awaits it through the injected
   :class:`~sdg1531.ports.InfoFetcher`.

   What differs is the two wrapper nodes and the endpoint, and nothing else. The
   ``Image.reduceRegion`` node is node-for-node the legacy's -- same reducer, same
   grouping, same geometry, scale, ``maxPixels``, ``bestEffort`` and ``tileScale``
   -- and the payload is the same object: the download wrapper put the group list
   at ``["features"][0]["properties"]["groups"]``, awaiting the dictionary puts it
   at ``["groups"]``. **This entry licenses no numeric, band, scale or reducer
   difference**; a parity run that finds one has found a real regression.

   The three call sites that already used ``getInfo`` (``:544``, ``:421``,
   ``widget/select_lc.py:64``) move to the same fetcher with no graph change at
   all, so they are part of no entry.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import ee

from sdg1531.enums import IndicatorLayer

if TYPE_CHECKING:
    # Typing only. Neither is needed at runtime, and `engine/indicator.py` does not
    # import `stats`, so naming them here creates no cycle in either direction.
    from sdg1531.engine.context import ExecutionContext
    from sdg1531.engine.indicator import IndicatorMaps

__all__ = [
    "build_areas_by_land_cover",
    "build_band_names",
    "build_distinct_pixel_values",
    "build_transition_areas",
    "build_zonal_areas",
]

# 1e13 is a FLOAT on purpose: `ee.serializer.encode` emits `10000000000000.0` for it
# and `10000000000000` for `int(1e13)`, which are different JSON, and the legacy has
# always passed the float (run_15_3_1.py:230, :276, :508). `ee`'s own signature types
# `maxPixels` as an integer, so the call sites wrap it in `ee.Number` -- which is in
# the accepted type and encodes to the identical constant, as
# `test_max_pixels_reaches_every_reducer_as_the_legacy_float` pins.
_MAX_PIXELS = 1e13
_TILE_SCALE = 2
_BEST_EFFORT = True
_M2_PER_HA = 10000

# run_15_3_1.py:478 and :481 declare these as defaults; the module's only call site
# passes 1000000 and 1.0 at :332 and :335, so 1.0 is the tile scale that ever ran
# (the 2.0 default is dead). The denominator turns m2 into SQUARE KILOMETRES -- the
# legacy's own comment at :478 says "hectares", and is simply wrong; the value is
# transcribed, the comment is not.
_ZONAL_DENOMINATOR = 1000000
_ZONAL_TILE_SCALE = 1.0

# transcribed from run_15_3_1.py:425-450 (indicator_n_category_label): the band each
# layer's statistics are counted on. None means "no select", as in the legacy. See
# the module docstring: for trend and state this deliberately disagrees with
# ClassifiedLayer.band, and unifying the two would change the published statistics.
_STATS_BAND: Mapping[IndicatorLayer, str | None] = MappingProxyType(
    {
        IndicatorLayer.PRODUCTIVITY: None,  # :428-429
        IndicatorLayer.SOC: "soc",  # :431-432
        IndicatorLayer.LAND_COVER: "degradation",  # :434-435
        IndicatorLayer.PRODUCTIVITY_STATE: "state_5_levels",  # :437-438
        IndicatorLayer.PRODUCTIVITY_TREND: "trajectory_5_levels",  # :440-441
        IndicatorLayer.PRODUCTIVITY_PERFORMANCE: None,  # :443-444
        IndicatorLayer.INDICATOR_15_3_1: None,  # :446-447
    }
)


def build_transition_areas(maps: IndicatorMaps, ctx: ExecutionContext) -> ee.Dictionary:
    """Area per land cover transition class. Reads ``maps.land_cover.stack``."""
    # transcribed from run_15_3_1.py:212-234
    landcover: ee.Image = maps.land_cover.stack.select("transition")
    pixel_area: ee.Image = ee.Image.pixelArea().divide(_M2_PER_HA).addBands(landcover.selfMask())
    return pixel_area.reduceRegion(
        reducer=ee.Reducer.sum().group(1, "lc_comb"),
        geometry=ctx.bounds,
        scale=ctx.analysis_scale,
        maxPixels=ee.Number(_MAX_PIXELS),
        bestEffort=_BEST_EFFORT,
        tileScale=_TILE_SCALE,
    )


def build_areas_by_land_cover(
    maps: IndicatorMaps, ctx: ExecutionContext, *, layer: IndicatorLayer
) -> ee.Dictionary:
    """Area per (indicator class, land cover class).

    Reads ``maps.land_cover.stack`` and ``maps.layers()[layer].image``. The land
    cover side is always the ``start`` band: ``compute_stats_by_lc``'s
    ``select_landcover`` argument (run_15_3_1.py:253) is only ever left at its
    default, and its label mapping at :266 is keyed on the start vocabulary
    regardless, so an ``end`` call would have mislabelled anyway.

    The indicator side is ``_STATS_BAND[layer]``, not ``layer.band`` -- see the
    module docstring.
    """
    # transcribed from run_15_3_1.py:258-282
    landcover: ee.Image = maps.land_cover.stack.select("start")

    indicator: ee.Image = maps.layers()[layer].image
    band = _STATS_BAND[layer]
    if band is not None:
        indicator = indicator.select(band)

    # band order is load-bearing: area is band 0, land cover band 1, the indicator
    # band 2, which is exactly what group(1, "lc") and group(2, "indicator") name.
    combined: ee.Image = (
        ee.Image.pixelArea().divide(_M2_PER_HA).addBands(landcover).addBands(indicator)
    )
    return combined.reduceRegion(
        reducer=ee.Reducer.sum().group(1, "lc").group(2, "indicator"),
        geometry=ctx.bounds,
        maxPixels=ee.Number(_MAX_PIXELS),
        scale=ctx.analysis_scale,
        bestEffort=_BEST_EFFORT,
        tileScale=_TILE_SCALE,
    )


def build_zonal_areas(
    maps: IndicatorMaps, zones: ee.FeatureCollection, *, scale: int
) -> ee.FeatureCollection:
    """Per-zone area of each indicator class, as ``Class_N`` properties.

    ``zones`` is the caller's own collection, not ``ctx``: the legacy passed
    ``aoi_model.feature_collection`` (:331) but the port lets the app zone by any
    collection, and the reduction is per feature geometry either way.
    """
    # transcribed from run_15_3_1.py:487-539
    value_raster: ee.Image = maps.layers()[IndicatorLayer.INDICATOR_15_3_1].image
    collection: ee.FeatureCollection = zones

    # `-> ee.Element` because that is what `Element.set` is typed to return; the
    # object is a Feature, and `Collection.map` takes any element-returning callable.
    def calculate_class_areas(feature: ee.Feature) -> ee.Element:
        pixel_area: ee.Image = ee.Image.pixelArea()
        # :495 -- by INDEX, so the layer's band name is deliberately not consulted
        val_raster: ee.Image = value_raster.select([0])
        combined: ee.Image = pixel_area.addBands(val_raster)

        stats: ee.Dictionary = combined.reduceRegion(
            reducer=ee.Reducer.sum().group(groupField=1, groupName="class"),
            geometry=feature.geometry(),
            scale=scale,
            maxPixels=ee.Number(_MAX_PIXELS),
            tileScale=_ZONAL_TILE_SCALE,
        )

        groups: ee.List = ee.List(stats.get("groups"))

        def create_dict(group: Any) -> ee.List:
            entry: ee.Dictionary = ee.Dictionary(group)
            key: ee.String = ee.Number(entry.get("class")).format("Class_%d")
            value: ee.Number = ee.Number(entry.get("sum")).divide(_ZONAL_DENOMINATOR)
            pair: ee.List = ee.List([key, value])
            return pair

        # :525-531 -- a zone that overlaps no pixel yields an empty group list, and
        # ee.Dictionary([]) would fail; the If keeps the feature with no Class_N at all
        new_props: ee.Dictionary = ee.Dictionary(
            ee.Algorithms.If(
                groups.size().gt(0),
                ee.Dictionary(groups.map(create_dict).flatten()),
                ee.Dictionary({}),
            )
        )

        return feature.set(new_props)

    mapped: ee.FeatureCollection = collection.map(calculate_class_areas)
    return mapped


def build_distinct_pixel_values(asset_id: str) -> ee.List:
    """The distinct pixel values of a custom land cover asset."""
    # transcribed from run_15_3_1.py:414-422, minus the getInfo at :421
    image: ee.Image = ee.Image(asset_id)
    geometry: ee.Geometry = image.geometry()
    reduction: ee.Dictionary = image.reduceRegion(
        ee.Reducer.frequencyHistogram(), geometry, bestEffort=True
    )
    histogram: ee.Dictionary = ee.Dictionary(reduction.get(image.bandNames().get(0)))
    return histogram.keys()


def build_band_names(asset_id: str) -> ee.List:
    """The band names of an asset.

    transcribed from ``widget/select_lc.py:63-65``, whose ``getInfo()`` runs inside
    a traitlets observer and blocks the kernel while it waits.
    """
    image: ee.Image = ee.Image(asset_id)
    return image.bandNames()
