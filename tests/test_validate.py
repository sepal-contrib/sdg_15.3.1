"""sdg1531.validate — the total validator (spec §4 "two total functions", §7)."""

from dataclasses import replace

from _subprocess import run_python
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from sdg1531.enums import Trajectory
from sdg1531.scheme import LandCoverScheme, TransitionMatrix
from sdg1531.spec import (
    AssetAoi,
    Compatibility,
    CustomLandCoverSource,
    EsaCciSource,
    Period,
    PeriodOverride,
    PrecomputedViAsset,
    RunSpec,
    SensorSelection,
    SubPeriods,
)
from sdg1531.validate import Problem, check_custom_lc_codes, validate

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


def scheme(matrix: TransitionMatrix | None = None) -> LandCoverScheme:
    # Stands in for a parsed CSV, so is_custom is True. It is a stored field, not
    # something resolve() re-derives from the source arm, so it is set here.
    return LandCoverScheme(
        start_names=("Forest", "Cropland"),
        start_codes=(10, 30),
        end_names=("Forest", "Cropland"),
        end_codes=(10, 30),
        matrix=matrix if matrix is not None else TransitionMatrix(((0, -1), (1, 0))),
        is_custom=True,
    )


def test_precomputed_vi_is_rejected():
    spec = BASE.evolve(vi_source=PrecomputedViAsset("users/someone/vi", 30))
    problem = only(spec, "unsupported_vi_source")
    assert problem.field == "vi_source"
    assert problem.fatal is True
    assert "missing_sensors" not in codes(spec)


def test_s_res_trend_is_rejected():
    problem = only(BASE.evolve(trajectory=Trajectory.S_RES_TREND), "unsupported_trajectory")
    assert problem.field == "trajectory"
    assert problem.fatal is True


def test_every_other_trajectory_is_accepted():
    for trajectory in Trajectory:
        if trajectory is Trajectory.S_RES_TREND:
            continue
        assert "unsupported_trajectory" not in codes(BASE.evolve(trajectory=trajectory))


def test_half_custom_land_cover_is_a_warning():
    # land_cover.py:40 takes the custom branch on the two assets alone, while
    # indicator_model.py:232 needs the CSV before it uses the custom vocabulary.
    spec = BASE.evolve(
        land_cover=CustomLandCoverSource(
            start_asset="users/someone/start", end_asset="users/someone/end"
        )
    )
    problem = only(spec, "half_custom_land_cover")
    assert problem.field == "land_cover.scheme"
    assert problem.fatal is False


def test_fully_custom_land_cover_is_silent():
    spec = BASE.evolve(
        land_cover=CustomLandCoverSource(
            start_asset="users/someone/start",
            end_asset="users/someone/end",
            scheme=scheme(),
        )
    )
    assert validate(spec) == ()


def test_missing_custom_land_cover_assets_are_reported_per_field():
    # both asset fields are required, so an unselected asset is the empty string
    # a half-filled form carries, not a missing constructor argument.
    spec = BASE.evolve(
        land_cover=CustomLandCoverSource(start_asset="", end_asset="users/someone/end")
    )
    problem = only(spec, "missing_custom_land_cover_asset")
    assert problem.field == "land_cover.start_asset"
    assert problem.fatal is True

    both = BASE.evolve(land_cover=CustomLandCoverSource(start_asset="", end_asset=""))
    fields = [p.field for p in validate(both) if p.code == "missing_custom_land_cover_asset"]
    assert fields == ["land_cover.start_asset", "land_cover.end_asset"]


# Two of the three legal values, and one foreign value, both built off the real
# 7x7 default matrix (49 cells) rather than a toy 2x2 — the top-level
# `transition_matrix` field has no vocabulary of its own, it is only ever meant
# to pair with the built-in 7-class IPCC scheme, so a differently-shaped matrix
# would trip the *shape* rule below and make these value-range tests ambiguous.
TWO_VALUED_DEFAULT = TransitionMatrix(
    tuple(tuple(0 if v == 1 else v for v in row) for row in TransitionMatrix.default().rows)
)
FOREIGN_VALUE_DEFAULT = TransitionMatrix.default().with_cell(0, 1, 2)


def test_two_valued_matrix_is_accepted():
    # input_tile.py:310 used set equality and rejected this matrix; validate()
    # uses a subset test instead.
    assert "invalid_transition_matrix" not in codes(
        BASE.evolve(transition_matrix=TWO_VALUED_DEFAULT)
    )


def test_matrix_with_a_foreign_value_is_fatal():
    problem = only(
        BASE.evolve(transition_matrix=FOREIGN_VALUE_DEFAULT), "invalid_transition_matrix"
    )
    assert problem.field == "transition_matrix"
    assert problem.fatal is True


def test_custom_scheme_matrix_is_checked_under_its_own_field():
    spec = BASE.evolve(
        land_cover=CustomLandCoverSource(
            start_asset="users/someone/start",
            end_asset="users/someone/end",
            scheme=scheme(TransitionMatrix(((0, 2), (-1, 0)))),
        )
    )
    problem = only(spec, "invalid_transition_matrix")
    assert problem.field == "land_cover.scheme.matrix"


