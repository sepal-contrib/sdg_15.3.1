"""Productivity sub-indicators: trajectory, performance, state and the collapse.

Transcribed from ``component/scripts/productivity.py``. Phase 1 is a
transcription, not a refactor: every node must match the legacy graph. The
known weaknesses are preserved and annotated -- restrend still fits one
un-segmented per-pixel linear model over the whole trend period
(productivity.py:477-480), and build_performance still reduces with
``bestEffort=True`` (productivity.py:141-145), which silently coarsens the
scale on large AOIs.

The sharpest preserved weakness is the year filter that ``_vi_trend``,
``_restrend``, ``_rain_use_efficiency_trend`` and ``build_performance`` all
share: ``ee.Filter.gte("year", start).And(ee.Filter.lte("year", end))``.
``ee.Filter.And`` is a STATICMETHOD (ee/filter.py), so the receiver is silently
discarded and the expression encodes as ``Filter.and([lte(end)])`` -- **the
start bound never reaches the graph**, and each of these four periods is open
at its lower end. The legacy spells it exactly this way (productivity.py:
430-432, :465-470, :532-537, :119-123), so a transcription must reproduce it;
``test_year_filters_silently_drop_their_lower_bound`` pins it so that a later
"fix" to ``ee.Filter.And(gte, lte)`` -- which WOULD change the graph and break
parity -- cannot land silently.

A phase-2 fix must repair TWO stacked errors, not one. The collection those
filters run against starts at the ENVELOPE of all four periods
(``resolve.py``'s ``_integration_period``, from integration.py:11-19,
duplicated verbatim at :32-40), so a discarded lower bound makes the series
``[envelope_start, end]``.
All three trend methods then reduce that series with
``ee.Reducer.kendallsCorrelation()`` and scale the tau by ``z_coefficient(n)``
with ``n = end - start + 1`` computed from the DECLARED start (see the ``n =``
line in each of ``_vi_trend``, ``_restrend`` and ``_rain_use_efficiency_trend``
-- named rather than cited by line, because a line number into THIS file goes
stale the next time anything above it moves, which is how the citation this
sentence replaces was born). So the series covers the wrong span AND the
significance normalisation does not match the span it covers -- two errors in
one expression, feeding the +-1.96 / +-1.28 ladders directly. Repairing only
the filter leaves ``n`` correct by accident, and only when the trend window
happens to start at the envelope start. Both belong in the same phase-2 change,
with its own golden-graph update, not here.

ResolvedSpec fields read here:
    spec.trajectory, spec.lceu, trend, state, performance,
    lc_year_start_esa, analysis_scale, productivity_table

EXPECTED_DIVERGENCES note -- four raises in this module have NO legacy
counterpart, and the parity harness must carry all four:

1. Every Period bound consumed here (``trend``, ``state``, ``performance``) is
   narrowed with ``require_int`` (engine/_typing.py), which raises
   ``SpecError`` if it is unset. The legacy does ``model.p_state_end - 2``
   (productivity.py:196-199) and hands ``model.p_performance_start`` straight
   to ``ee.Filter.gte`` (:120-122), so an unset bound raises TypeError there
   and would build a broken graph here.
2. An unknown ``Lceu`` raises ``SpecError`` in ``build_lc_ecological_units``;
   productivity.py:92-116 falls through and raises ``UnboundLocalError``.
3. An unknown ``Trajectory`` raises ``SpecError`` in ``build_trajectory``;
   productivity.py:30-51 falls through and leaves ``z_score`` unbound.
4. ``_s_res_trend_unavailable`` raises ``SpecError`` where productivity.py:
   41-43 raises a bare ``NameError``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import partial
from types import MappingProxyType
from typing import TYPE_CHECKING

import ee

from sdg1531.catalog import ASSETS, z_coefficient
from sdg1531.engine._typing import as_collection, as_element, as_image, require_int
from sdg1531.engine.apply import apply_truth_table
from sdg1531.enums import Lceu, Trajectory
from sdg1531.errors import SpecError
from sdg1531.tables import ESA_LC_CLASSES, RECLASSIFICATION_MATRIX

if TYPE_CHECKING:  # typing only -- no runtime dependency on resolve/context
    from sdg1531.engine.context import ExecutionContext
    from sdg1531.resolve import ResolvedSpec

__all__ = [
    "build_lc_ecological_units",
    "build_performance",
    "build_productivity",
    "build_state",
    "build_trajectory",
]


def _lceu_static(asset_key: str) -> Callable[[ResolvedSpec], ee.Image]:
    """The four fixed LCEU rungs: one asset each, chosen by `spec.lceu` alone.

    `build` takes the run and reads nothing off it, which is correct rather than an
    oversight -- these assets do not depend on the run -- and its signature has to
    match `_lceu_calculate`, the fifth rung, which does.
    """

    def build(_: ResolvedSpec) -> ee.Image:
        return as_image(ee.Image(ASSETS[asset_key]))

    return build


def _lceu_calculate(r: ResolvedSpec) -> ee.Image:
    """Transcribed from productivity.py:98-114."""
    landcover = ee.ImageCollection(ASSETS["land_cover_ic"])

    soil_taxonomy = ee.Image(ASSETS["soil_taxonomy"]).select("b0")

    # reclassify lc to ipcc classes
    lc_reclass = (
        landcover.filter(ee.Filter.calendarRange(r.lc_year_start_esa, r.lc_year_start_esa, "year"))
        .first()
        .remap(list(ESA_LC_CLASSES), list(RECLASSIFICATION_MATRIX))
    )

    return as_image(soil_taxonomy.multiply(100).add(lc_reclass))


# productivity.py:92-116 as an exhaustive table; spec 7 replaces the
# fall-through-to-unbound-local with a raising default in build_*.
_LCEU_BUILDERS: Mapping[Lceu, Callable[[ResolvedSpec], ee.Image]] = MappingProxyType(
    {
        Lceu.GAES: _lceu_static("gaes"),
        Lceu.AEZ: _lceu_static("aez"),
        Lceu.HRU: _lceu_static("hru"),
        Lceu.WTE: _lceu_static("wte"),
        Lceu.CALCULATE: _lceu_calculate,
    }
)


def build_lc_ecological_units(r: ResolvedSpec) -> ee.Image:
    """The land-cover ecological unit raster. productivity.py:91-116."""
    try:
        builder = _LCEU_BUILDERS[r.spec.lceu]
    except KeyError:
        raise SpecError(f"Unsupported land cover ecological unit: {r.spec.lceu}") from None
    return builder(r)


def _ndvi_climate_merge(
    climate_yearly_integration: ee.ImageCollection,
    ndvi_yearly_integration: ee.ImageCollection,
    start: int | None = None,
    end: int | None = None,
) -> ee.ImageCollection:
    """Transcribed from productivity.py:560-583.

    `start` and `end` are DEAD parameters, accepted and ignored exactly as in
    the legacy: :473 passes them, :540 does not, and both call sites produce
    the same graph. They are kept so the asymmetry between the two callers
    stays visible against the legacy source.
    """
    join_filter = ee.Filter.equals(leftField="year", rightField="year")

    join = ee.Join.inner("clim", "vi", "year")

    inner_join = join.apply(
        climate_yearly_integration.select("clim"),
        ndvi_yearly_integration.select("vi"),
        join_filter,
    )

    joined = inner_join.map(
        lambda feature: ee.Image.cat(feature.get("clim"), feature.get("vi")).set(
            "year", ee.Image(feature.get("clim")).get("year")
        )  # both have the same year
    )

    return as_collection(ee.ImageCollection(joined))


def _ndvi_residuals(image: ee.Image, modeled: ee.ImageCollection) -> ee.Image:
    """Transcribed from productivity.py:586-603.

    The subtraction is observed - predicted, which is what the legacy code
    does. productivity.py:451's prose says "(Predicted - Obsedved)" and is
    wrong about its own function; do not flip it to match.
    """
    year = image.get("year")

    ndvi_o = image.select("vi")

    ndvi_p = modeled.filter(ee.Filter.eq("year", year)).first()

    ndvi_r = (
        ee.Image.constant(year).float().addBands(ndvi_o.subtract(ndvi_p)).rename(["year", "vi_res"])
    )

    return as_image(ndvi_r)


def _use_efficiency_ratio(image: ee.Image) -> ee.Element:
    """Transcribed from productivity.py:606-620."""
    ndvi_img = image.select("vi")
    clim_img = image.select("clim").divide(1000)
    year = image.get("year")
    divide_img = (
        ndvi_img.divide(clim_img)
        .addBands(ee.Image.constant(year).float())
        .rename(["ue", "year"])
        .set({"year": year})
    )

    return as_element(divide_img)


def _vi_trend(start: int, end: int, integrated_annual_vi: ee.ImageCollection) -> ee.Image:
    """Transcribed from productivity.py:422-444."""
    integrated_annual_vi_fltr = integrated_annual_vi.filter(
        ee.Filter.gte("year", start).And(ee.Filter.lte("year", end))
    )

    # Compute Kendall statistics
    n = end - start + 1
    coefficient = z_coefficient(n)
    kendall_trend = (
        integrated_annual_vi_fltr.select("vi")
        .reduce(ee.Reducer.kendallsCorrelation(), 2)
        .select("vi_tau")
        .multiply(coefficient)
    )

    return as_image(kendall_trend)


def _restrend(
    start: int,
    end: int,
    ndvi_yearly_integration: ee.ImageCollection,
    climate_yearly_integration: ee.ImageCollection,
) -> ee.Image:
    """Transcribed from productivity.py:447-521."""
    ndvi_yearly_integration_fltr = ndvi_yearly_integration.filter(
        ee.Filter.gte("year", start).And(ee.Filter.lte("year", end))
    )
    climate_yearly_integration_fltr = climate_yearly_integration.filter(
        ee.Filter.gte("year", start).And(ee.Filter.lte("year", end))
    )

    ndvi_climate_yearly_integration = _ndvi_climate_merge(
        climate_yearly_integration_fltr, ndvi_yearly_integration_fltr, start, end
    )

    # One un-segmented per-pixel linear model over the whole period; preserved.
    linear_model_climate_ndvi = ndvi_climate_yearly_integration.select(["clim", "vi"]).reduce(
        ee.Reducer.linearFit()
    )

    def ndvi_prediction_climate(image: ee.Image, accumulator: ee.List) -> ee.List:
        """predict NDVI from climate. part of p_restrend function"""
        ndvi = (
            linear_model_climate_ndvi.select("offset")
            .add(linear_model_climate_ndvi.select("scale").multiply(image.select("clim")))
            .set({"year": image.get("year")})
        )

        return ee.List(accumulator).add(ndvi)

    first = ee.List([])
    predicted_yearly_ndvi = ee.ImageCollection(
        ee.List(
            ndvi_climate_yearly_integration.select("clim").iterate(ndvi_prediction_climate, first)
        )
    )

    residual_yearly_ndvi = ndvi_yearly_integration_fltr.map(
        partial(_ndvi_residuals, modeled=predicted_yearly_ndvi)
    )

    # Compute Kendall statistics
    n = end - start + 1
    coefficient = z_coefficient(n)
    kendall_trend = (
        residual_yearly_ndvi.select("vi_res")
        .reduce(ee.Reducer.kendallsCorrelation(), 2)
        .select("vi_res_tau")
        .multiply(coefficient)
    )

    return as_image(kendall_trend)


def _rain_use_efficiency_trend(
    start: int,
    end: int,
    ndvi_yearly_integration: ee.ImageCollection,
    climate_yearly_integration: ee.ImageCollection,
) -> ee.Image:
    """Transcribed from productivity.py:524-557."""
    ndvi_yearly_integration_fltr = ndvi_yearly_integration.filter(
        ee.Filter.gte("year", start).And(ee.Filter.lte("year", end))
    )
    climate_yearly_integration_fltr = climate_yearly_integration.filter(
        ee.Filter.gte("year", start).And(ee.Filter.lte("year", end))
    )

    # :540-542 calls the merge WITHOUT start/end; preserved.
    ndvi_climate_yearly_integration = _ndvi_climate_merge(
        climate_yearly_integration_fltr, ndvi_yearly_integration_fltr
    )

    ue_yearly_collection = ndvi_climate_yearly_integration.map(_use_efficiency_ratio)

    # Compute Kendall statistics
    n = end - start + 1
    coefficient = z_coefficient(n)
    kendall_trend = (
        ue_yearly_collection.select("ue")
        .reduce(ee.Reducer.kendallsCorrelation(), 2)
        .select("ue_tau")
        .multiply(coefficient)
    )

    return as_image(kendall_trend)


def _s_res_trend_unavailable(
    start: int, end: int, vi: ee.ImageCollection, climate: ee.ImageCollection
) -> ee.Image:
    """productivity.py:41-43 -- water use efficiency, never implemented.

    parameter/ui.py:35 marks it `disabled: True` and validate() rejects it, so
    this exists only to keep _TRAJECTORY_BUILDERS exhaustive over Trajectory.
    """
    raise SpecError("The water use efficiency trajectory (s_res_trend) is not implemented.")


# productivity.py:26-51 as an exhaustive table. The legacy indexes
# pm.trajectories positionally: [0] ndvi_trend, [1] p_res_trend,
# [2] s_res_trend, [3] ue_trend. Note the names do NOT match the display
# labels: index 2 (s_res_trend) is labelled "Water use efficiency" and is the
# one that raises, index 3 (ue_trend) is "Rain use efficiency" and computes.
_TRAJECTORY_BUILDERS: Mapping[
    Trajectory, Callable[[int, int, ee.ImageCollection, ee.ImageCollection], ee.Image]
] = MappingProxyType(
    {
        Trajectory.NDVI_TREND: lambda start, end, vi, climate: _vi_trend(start, end, vi),
        Trajectory.P_RES_TREND: lambda start, end, vi, climate: _restrend(start, end, vi, climate),
        Trajectory.S_RES_TREND: _s_res_trend_unavailable,
        Trajectory.UE_TREND: lambda start, end, vi, climate: _rain_use_efficiency_trend(
            start, end, vi, climate
        ),
    }
)


def build_trajectory(
    r: ResolvedSpec, vi: ee.ImageCollection, climate: ee.ImageCollection
) -> ee.Image:
    """Productivity trend, reclassified into 5 and 3 levels.

    Transcribed from productivity.py:9-74 (``productivity_trajectory``).
    Reads r.spec.trajectory and r.trend.
    """
    try:
        builder = _TRAJECTORY_BUILDERS[r.spec.trajectory]
    except KeyError:
        raise SpecError(f"Unsupported trajectory method: {r.spec.trajectory}") from None

    trend_start = require_int(r.trend.start, "trend.start")
    trend_end = require_int(r.trend.end, "trend.end")

    z_score = builder(trend_start, trend_end, vi, climate)

    # Define Kendall parameter values for a significance of 0.05
    five_levels_trajectory = (
        ee.Image(0)
        .where(z_score.lt(-1.96), 1)
        .where(z_score.lt(-1.28).And(z_score.gte(-1.96)), 2)
        .where(z_score.gte(-1.28).And(z_score.lte(1.28)), 3)
        .where(z_score.gt(1.28).And(z_score.lte(1.96)), 4)
        .where(z_score.gt(1.96), 5)
        .rename("trajectory_5_levels")
        .uint8()
    )

    trajectory = (
        ee.Image(0)
        .where(z_score.lt(-1.96), 1)
        .where(z_score.gte(-1.96).And(z_score.lte(1.96)), 2)
        .where(z_score.gt(1.96), 3)
        .rename("trajectory")
        .uint8()
    )

    return as_image(five_levels_trajectory.addBands(trajectory))


def build_performance(r: ResolvedSpec, ctx: ExecutionContext, vi: ee.ImageCollection) -> ee.Image:
    """Local productivity relative to similar ecological units.

    Transcribed from productivity.py:77-174 (``productivity_performance``).
    The legacy also took ``climate_yearly_integration`` and never used it; that
    parameter is dropped. Reads r.spec.lceu, r.performance, r.analysis_scale.
    """
    performance_start = require_int(r.performance.start, "performance.start")
    performance_end = require_int(r.performance.end, "performance.end")

    lc_eco_functional_unit = build_lc_ecological_units(r)

    # compute mean ndvi for the period
    nvdi_yearly_integration_fltr = vi.filter(
        ee.Filter.gte("year", performance_start).And(ee.Filter.lte("year", performance_end))
    )
    ndvi_mean = nvdi_yearly_integration_fltr.select("vi").reduce(ee.Reducer.mean()).rename(["vi"])

    # fill the gaps in lceu with a negative value to prevent masking. NOT
    # unmask(-1): where() treats 0 as false, so a genuine 0 becomes -1 too.
    lc_eco_functional_unit_filled = ee.Image(-1).where(
        lc_eco_functional_unit, lc_eco_functional_unit
    )

    # create a 2 band raster to compute 90th percentile per ecoregion
    ndvi_id = ndvi_mean.addBands(lc_eco_functional_unit_filled)

    # compute 90th percentile by unit. `ctx` supplies the geometry only: the
    # scale is read off the ResolvedSpec because the legacy reads model.scale
    # (productivity.py:144), and a transcription keeps it there. ExecutionContext
    # carries its own analysis_scale that nothing in sdg1531/ reads -- deliberately
    # not used here, so Tasks 12-17 do not each re-decide which copy is
    # authoritative.
    percentile_90 = ndvi_id.reduceRegion(
        reducer=ee.Reducer.percentile([90]).group(groupField=1, groupName="code"),
        geometry=ctx.geometry,
        scale=r.analysis_scale,
        bestEffort=True,
        maxPixels=1e15,
    )

    # Extract the cluster IDs and the 90th percentile -- server-side throughout
    groups = ee.List(percentile_90.get("groups"))
    ids = groups.map(lambda d: ee.Dictionary(d).get("code"))
    percentile = groups.map(lambda d: ee.Dictionary(d).get("p90"))

    # remap the similar ecoregion raster using their 90th percentile value
    ecoregion_90th_percentile = lc_eco_functional_unit_filled.remap(ids, percentile)
    # set a very small number to 0 valued pixels to prevent masking
    ecoregion_90th_percentile_v2 = ecoregion_90th_percentile.where(
        ecoregion_90th_percentile.eq(0), 0.001
    )

    # compute the ratio of observed ndvi to 90th for that class
    observed_ratio = ndvi_mean.divide(ecoregion_90th_percentile_v2)

    # create final degradation output layer (0 is background), 2 is not
    # degreaded, 1 is degraded. The two conditions OVERLAP at exactly 0.5 and
    # the later .where() wins, so a ratio of exactly 0.5 is degraded; the order
    # of these two lines is behaviour, not style.
    performance = (
        ee.Image(0)
        .where(observed_ratio.gte(0.5), 2)
        .where(observed_ratio.lte(0.5), 1)
        .rename("performance")
        .uint8()
    )

    return as_image(performance)


def build_state(r: ResolvedSpec, vi: ee.ImageCollection) -> ee.Image:
    """Recent productivity against the pixel's own baseline.

    Transcribed from productivity.py:177-249 (``productivity_state``); its
    unused ``aoi_model`` and ``output`` parameters are dropped. Reads r.state.
    Note :198-200's baseline window is [start, end - 3], so a state period
    shorter than four years yields an all-masked z-score; validate() reports
    that as a warning rather than rejecting it.
    """
    state_start = require_int(r.state.start, "state.start")
    state_end = require_int(r.state.end, "state.end")

    # Filter the annual data of three most recent years
    recent_yaers_filter = ee.Filter.rangeContains("year", state_end - 2, state_end)
    previous_year_filter = ee.Filter.rangeContains("year", state_start, state_end - 3)

    # compute mean ndvi for the baseline and target period period
    recent_vi_xbar = (
        vi.filter(recent_yaers_filter).select("vi").reduce(ee.Reducer.mean()).rename(["vi"])
    )

    previous_vi_mu = (
        vi.filter(previous_year_filter).select("vi").reduce(ee.Reducer.mean()).rename(["vi"])
    )

    previous_vi_sigma = (
        vi.filter(previous_year_filter).select("vi").reduce(ee.Reducer.stdDev()).rename(["vi"])
    )
    # sqrt(3) is hardcoded rather than derived from the recent-year count; it
    # is right only because that window happens to be three years wide.
    z_score = recent_vi_xbar.subtract(previous_vi_mu).divide(
        previous_vi_sigma.divide(ee.Number(3).sqrt())
    )

    five_levels_state = (
        ee.Image(0)
        .where(z_score.lt(-1.96), 1)
        .where(z_score.lt(-1.28).And(z_score.gte(-1.96)), 2)
        .where(z_score.gte(-1.28).And(z_score.lte(1.28)), 3)
        .where(z_score.gt(1.28).And(z_score.lte(1.96)), 4)
        .where(z_score.gt(1.96), 5)
        .rename("state_5_levels")
        .uint8()
    )

    state = (
        ee.Image(0)
        .where(z_score.lt(-1.96), 1)
        .where(z_score.gte(-1.96).And(z_score.lte(1.96)), 2)
        .where(z_score.gt(1.96), 3)
        .rename("state")
        .uint8()
    )

    return as_image(five_levels_state.addBands(state))


def build_productivity(
    r: ResolvedSpec,
    *,
    trajectory: ee.Image,
    state: ee.Image,
    performance: ee.Image,
) -> ee.Image:
    """Collapse trajectory, state and performance into the productivity class.

    Transcribed from productivity.py:252-334 (``productivity_final``, GPGv2)
    and :337-419 (``productivity_final_GPG1``): the two 18-rule ``.where()``
    chains are now one ordered TruthTable, chosen in resolve() and emitted by
    apply_truth_table, so the node order -- and therefore the encoded graph --
    is unchanged. Reads r.productivity_table.

    apply_truth_table neither selects nor casts. The three single-band inputs
    are selected here, in rule-input order (trajectory, state, performance),
    exactly as productivity.py:253-255 does once and reuses, and the uint8 cast
    of :334 is applied to the result.

    The three images are KEYWORD-ONLY on purpose. That order is the order the
    rule conditions AND them in (:259), but the legacy signature and its only
    call site are both (trajectory, PERFORMANCE, STATE) -- productivity.py:252
    and run_15_3_1.py:185-190 -- so the two middle arguments are inverted with
    respect to the code this is transcribed from. `ee` is lazy, so a positional
    swap would build a clean graph and only misclassify at evaluation time.
    """
    return as_image(
        apply_truth_table(
            (
                trajectory.select("trajectory"),
                state.select("state"),
                performance.select("performance"),
            ),
            r.productivity_table,
            "productivity",  # productivity.py:331
        ).uint8()  # productivity.py:334
    )
