"""Annual VI and climate integration.

Transcribed from ``component/scripts/integration.py``. Phase 1 is a
transcription, not a refactor: every node this module builds must match the
legacy graph node for node, so the ugly parts (``ee.Image().constant``, the
un-merged monthly path, the MODIS rung merging a second asset whatever sensor it
belongs to) are preserved and annotated rather than corrected.

ResolvedSpec fields read here:
    integration_period, vi_processor, vi_assets, spec.vi_source,
    spec.vegetation_index, spec.threshold

EXPECTED_DIVERGENCES note -- one divergence from the legacy. The parity harness
must carry it:

1. **No legacy counterpart.** The rungs that consume ``spec.threshold`` (MODIS,
   Sentinel 2, the Landsat sensors, Derived VI Landsat) narrow it with
   ``require_float`` and raise ``SpecError`` if it is unset. ``vi_threshold``
   (integration.py:410-415) calls ``img.gt(threshold)`` unconditionally, and
   ``ee.Image.gt(None)`` builds an ``Image.gt`` node with its ``image2``
   argument simply ABSENT -- so the legacy shipped a graph that looks well
   formed and fails only on evaluation. Terra NPP is deliberately outside the
   entry: ``process_terra_npp`` (:134-142) takes no threshold argument, so that
   rung still builds with the field unset. Pinned by
   ``test_an_unset_threshold_raises_on_every_rung_that_consumes_it`` and its
   companion ``test_terra_npp_still_builds_without_a_threshold``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from functools import partial
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, assert_never

import ee

from sdg1531.catalog import ASSETS
from sdg1531.engine._typing import as_collection, as_element, require_float, require_int
from sdg1531.enums import VegetationIndex
from sdg1531.errors import SpecError
from sdg1531.resolve import ResolvedSpec, ViProcessor
from sdg1531.spec import SensorSelection

if TYPE_CHECKING:  # typing only -- no runtime dependency on context
    from sdg1531.engine.context import ExecutionContext

__all__ = ["build_climate_collection", "build_vi_collection"]

# The membership list `cloud_mask` (integration.py:248) and `apply_scale_factor`
# (:292) test against -- two legacy call sites, one tuple. Changing it moves both
# behaviours at once. The third call site, the ladder's own test at :81-83, is
# `resolve._LANDSAT_SENSORS` now.
_LANDSAT_SR_SENSORS = (
    "Landsat 4",
    "Landsat 5",
    "Landsat 7",
    "Landsat 8",
    "Landsat 9",
)
_LANDSAT_OLD = ("Landsat 4", "Landsat 5", "Landsat 7")
_LANDSAT_NEW = ("Landsat 8", "Landsat 9")


def build_climate_collection(r: ResolvedSpec, ctx: ExecutionContext) -> ee.ImageCollection:
    """Annual mean precipitation, one image per year of the integration period.

    Transcribed from integration.py:10-28 (``integrate_climate``). The period
    envelope itself is resolved upstream; integration.py:11-19 recomputed it
    inline.
    """
    period_start = require_int(r.integration_period.start, "integration_period.start")
    period_end = require_int(r.integration_period.end, "integration_period.end")

    # transcribed from integration.py:20-25
    precipitation = (
        ee.ImageCollection(ASSETS["precipitation"])
        .filterBounds(ctx.feature_collection)
        .filterDate(f"{period_start}-01-01", f"{period_end}-12-31")
        .select("precipitation")
    )

    return _annual_climate(precipitation, period_start, period_end)


def _annual_climate(precipitation: ee.ImageCollection, start: int, end: int) -> ee.ImageCollection:
    """Transcribed from integration.py:337-353 (``int_yearly_climate``)."""
    years = ee.List.sequence(start, end)

    return as_collection(
        ee.ImageCollection.fromImages(
            years.map(
                lambda year: (
                    precipitation.filter(ee.Filter.calendarRange(year, field="year"))
                    .reduce(ee.Reducer.mean())
                    .rename("clim")
                    # ee.Image().constant(...) is how the legacy spells it; the
                    # instance call encodes the same node as ee.Image.constant(...)
                    # only if transcribed verbatim, so leave it alone.
                    .addBands(ee.Image().constant(year).float().rename("year"))
                    .set("year", year)
                )
            )
        )
    )


def _annual_mean(collection: ee.ImageCollection, start: int, end: int) -> ee.ImageCollection:
    """Transcribed from integration.py:424-438 (``annual_modis_vi``)."""
    years = ee.List.sequence(start, end)

    return as_collection(
        ee.ImageCollection.fromImages(
            years.map(
                lambda year: (
                    collection.filter(ee.Filter.calendarRange(year, field="year"))
                    .reduce(ee.Reducer.mean())
                    .rename("vi")
                    .addBands(ee.Image().constant(year).float().rename("year"))
                    .set("year", year)
                )
            )
        )
    )


def _annual_npp(npp_coll: ee.ImageCollection, start: int, end: int) -> ee.ImageCollection:
    """Transcribed from integration.py:441-453 (``preproc_modis_npp``)."""
    years = ee.List.sequence(start, end)

    return as_collection(
        ee.ImageCollection.fromImages(
            years.map(
                lambda year: (
                    npp_coll.filter(ee.Filter.calendarRange(year, field="year"))
                    .first()
                    .multiply(0.0001)
                    .rename("vi")
                    .addBands(ee.Image().constant(year).float().rename("year"))
                    .set("year", year)
                )
            )
        )
    )


def _annual_mean_via_monthly(
    vi_coll: ee.ImageCollection, start: int, end: int
) -> ee.ImageCollection:
    """Transcribed from integration.py:305-334 (``int_yearly_ndvi``).

    Note this path emits a single ``vi`` band and NO ``year`` band -- only the
    ``year`` property -- unlike _annual_mean above. Preserved as found.
    """

    def daily_to_monthly_to_annual(year: ee.Number) -> ee.Element:
        ndvi_collection = vi_coll
        ndvi_coll_ann = ndvi_collection.filter(ee.Filter.calendarRange(year, field="year"))
        months = (
            ndvi_coll_ann.aggregate_array("system:time_start")
            .map(lambda x: ee.Number.parse(ee.Date(x).format("MM")))
            .distinct()
        )

        img_coll = ee.ImageCollection.fromImages(
            months.map(
                lambda month: ndvi_coll_ann.filter(
                    ee.Filter.calendarRange(month, field="month")
                ).reduce(ee.Reducer.mean())
            )
        )
        img_coll_ndvi = img_coll.reduce(ee.Reducer.mean()).float().rename("vi").set("year", year)
        return as_element(img_coll_ndvi)

    years = ee.List.sequence(start, end)
    return as_collection(ee.ImageCollection.fromImages(years.map(daily_to_monthly_to_annual)))


def _calculate_ndvi(img: ee.Image) -> ee.Element:
    """Transcribed from integration.py:356-369.

    Returns ee.Element, not ee.Image: the chain ends in ``.set()``, which the
    installed ee stubs type as ee.Element (ee/element.py:122-131).
    """
    red = img.select("Red")
    nir = img.select("NIR")

    ndvi = (
        nir.subtract(red)
        .divide(nir.add(red))
        .rename("ndvi")
        .set("system:time_start", img.get("system:time_start"))
    )

    return as_element(ndvi)


def _calculate_evi(img: ee.Image) -> ee.Element:
    """Transcribed from integration.py:372-383."""
    evi = (
        img.expression(
            "2.4*((nir-red)/(nir+red+1))",
            {"nir": img.select("NIR"), "red": img.select("Red")},
        )
        .rename("evi")
        .set("system:time_start", img.get("system:time_start"))
    )
    return as_element(evi)


def _calculate_msvi(img: ee.Image) -> ee.Element:
    """Transcribed from integration.py:386-395."""
    msvi2 = (
        img.expression(
            "(2 * nir + 1 - sqrt(pow((2 * nir + 1), 2) - 8 * (nir - red)) ) / 2",
            {"nir": img.select("NIR"), "red": img.select("Red")},
        )
        .rename("msvi")
        .set("system:time_start", img.get("system:time_start"))
    )
    return as_element(msvi2)


def _calculate_msvi_modis(img: ee.Image) -> ee.Element:
    """Transcribed from integration.py:398-407."""
    msvi2 = (
        img.expression(
            "(2 * nir + 1 - sqrt(pow((2 * nir + 1), 2) - 8 * (nir - red)) ) / 2",
            {"nir": img.select("sur_refl_b02"), "red": img.select("sur_refl_b01")},
        )
        .rename("msvi")
        .set("system:time_start", img.get("system:time_start"))
    )
    return as_element(msvi2)


# Replaces globals()[f"calculate_{vi_index}"] at integration.py:165 and :193.
_VI_BUILDERS: Mapping[VegetationIndex, Callable[[ee.Image], ee.Element]] = MappingProxyType(
    {
        VegetationIndex.NDVI: _calculate_ndvi,
        VegetationIndex.EVI: _calculate_evi,
        VegetationIndex.MSVI: _calculate_msvi,
    }
)


def _vi_expression(img: ee.Image, index: VegetationIndex) -> ee.Element:
    """Dispatch to the index builder. Raising default, spec 7."""
    try:
        builder = _VI_BUILDERS[index]
    except KeyError:
        raise SpecError(f"Unsupported vegetation index: {index}") from None
    return builder(img)


def _rename_bands(img: ee.Image, sensor: str) -> ee.Image:
    """Transcribed from integration.py:230-242 (``rename_band``).

    Falls through unchanged for any other sensor, exactly as the legacy does;
    only the Landsat and Sentinel paths ever call it.
    """
    if sensor in _LANDSAT_OLD:
        img = img.select(
            ["SR_B1", "SR_B3", "SR_B4", "QA_PIXEL"], ["Blue", "Red", "NIR", "pixel_qa"]
        )
    elif sensor in _LANDSAT_NEW:
        img = img.select(
            ["SR_B2", "SR_B4", "SR_B5", "QA_PIXEL"], ["Blue", "Red", "NIR", "pixel_qa"]
        )
    elif sensor == "Sentinel 2":
        img = img.select(["B2", "B4", "B8", "QA60"], ["Blue", "Red", "NIR", "QA60"])

    return img


def _bit_selection(bitmask: ee.Image, start_bit: int, end_bit: int) -> ee.Image:
    """Transcribed from integration.py:284-287."""
    bit_len = ee.Number(1).add(end_bit).subtract(start_bit)
    bit_position = ee.Number(1).leftShift(bit_len).subtract(1)
    return bitmask.rightShift(start_bit).bitwiseAnd(bit_position)


def _cloud_mask(img: ee.Image, sensor: str) -> ee.Element:
    """Transcribed from integration.py:245-281 (``cloud_mask``).

    The legacy rebinds ``img`` in every branch and returns once at the end;
    each branch returns directly here because the Sentinel arm ends in
    ``copyProperties``, which ee types as ee.Element rather than ee.Image, and
    rebinding an ``img: ee.Image`` parameter to it does not type-check. The
    emitted nodes are identical.
    """
    if sensor in _LANDSAT_SR_SENSORS:
        qa = img.select("pixel_qa")
        cloud = qa.bitwiseAnd(1 << 3).And(qa.bitwiseAnd(1 << 8)).Or(qa.bitwiseAnd(1 << 4))
        mask2 = img.mask().reduce(ee.Reducer.min())

        return img.updateMask(cloud.Not()).updateMask(mask2)

    if sensor == "Sentinel 2":
        qa = img.select("QA60")
        cloudBitMask = 1 << 10
        cirrusBitMask = 1 << 11
        mask = qa.bitwiseAnd(cloudBitMask).eq(0).And(qa.bitwiseAnd(cirrusBitMask).eq(0))
        return (
            img.updateMask(mask)
            .divide(10000)
            .copyProperties(img, ["system:time_start", "system:time_end"])
        )

    if sensor == "MODIS":
        qa = img.select("DetailedQA")
        viqamask1 = _bit_selection(qa, 0, 1).lte(1)
        snowmask = _bit_selection(qa, 14, 14).eq(0)
        shadowmask = _bit_selection(qa, 15, 15).eq(0)
        mixedcloudmask = _bit_selection(qa, 10, 10).eq(0)
        mask = viqamask1.And(snowmask).And(shadowmask).And(mixedcloudmask)
        return img.updateMask(mask)

    return img


def _apply_scale_factor(img: ee.Image, sensor: str) -> ee.Element:
    """Transcribed from integration.py:290-302.

    The legacy leaves ``scalled_img`` unbound for any other sensor
    (UnboundLocalError); spec 7 replaces that with an explicit raise.
    """
    if sensor in _LANDSAT_SR_SENSORS:
        scalled_img = (
            img.multiply(0.0000275)
            .add(-0.2)
            .copyProperties(img, ["system:time_start", "system:time_end"])
        )
    elif sensor == "Sentinel 2":
        scalled_img = img.multiply(0.0001).copyProperties(
            img, ["system:time_start", "system:time_end"]
        )
    else:
        raise SpecError(f"No scale factor is defined for sensor {sensor!r}.")
    return scalled_img


def _apply_vi_threshold(img: ee.Image, threshold: float) -> ee.Element:
    """Transcribed from integration.py:410-415 (``vi_threshold``)."""
    threshold_bin = img.gt(threshold)
    return img.multiply(threshold_bin).copyProperties(img, ["system:time_start", "system:time_end"])


def _img_scaling(img: ee.Image, scale_factor: float) -> ee.Element:
    """Transcribed from integration.py:418-421 (``img_scalling``)."""
    return img.multiply(scale_factor).copyProperties(img, ["system:time_start", "system:time_end"])


def _sensor_names(r: ResolvedSpec) -> tuple[str, ...]:
    """The selection's sensor names, which three of the rungs still need.

    Raw spec data rather than a derivation, so it is read off the spec and not
    off a resolved field. ``RunSpec.vi_source`` is ``ViSource | None``; every
    rung that calls this was reached through ``_vi_dispatch``'s
    ``SensorSelection`` arm, so the narrowing below cannot fail for a
    ``ResolvedSpec`` that ``resolve()`` produced.
    """
    source = r.spec.vi_source
    if not isinstance(source, SensorSelection):
        raise SpecError(f"Unsupported VI source: {source!r}")
    return tuple(source.names)


def build_vi_collection(r: ResolvedSpec, ctx: ExecutionContext) -> ee.ImageCollection:
    """Annual integrated vegetation index for the integration period.

    Transcribed from integration.py:31-95 (``integrate_vi``), less its sensor
    dispatch: the ORDERED LADDER of :45-94 is walked once, by
    ``sdg1531.resolve._vi_dispatch``, and this reads the rung it picked off
    ``r.vi_processor`` and the asset ids it resolved off ``r.vi_assets``. That
    includes the derived-VI branch of :66-71, asset swap and all, so the index
    and the compatibility flag are not consulted here.

    HOW MUCH of ``vi_assets`` a rung consumes differs by rung, and the
    difference is legacy-faithful: ``_process_modis`` reads only the first two
    entries however many sensors were selected (:106-111); Terra NPP, Sentinel 2
    and the derived-VI composite take the first alone (:136, :59, :67-71); and
    only ``_process_landsat_sensors`` walks the whole list (:149-162).
    """
    if r.vi_processor is ViProcessor.PRECOMPUTED:
        # integration.py:79-80's "GEE Asset" branch is dropped: it read a trait
        # that does not exist, and "GEE Asset" is not a key of pm.sensors so
        # :42 would KeyError first. The replacement arm is not wired yet.
        raise SpecError(
            "A precomputed VI asset is not supported in phase 1; select sensors instead."
        )

    period_start = require_int(r.integration_period.start, "integration_period.start")
    period_end = require_int(r.integration_period.end, "integration_period.end")
    index = r.spec.vegetation_index
    # Not narrowed here: Terra NPP never reads a threshold (integration.py:
    # 134-142 -- process_terra_npp takes no threshold argument), so narrowing
    # this early would raise on a Terra NPP spec the legacy ran successfully.
    # Each rung that actually consumes `threshold` narrows it itself, at the
    # point of consumption.
    threshold = r.spec.threshold
    # `ViAsset` is `str | tuple[str, str]`: the "Derived VI Landsat" record is a
    # PAIR, and a rung that wins the ladder over it hands that pair to
    # `ee.ImageCollection` nested and unresolved, exactly as integration.py:
    # 41-43 did. `Any` is what carrying that faithfully costs.
    vi_assets: Sequence[Any] = r.vi_assets

    match r.vi_processor:
        case ViProcessor.MODIS:
            return _process_modis(
                _sensor_names(r), vi_assets, index, threshold, period_start, period_end
            )
        case ViProcessor.TERRA_NPP:
            return _process_terra_npp(vi_assets, period_start, period_end)
        case ViProcessor.SENTINEL2:
            # :59 passes sensors[0], not "Sentinel 2"; preserved.
            return _process_sentinel2(
                ctx.feature_collection,
                _sensor_names(r)[0],
                vi_assets[0],
                index,
                threshold,
                period_start,
                period_end,
            )
        case ViProcessor.DERIVED_VI_LANDSAT:
            return _process_landsat_derived_vi(
                ctx.feature_collection, vi_assets[0], threshold, period_start, period_end
            )
        case ViProcessor.LANDSAT_SENSORS:
            return _process_landsat_sensors(
                ctx.feature_collection,
                _sensor_names(r),
                vi_assets,
                index,
                threshold,
                period_start,
                period_end,
            )
        case _:
            # ViProcessor is a closed enum, so this is unreachable -- and
            # `assert_never` makes mypy say so at type-check time rather than
            # waiting for the rung-coverage test to catch a new member.
            assert_never(r.vi_processor)


def _process_modis(
    sensor_list: Sequence[str],
    ee_asset_list: Sequence[Any],
    index: VegetationIndex,
    threshold: float | None,
    period_start: int,
    period_end: int,
) -> ee.ImageCollection:
    """Transcribed from integration.py:98-131."""
    threshold = require_float(threshold, "spec.threshold")
    modis_coll_ = ee.ImageCollection(ee_asset_list[0]).filterDate(
        f"{period_start}-01-01", f"{period_end}-12-31"
    )

    # merge the collection if both the MODIS sensors are selected
    if len(sensor_list) > 1:
        modis_coll_ = modis_coll_.merge(
            ee.ImageCollection(ee_asset_list[1]).filterDate(
                f"{period_start}-01-01", f"{period_end}-12-31"
            )
        )

    modis_coll = modis_coll_.map(partial(_cloud_mask, sensor="MODIS"))

    if index in (VegetationIndex.NDVI, VegetationIndex.EVI):
        modis_vi_scalled = modis_coll.select(index.value.upper()).map(
            partial(_img_scaling, scale_factor=0.0001)
        )
        modis_vi_w_threshold = modis_vi_scalled.map(
            partial(_apply_vi_threshold, threshold=threshold)
        )
    elif index is VegetationIndex.MSVI:
        modis_vi_scalled = modis_coll.map(_calculate_msvi_modis).select("msvi")
        modis_vi_w_threshold = modis_vi_scalled.map(
            partial(_apply_vi_threshold, threshold=threshold)
        )
    else:
        raise SpecError(f"Unsupported vegetation index: {index}")

    return _annual_mean(modis_vi_w_threshold, period_start, period_end)


def _process_terra_npp(
    ee_asset_list: Sequence[Any], period_start: int, period_end: int
) -> ee.ImageCollection:
    """Transcribed from integration.py:134-142."""
    npp_filtered = (
        ee.ImageCollection(ee_asset_list[0])
        .filterDate(f"{period_start}-01-01", f"{period_end}-12-31")
        .select("Npp")
    )
    return _annual_npp(npp_filtered, period_start, period_end)


def _process_landsat_sensors(
    aoi: ee.FeatureCollection,
    sensor_list: Sequence[str],
    ee_asset_list: Sequence[Any],
    index: VegetationIndex,
    threshold: float | None,
    period_start: int,
    period_end: int,
) -> ee.ImageCollection:
    """Transcribed from integration.py:146-175."""
    threshold = require_float(threshold, "spec.threshold")
    i_img_coll = ee.ImageCollection([])

    for sensor, asset_id in zip(sensor_list, ee_asset_list, strict=True):
        sat = (
            ee.ImageCollection(asset_id)
            .filterBounds(aoi)
            .filterDate(f"{period_start}-01-01", f"{period_end}-12-31")
            .filter(ee.Filter.lt("CLOUD_COVER_LAND", 20))
            .map(partial(_rename_bands, sensor=sensor))
            .map(partial(_cloud_mask, sensor=sensor))
            .map(partial(_apply_scale_factor, sensor=sensor))
        )

        i_img_coll = i_img_coll.merge(sat)

    vi_coll = i_img_coll.map(partial(_vi_expression, index=index)).select(index.value)
    vi_coll_w_threshold = vi_coll.map(partial(_apply_vi_threshold, threshold=threshold))
    return _annual_mean_via_monthly(vi_coll_w_threshold, period_start, period_end)


def _process_sentinel2(
    aoi: ee.FeatureCollection,
    sensor: str,
    ee_asset_id: str,
    index: VegetationIndex,
    threshold: float | None,
    period_start: int,
    period_end: int,
) -> ee.ImageCollection:
    """Transcribed from integration.py:179-203."""
    threshold = require_float(threshold, "spec.threshold")
    i_img_coll = (
        ee.ImageCollection(ee_asset_id)
        .filterBounds(aoi)
        .filterDate(f"{period_start}-01-01", f"{period_end}-12-31")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
        .map(partial(_rename_bands, sensor=sensor))
        .map(partial(_cloud_mask, sensor=sensor))
        .map(partial(_apply_scale_factor, sensor=sensor))
    )

    vi_coll = i_img_coll.map(partial(_vi_expression, index=index)).select(index.value)
    vi_coll_w_threshold = vi_coll.map(partial(_apply_vi_threshold, threshold=threshold))
    return _annual_mean_via_monthly(vi_coll_w_threshold, period_start, period_end)


def _process_landsat_derived_vi(
    aoi: ee.FeatureCollection,
    asset_id: str,
    threshold: float | None,
    period_start: int,
    period_end: int,
) -> ee.ImageCollection:
    """Transcribed from integration.py:206-214."""
    threshold = require_float(threshold, "spec.threshold")
    img_coll = (
        ee.ImageCollection(asset_id)
        .filterBounds(aoi)
        .filterDate(f"{period_start}-01-01", f"{period_end}-12-31")
        .map(partial(_apply_vi_threshold, threshold=threshold))
    )
    return _annual_mean(img_coll, period_start, period_end)