def test_ragged_transition_matrix_is_fatal():
    # TransitionMatrix performs no shape validation on its own (Task 3); a
    # matrix whose flattened length doesn't match its scheme's code count feeds
    # land_cover.py's remap the wrong number of values — a GEE arity error at
    # runtime rather than one caught at construction.
    ragged = TransitionMatrix(((0, -1, 1), (-1, 0)))
    problem = only(BASE.evolve(transition_matrix=ragged), "invalid_transition_matrix")
    assert problem.field == "transition_matrix"
    assert problem.fatal is True


def test_undersized_custom_scheme_matrix_is_fatal():
    spec = BASE.evolve(
        land_cover=CustomLandCoverSource(
            start_asset="users/someone/start",
            end_asset="users/someone/end",
            scheme=scheme(TransitionMatrix(((0, -1),))),  # 1x2, the scheme needs 2x2
        )
    )
    problem = only(spec, "invalid_transition_matrix")
    assert problem.field == "land_cover.scheme.matrix"


def test_exact_check_accepts_an_identical_code_set():
    assert check_custom_lc_codes(scheme(), (30, 10), (10, 30), exact=True) == ()


def test_exact_check_rejects_a_strict_subset():
    # input_tile.py:267-278 — the lc_pixel_check=True branch demands equality.
    problems = check_custom_lc_codes(scheme(), (10,), (10, 30), exact=True)
    assert [p.code for p in problems] == ["custom_lc_codes_mismatch"]
    assert problems[0].field == "land_cover.start_asset"
    assert problems[0].fatal is True


def test_exact_check_reports_both_assets_independently():
    problems = check_custom_lc_codes(scheme(), (10,), (99,), exact=True)
    assert [p.field for p in problems] == [
        "land_cover.start_asset",
        "land_cover.end_asset",
    ]


def test_subset_check_accepts_a_strict_subset():
    # input_tile.py:282-298 — the lc_pixel_check=False branch demands a subset.
    assert check_custom_lc_codes(scheme(), (10,), (), exact=False) == ()


def test_subset_check_rejects_an_unknown_pixel_value():
    problems = check_custom_lc_codes(scheme(), (10, 30), (10, 99), exact=False)
    assert [p.code for p in problems] == ["custom_lc_codes_not_subset"]
    assert problems[0].field == "land_cover.end_asset"
    assert "99" in problems[0].message


SENSOR_NAMES = ["MODIS MOD13Q1", "Sentinel 2", "Landsat 8", "Derived VI Landsat"]

years = st.one_of(st.none(), st.integers(min_value=1900, max_value=2100))
base_periods = st.builds(Period, start=years, end=years)
overrides = st.builds(PeriodOverride, start=years, end=years)
sub_periods = st.builds(
    SubPeriods,
    overall=base_periods,
    trend=overrides,
    state=overrides,
    performance=overrides,
    land_cover=overrides,
    soc=overrides,
)
matrices = (
    st.lists(
        st.lists(st.integers(min_value=-3, max_value=3), min_size=1, max_size=3).map(tuple),
        min_size=1,
        max_size=3,
    )
    .map(tuple)
    .map(TransitionMatrix)
)
schemes = st.builds(
    LandCoverScheme,
    start_names=st.just(("Forest", "Cropland")),
    start_codes=st.just((10, 30)),
    end_names=st.just(("Forest", "Cropland")),
    end_codes=st.just((10, 30)),
    matrix=matrices,
    is_custom=st.booleans(),
)
vi_sources = st.one_of(
    st.none(),
    st.builds(
        SensorSelection,
        names=st.lists(st.sampled_from(SENSOR_NAMES), max_size=3).map(tuple),
    ),
    st.builds(
        PrecomputedViAsset,
        asset_id=st.text(max_size=8),
        scale=st.integers(min_value=1, max_value=300),
    ),
)
land_cover_sources = st.one_of(
    st.just(EsaCciSource()),
    st.builds(
        CustomLandCoverSource,
        # both asset fields are required strings; "" is the half-filled form
        start_asset=st.sampled_from(("", "users/someone/start")),
        end_asset=st.sampled_from(("", "users/someone/end")),
        scheme=st.one_of(st.none(), schemes),
    ),
)
run_specs = st.builds(
    RunSpec,
    periods=sub_periods,
    vi_source=vi_sources,
    trajectory=st.sampled_from(list(Trajectory)),
    transition_matrix=matrices,
    land_cover=land_cover_sources,
    aoi=st.one_of(
        st.none(),
        st.builds(
            AssetAoi,
            asset_id=st.just("users/someone/aoi"),
            name=st.just("someone-aoi"),
        ),
    ),
    compatibility=st.builds(Compatibility, clamp_soc_start_year=st.booleans()),
)


@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
@given(run_specs)
def test_validate_never_raises(spec):
    problems = validate(spec)
    assert isinstance(problems, tuple)
    assert all(isinstance(problem, Problem) for problem in problems)
    assert all(isinstance(problem.field, str) and problem.code for problem in problems)
    assert "internal_error" not in {problem.code for problem in problems}


def test_validate_does_not_import_ee():
    # The JSON half of the domain must stay importable without earthengine-api
    # (spec §4). Run in a subprocess: the session ee fixture in conftest.py has
    # already put `ee` in sys.modules for the in-process tests.
    proc = run_python("import sys, sdg1531.validate; assert 'ee' not in sys.modules")
    assert proc.returncode == 0, proc.stdout + proc.stderr
