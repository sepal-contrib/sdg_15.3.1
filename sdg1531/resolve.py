"""ResolvedSpec: every derivation of a run, computed once.

Transcribed from the legacy `IndicatorModel` properties and the derivations the
science scripts kept inline (spec §6). This module is the JSON half: it must not
import ee.
"""

from __future__ import annotations

from dataclasses import dataclass

from sdg1531.catalog import LAND_COVER_FIRST_YEAR, LAND_COVER_MAX_YEAR, SENSORS
from sdg1531.errors import SpecError
from sdg1531.spec import Period, PrecomputedViAsset, RunSpec, SensorSelection

__all__ = ["ResolvedSpec", "resolve"]


def _clamp_cci(year: int) -> int:
    """indicator_model.py:156-168 (and the inline copy at soil_organic_carbon.py:12-14)."""
    return min(max(year, LAND_COVER_FIRST_YEAR), LAND_COVER_MAX_YEAR)


def _require_year(year: int | None, field: str) -> int:
    """Narrow an endpoint to ``int`` before it reaches a CCI clamp.

    Not a legacy transcription: the legacy would raise ``TypeError`` deep inside
    ``max()`` for the same missing-endpoint case. ``RunSpec`` itself never
    validates (``sdg1531.validate`` does, spec §4), so ``resolve()`` is the first
    place that can name what is actually missing.
    """
    if year is None:
        raise SpecError(f"{field} must be set before a run can be resolved")
    return year


def _selected_sensors(spec: RunSpec) -> tuple[str, ...]:
    source = spec.vi_source
    return source.names if isinstance(source, SensorSelection) else ()


def _integration_period(spec: RunSpec) -> Period:
    """integration.py:11-19, duplicated verbatim at :32-40.

    Reads the RAW overrides, not the resolved sub-periods, and never looks at the
    land-cover or SOC sub-periods.
    """
    p = spec.periods
    starts = (p.overall.start, p.trend.start, p.state.start, p.performance.start)
    ends = (p.overall.end, p.trend.end, p.state.end, p.performance.end)
    return Period(
        start=min(v for v in starts if v is not None),
        end=max(v for v in ends if v is not None),
    )


@dataclass(frozen=True, slots=True)
class ResolvedSpec:
    spec: RunSpec
    analysis_scale: int
    zonal_scale: int
    trend: Period
    state: Period
    performance: Period
    land_cover_period: Period
    soc_period: Period
    integration_period: Period
    lc_year_start_esa: int
    lc_year_end_esa: int
    soc_year_start: int
    soc_year_end_esa: int


def resolve(spec: RunSpec) -> ResolvedSpec:
    p = spec.periods
    base = p.overall

    trend = p.trend.resolve(base)  # indicator_model.py:81-94
    state = p.state.resolve(base)  # :96-109
    performance = p.performance.resolve(base)  # :111-124
    land_cover_period = p.land_cover.resolve(base)  # :126-139
    soc_period = p.soc.resolve(base)  # :141-153

    sensors = _selected_sensors(spec)
    if isinstance(spec.vi_source, PrecomputedViAsset):
        analysis_scale = spec.vi_source.scale
    else:
        analysis_scale = SENSORS[sensors[0]].scale  # indicator_model.py:74-76

    # soil_organic_carbon.py:16 — the start year reaches calendarRange unclamped.
    soc_start = _require_year(soc_period.start, "soc.start")
    soc_year_start = _clamp_cci(soc_start) if spec.compatibility.clamp_soc_start_year else soc_start

    return ResolvedSpec(
        spec=spec,
        analysis_scale=analysis_scale,
        zonal_scale=100 if "Sentinel 2" in sensors else 300,  # run_15_3_1.py:324
        trend=trend,
        state=state,
        performance=performance,
        land_cover_period=land_cover_period,
        soc_period=soc_period,
        integration_period=_integration_period(spec),
        lc_year_start_esa=_clamp_cci(_require_year(land_cover_period.start, "land_cover.start")),
        lc_year_end_esa=_clamp_cci(_require_year(land_cover_period.end, "land_cover.end")),
        soc_year_start=soc_year_start,
        # soil_organic_carbon.py:12-14
        soc_year_end_esa=_clamp_cci(_require_year(soc_period.end, "soc.end")),
    )
