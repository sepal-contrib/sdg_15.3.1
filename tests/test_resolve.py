"""resolve.py — every derivation the legacy computed lazily, resolved once.

Transcribed behaviour lives in component/model/indicator_model.py:74-266, plus the
inline derivations at run_15_3_1.py:184-197,324, integration.py:11-94 and
soil_organic_carbon.py:12-16.
"""

from __future__ import annotations

import pytest

from sdg1531.resolve import resolve
from sdg1531.spec import Period, PeriodOverride, SubPeriods
from spec_factory import default_spec

SUB_PERIODS = ("trend", "state", "performance", "land_cover", "soc")
RESOLVED_FIELD = {
    "trend": "trend",
    "state": "state",
    "performance": "performance",
    "land_cover": "land_cover_period",
    "soc": "soc_period",
}


def _legacy_endpoint(override_value, base_value):
    """indicator_model.py:81-153 — `return X if X else Y`: truthiness, not `is not None`."""
    if override_value:
        return override_value
    return base_value


def _periods(sub_period, override, base=Period(start=2000, end=2020)):
    overrides = {name: PeriodOverride(None, None) for name in SUB_PERIODS}
    overrides[sub_period] = override
    return SubPeriods(overall=base, **overrides)


@pytest.mark.parametrize("sub_period", SUB_PERIODS)
@pytest.mark.parametrize(
    "start_set,end_set", [(False, False), (True, False), (False, True), (True, True)]
)
def test_sub_period_endpoints_fall_back_one_by_one(sub_period, start_set, end_set):
    base = Period(start=2000, end=2020)
    override = PeriodOverride(
        start=2005 if start_set else None, end=2015 if end_set else None
    )
    r = resolve(default_spec(periods=_periods(sub_period, override, base)))

    assert getattr(r, RESOLVED_FIELD[sub_period]) == Period(
        start=_legacy_endpoint(override.start, base.start),
        end=_legacy_endpoint(override.end, base.end),
    )
    for other in SUB_PERIODS:
        if other != sub_period:
            assert getattr(r, RESOLVED_FIELD[other]) == base


def test_zero_endpoint_falls_back_like_legacy_truthiness():
    # indicator_model.py:82-87 — `if self.trend_start:` treats 0 as unset.
    r = resolve(default_spec(periods=_periods("trend", PeriodOverride(0, 0))))
    assert r.trend == Period(start=2000, end=2020)
