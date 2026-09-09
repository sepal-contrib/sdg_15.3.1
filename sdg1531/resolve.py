"""ResolvedSpec: every derivation of a run, computed once.

Transcribed from the legacy `IndicatorModel` properties and the derivations the
science scripts kept inline (spec §6). This module is the JSON half: it must not
import ee.
"""

from __future__ import annotations

from dataclasses import dataclass

from sdg1531.spec import Period, RunSpec

__all__ = ["ResolvedSpec", "resolve"]


@dataclass(frozen=True, slots=True)
class ResolvedSpec:
    spec: RunSpec
    trend: Period
    state: Period
    performance: Period
    land_cover_period: Period
    soc_period: Period


def resolve(spec: RunSpec) -> ResolvedSpec:
    p = spec.periods
    base = p.overall
    return ResolvedSpec(
        spec=spec,
        trend=p.trend.resolve(base),  # indicator_model.py:81-94
        state=p.state.resolve(base),  # :96-109
        performance=p.performance.resolve(base),  # :111-124
        land_cover_period=p.land_cover.resolve(base),  # :126-139
        soc_period=p.soc.resolve(base),  # :141-153
    )
