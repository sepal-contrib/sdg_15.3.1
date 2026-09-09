"""sdg1531.validate — the total validator (spec §4 "two total functions", §7)."""

from dataclasses import replace

from sdg1531.spec import (
    AssetAoi,
    Compatibility,
    Period,
    PeriodOverride,
    RunSpec,
    SensorSelection,
    SubPeriods,
)
from sdg1531.validate import Problem, validate

BASE = RunSpec().evolve(
    periods=SubPeriods(overall=Period(2000, 2015)),
    vi_source=SensorSelection(("MODIS MOD13Q1",)),
    aoi=AssetAoi("users/someone/aoi", "someone-aoi"),
)


def overall(**override) -> SubPeriods:
    """``BASE``'s sub-periods with a different base period, overrides untouched."""
    return replace(BASE.periods, overall=Period(**override))


def codes(spec: RunSpec) -> set[str]:
    return {problem.code for problem in validate(spec)}


def only(spec: RunSpec, code: str) -> Problem:
    matches = [problem for problem in validate(spec) if problem.code == code]
    assert len(matches) == 1, f"expected exactly one {code}, got {matches}"
    return matches[0]


def test_default_run_spec_yields_problems_rather_than_raising():
    problems = validate(RunSpec())
    assert isinstance(problems, tuple)
    assert all(isinstance(problem, Problem) for problem in problems)
    assert {"missing_aoi", "missing_sensors"} <= {p.code for p in problems}


def test_a_complete_base_spec_has_no_problems():
    assert validate(BASE) == ()


def test_start_not_before_end_is_fatal():
    problem = only(BASE.evolve(periods=overall(start=2015, end=2015)), "start_not_before_end")
    assert problem.field == "periods.overall.start"
    assert problem.fatal is True
    assert "start_not_before_end" not in codes(BASE)


def test_start_after_end_is_also_reported():
    assert "start_not_before_end" in codes(BASE.evolve(periods=overall(start=2016, end=2015)))


def test_half_filled_period_is_not_a_period_order_problem():
    assert "start_not_before_end" not in codes(BASE.evolve(periods=overall(start=2000, end=None)))
    assert "start_not_before_end" not in codes(BASE.evolve(periods=overall(start=None, end=None)))


def test_missing_sensors_is_fatal_and_anchored():
    problem = only(BASE.evolve(vi_source=SensorSelection(())), "missing_sensors")
    assert problem.field == "vi_source.names"
    assert problem.fatal is True


def test_missing_sensors_when_vi_source_is_unset():
    # RunSpec's actual default is `vi_source=None` (spec.py), not an empty
    # SensorSelection — the half-filled-form state must be caught too.
    problem = only(BASE.evolve(vi_source=None), "missing_sensors")
    assert problem.field == "vi_source.names"
    assert problem.fatal is True


def test_missing_aoi_is_fatal_and_anchored():
    problem = only(BASE.evolve(aoi=None), "missing_aoi")
    assert problem.field == "aoi"
    assert problem.fatal is True


def soc(**override) -> SubPeriods:
    return replace(BASE.periods, soc=PeriodOverride(**override))


def state(**override) -> SubPeriods:
    return replace(BASE.periods, state=PeriodOverride(**override))


def test_soc_start_before_cci_is_a_warning():
    # soil_organic_carbon.py:16 passes p_soc_t_start raw into calendarRange
    spec = BASE.evolve(periods=overall(start=1985, end=2015))
    problem = only(spec, "soc_start_before_cci")
    assert problem.field == "periods.soc.start"
    assert problem.fatal is False


def test_soc_start_before_cci_is_silent_when_the_start_is_clamped():
    spec = BASE.evolve(
        periods=overall(start=1985, end=2015),
        compatibility=Compatibility(clamp_soc_start_year=True),
    )
    assert "soc_start_before_cci" not in codes(spec)


def test_soc_start_inside_cci_is_silent():
    assert "soc_start_before_cci" not in codes(BASE)


def test_soc_period_collapses_is_fatal():
    # soil_organic_carbon.py:161 selects `lc_year_end - p_soc_t_start`, negative
    # once the SOC period lies entirely after the 2022 CCI ceiling.
    spec = BASE.evolve(periods=soc(start=2025, end=2030))
    problem = only(spec, "soc_period_collapses")
    assert problem.field == "periods.soc"
    assert problem.fatal is True


def test_soc_period_ending_at_the_cci_ceiling_does_not_collapse():
    spec = BASE.evolve(periods=soc(start=2022, end=2030))
    assert "soc_period_collapses" not in codes(spec)


def test_short_state_period_is_a_warning_not_an_error():
    # productivity.py:198-200 — rangeContains("year", start, end - 3) is empty
    # for any state period shorter than four years: an all-masked z-score.
    spec = BASE.evolve(periods=state(start=2013, end=2015))
    problem = only(spec, "state_period_too_short")
    assert problem.field == "periods.state"
    assert problem.fatal is False
    assert all(p.fatal is False for p in validate(spec))


def test_four_year_state_period_is_accepted():
    assert "state_period_too_short" not in codes(BASE.evolve(periods=state(start=2012, end=2015)))
