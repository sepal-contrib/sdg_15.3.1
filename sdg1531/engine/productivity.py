"""Productivity sub-indicators: trajectory, performance, state and the collapse.

Transcribed from ``component/scripts/productivity.py``. Phase 1 is a
transcription, not a refactor: every node must match the legacy graph. The
known weaknesses are preserved and annotated -- restrend still fits one
un-segmented per-pixel linear model over the whole trend period
(productivity.py:477-480), and build_performance still reduces with
``bestEffort=True`` (productivity.py:141-145), which silently coarsens the
scale on large AOIs.

ResolvedSpec fields read here:
    spec.trajectory, spec.lceu, trend, state, performance,
    lc_year_start_esa, analysis_scale, productivity_table

EXPECTED_DIVERGENCES note: every Period bound this module consumes is narrowed
with ``_require_int`` first, which raises ``SpecError`` if it is unset. That
check has NO legacy counterpart -- productivity.py:196-199 does
``model.p_state_end - 2`` and :120-122 hands ``model.p_performance_start``
straight to ``ee.Filter.gte``, so an unset bound would raise a TypeError there
and build a broken graph here. It follows the precedent
``engine/integration.py`` set for ``integration_period``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import partial
from types import MappingProxyType
from typing import TYPE_CHECKING

import ee

from sdg1531.catalog import ASSETS, z_coefficient
from sdg1531.engine._typing import as_collection, as_element, as_image
from sdg1531.enums import Lceu, Trajectory
from sdg1531.errors import SpecError
from sdg1531.tables import ESA_LC_CLASSES, RECLASSIFICATION_MATRIX

if TYPE_CHECKING:  # typing only -- no runtime dependency on resolve/context
    from sdg1531.resolve import ResolvedSpec

__all__ = [
    "build_lc_ecological_units",
    "build_trajectory",
]


def _require_int(value: int | None, what: str) -> int:
    """Narrow a resolved Period bound before it is used as a number.

    `Period.start`/`.end` stay `int | None` for the half-filled form (spec.py);
    `resolve()` guarantees the three productivity periods have both set, but
    nothing in the type system says so. Mirrors `engine/integration.py`'s
    helper of the same name -- duplicated rather than shared, so neither engine
    module depends on the other's privates.
    """
    if value is None:
        raise SpecError(f"{what} must be resolved before the ee graph can be built")
    return value


def _lceu_static(asset_key: str) -> Callable[[ResolvedSpec], ee.Image]:
    def build(r: ResolvedSpec) -> ee.Image:
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

    trend_start = _require_int(r.trend.start, "trend.start")
    trend_end = _require_int(r.trend.end, "trend.end")

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
