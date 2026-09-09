"""Annual VI and climate integration.

Transcribed from ``component/scripts/integration.py``. Phase 1 is a
transcription, not a refactor: every node this module builds must match the
legacy graph node for node, so the ugly parts (``ee.Image().constant``, the
un-merged monthly path, the MSVI/EVI asset swap) are preserved and annotated
rather than corrected.

ResolvedSpec fields read here:
    integration_period, spec.vi_source, spec.vegetation_index, spec.threshold,
    spec.compatibility.derived_vi_msvi_uses_evi_asset

EXPECTED_DIVERGENCES note: the rungs that consume ``spec.threshold`` (MODIS,
Sentinel 2, the Landsat sensors, Derived VI Landsat) narrow it with
``require_float`` and raise ``SpecError`` if it is unset. That check has NO
legacy counterpart -- ``vi_threshold`` (integration.py:410-415) calls
``img.gt(threshold)`` unconditionally and would pass a Python ``None``
straight into the ``ee`` graph. Task 17's parity harness should expect this
module to raise where a legacy run with an unset threshold would instead
build a graph that fails differently (or not at all, client-side).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from functools import partial
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import ee

from sdg1531.catalog import ASSETS, SENSORS
from sdg1531.engine._typing import as_collection, as_element, require_float, require_int
from sdg1531.enums import VegetationIndex
from sdg1531.errors import SpecError
from sdg1531.spec import PrecomputedViAsset, SensorSelection

if TYPE_CHECKING:  # typing only -- no runtime dependency on resolve/context
    from sdg1531.engine.context import ExecutionContext
    from sdg1531.resolve import ResolvedSpec

__all__ = ["build_climate_collection", "build_vi_collection"]

# The ladder's membership sets, from integration.py:45, :81-83.
_MODIS_VI_SENSORS = ("MODIS MOD13Q1", "MODIS MYD13Q1")
# Also the membership list `cloud_mask` (integration.py:248) and
# `apply_scale_factor` (:292) test against -- the same three legacy call
# sites, one tuple. Changing it moves all three behaviours at once.
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


def build_vi_collection(r: ResolvedSpec, ctx: ExecutionContext) -> ee.ImageCollection:
    """Annual integrated vegetation index for the integration period.

    Transcribed from integration.py:31-95 (``integrate_vi``). The sensor
    dispatch is the ORDERED LADDER of :45-94, not a family lookup: mixed
    selections are reachable (sensor_select.py:82-84 matches on substrings), so
    the precedence between the branches is observable behaviour.
    """
    source = r.spec.vi_source

    if isinstance(source, PrecomputedViAsset):
        # integration.py:79-80's "GEE Asset" branch is dropped: it read a trait
        # that does not exist, and "GEE Asset" is not a key of pm.sensors so
        # :42 would KeyError first. The replacement arm is not wired yet.
        raise SpecError(
            "A precomputed VI asset is not supported in phase 1; select sensors instead."
        )
    if not isinstance(source, SensorSelection):
        raise SpecError(f"Unsupported VI source: {source!r}")

    period_start = require_int(r.integration_period.start, "integration_period.start")
    period_end = require_int(r.integration_period.end, "integration_period.end")
    sensor_names = tuple(source.names)
    index = r.spec.vegetation_index
    # Not narrowed here: Terra NPP never reads a threshold (integration.py:
    # 134-142 -- process_terra_npp takes no threshold argument), so narrowing
    # this early would raise on a Terra NPP spec the legacy ran successfully.
    # Each rung that actually consumes `threshold` narrows it itself, at the
    # point of consumption.
    threshold = r.spec.threshold

    # transcribed from integration.py:41-43
    ee_asset_list: list[Any] = [SENSORS[name].collection_id for name in sensor_names]

    if set(_MODIS_VI_SENSORS) & set(sensor_names):  # integration.py:45
        return _process_modis(
            sensor_names, ee_asset_list, index, threshold, period_start, period_end
        )

    if "Terra NPP" in sensor_names:  # integration.py:54
        return _process_terra_npp(ee_asset_list, period_start, period_end)

    if "Sentinel 2" in sensor_names:  # integration.py:56
        # :59 passes sensors[0], not "Sentinel 2"; preserved.
        return _process_sentinel2(
            ctx.feature_collection,
            sensor_names[0],
            ee_asset_list[0],
            index,
            threshold,
            period_start,
            period_end,
        )

    if "Derived VI Landsat" in sensor_names:  # integration.py:66
        assets = ee_asset_list[0]
        if index is VegetationIndex.NDVI:
            asset_id = assets[0]
        elif index is VegetationIndex.EVI:
            asset_id = assets[1]
        elif r.spec.compatibility.derived_vi_msvi_uses_evi_asset:
            # Preserved defect, spec 7: integration.py:67-71 is
            # `assets[0] if vi == "ndvi" else assets[1]`, so MSVI reads the EVI
            # composite. Flag off turns it into an error instead.
            asset_id = assets[1]
        else:
            raise SpecError(
                "Derived VI Landsat publishes no MSVI composite; the legacy "
                "served the EVI asset instead. Enable "
                "Compatibility.derived_vi_msvi_uses_evi_asset to reproduce it."
            )
        return _process_landsat_derived_vi(
            ctx.feature_collection, asset_id, threshold, period_start, period_end
        )

    if set(_LANDSAT_SR_SENSORS) & set(sensor_names):  # integration.py:81
        return _process_landsat_sensors(
            ctx.feature_collection,
            sensor_names,
            ee_asset_list,
            index,
            threshold,
            period_start,
            period_end,
        )

    raise SpecError("No valid sensor type found in the selection.")


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
