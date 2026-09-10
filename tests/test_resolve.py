"""resolve.py — every derivation the legacy computed lazily, resolved once.

Transcribed behaviour lives in component/model/indicator_model.py:74-266, plus the
inline derivations at run_15_3_1.py:184-197,324, integration.py:11-94 and
soil_organic_carbon.py:12-16.
"""

from __future__ import annotations

import dataclasses
import json
import random
import re
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from spec_factory import default_spec

from sdg1531.enums import ProductivityLookup, VegetationIndex
from sdg1531.errors import SpecError
from sdg1531.palette import CSS4_HEX
from sdg1531.resolve import ResolvedSpec, ViProcessor, resolve
from sdg1531.scheme import LandCoverScheme, TransitionMatrix
from sdg1531.spec import (
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
from sdg1531.tables import (
    DEFAULT_LC_CLASS_NAMES,
    DEFAULT_LC_CODES,
    DEFAULT_LC_COLORS,
    IPCC_TRANSITION_CODES,
)
from sdg1531.truth_table import PRODUCTIVITY_GPGV1, PRODUCTIVITY_GPGV2

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


def _periods(sub_period, override, base: Period | None = None):
    base = base if base is not None else Period(start=2000, end=2020)
    overrides = {name: PeriodOverride(None, None) for name in SUB_PERIODS}
    overrides[sub_period] = override
    return SubPeriods(overall=base, **overrides)


@pytest.mark.parametrize("sub_period", SUB_PERIODS)
@pytest.mark.parametrize(
    "start_set,end_set", [(False, False), (True, False), (False, True), (True, True)]
)
def test_sub_period_endpoints_fall_back_one_by_one(sub_period, start_set, end_set):
    base = Period(start=2000, end=2020)
    override = PeriodOverride(start=2005 if start_set else None, end=2015 if end_set else None)
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


CCI_CLAMP_CASES = [
    (1980, 1992),
    (1991, 1992),
    (1992, 1992),
    (2000, 2000),
    (2022, 2022),
    (2023, 2022),
    (2030, 2022),
]


@pytest.mark.parametrize("year,expected", CCI_CLAMP_CASES)
def test_land_cover_years_are_clamped_to_the_cci_range(year, expected):
    # indicator_model.py:156-168
    r = resolve(default_spec(periods=_periods("land_cover", PeriodOverride(year, year))))
    assert r.land_cover_period == Period(start=year, end=year)
    assert r.lc_year_start_esa == expected
    assert r.lc_year_end_esa == expected


@pytest.mark.parametrize("year,expected", CCI_CLAMP_CASES)
def test_soc_start_is_raw_while_soc_end_is_clamped(year, expected):
    # soil_organic_carbon.py:12-16 — only the end year is clamped.
    r = resolve(default_spec(periods=_periods("soc", PeriodOverride(year, year))))
    assert r.soc_year_start == year
    assert r.soc_year_end_esa == expected


@pytest.mark.parametrize("year,expected", CCI_CLAMP_CASES)
def test_clamp_soc_start_year_flag_flips_the_asymmetry(year, expected):
    r = resolve(
        default_spec(
            periods=_periods("soc", PeriodOverride(year, year)),
            compatibility=Compatibility(clamp_soc_start_year=True),
        )
    )
    assert r.soc_year_start == expected
    assert r.soc_year_end_esa == expected


def test_analysis_scale_comes_from_the_first_selected_sensor():
    # indicator_model.py:74-76
    r = resolve(default_spec(vi_source=SensorSelection(("Landsat 8", "Landsat 9"))))
    assert r.analysis_scale == 30


def test_analysis_scale_is_the_first_sensor_not_the_last():
    # indicator_model.py:74-76 — sensors[0], observable only across scale families:
    # ("Landsat 8", "Landsat 9") alone can't tell sensors[0] from sensors[-1].
    r = resolve(default_spec(vi_source=SensorSelection(("Landsat 8", "MODIS MOD13Q1"))))
    assert r.analysis_scale == 30


def test_precomputed_vi_asset_carries_its_own_scale():
    r = resolve(default_spec(vi_source=PrecomputedViAsset(asset_id="users/x/vi", scale=125)))
    assert r.analysis_scale == 125
    assert r.zonal_scale == 300


def test_zonal_scale_differs_from_analysis_scale_for_sentinel_2():
    # run_15_3_1.py:324 — deliberately not the analysis scale.
    r = resolve(default_spec(vi_source=SensorSelection(("Sentinel 2",))))
    assert r.analysis_scale == 10
    assert r.zonal_scale == 100


@pytest.mark.parametrize(
    "sensor,analysis_scale",
    [("MODIS MOD13Q1", 250), ("Terra NPP", 250), ("Landsat 8", 30)],
)
def test_zonal_scale_is_300_without_sentinel_2(sensor, analysis_scale):
    r = resolve(default_spec(vi_source=SensorSelection((sensor,))))
    assert r.analysis_scale == analysis_scale
    assert r.zonal_scale == 300


def test_integration_period_excludes_land_cover_and_soc():
    # integration.py:11-19 and :32-40 — only overall/trend/state/performance.
    periods = SubPeriods(
        overall=Period(start=2005, end=2015),
        trend=PeriodOverride(2003, 2016),
        state=PeriodOverride(None, None),
        performance=PeriodOverride(2001, None),
        land_cover=PeriodOverride(1995, 2020),
        soc=PeriodOverride(1993, 2021),
    )
    r = resolve(default_spec(periods=periods))
    assert r.integration_period == Period(start=2001, end=2016)
    assert r.land_cover_period == Period(start=1995, end=2020)
    assert r.soc_period == Period(start=1993, end=2021)


def test_integration_period_reads_raw_overrides_not_resolved_periods():
    # integration.py:17-18 filters `is not None`, so a raw 0 enters the envelope
    # even though PeriodOverride.resolve() treats it as unset (truthiness, :81-153).
    # Raw and resolved diverge only at this falsy-but-not-None value.
    r = resolve(default_spec(periods=_periods("trend", PeriodOverride(0, None))))
    assert r.trend == Period(start=2000, end=2020)
    assert r.integration_period.start == 0


_YEAR = st.integers(min_value=1992, max_value=2030)
_OVERRIDE = st.tuples(st.none() | _YEAR, st.none() | _YEAR)


@given(
    overall_start=_YEAR,
    overall_end=_YEAR,
    trend=_OVERRIDE,
    state=_OVERRIDE,
    performance=_OVERRIDE,
    land_cover=_OVERRIDE,
    soc=_OVERRIDE,
)
def test_integration_period_is_the_minimal_envelope_of_four(
    overall_start, overall_end, trend, state, performance, land_cover, soc
):
    periods = SubPeriods(
        overall=Period(start=overall_start, end=overall_end),
        trend=PeriodOverride(*trend),
        state=PeriodOverride(*state),
        performance=PeriodOverride(*performance),
        land_cover=PeriodOverride(*land_cover),
        soc=PeriodOverride(*soc),
    )
    r = resolve(default_spec(periods=periods))
    covered = (Period(overall_start, overall_end), r.trend, r.state, r.performance)

    # contains all four
    assert all(r.integration_period.start <= q.start for q in covered)
    assert all(q.end <= r.integration_period.end for q in covered)
    # and is minimal
    assert r.integration_period.start == min(q.start for q in covered)
    assert r.integration_period.end == max(q.end for q in covered)


@given(land_cover=_OVERRIDE, soc=_OVERRIDE)
def test_land_cover_and_soc_never_move_the_integration_envelope(land_cover, soc):
    base = SubPeriods(
        overall=Period(start=2005, end=2015),
        trend=PeriodOverride(2004, 2016),
        state=PeriodOverride(None, None),
        performance=PeriodOverride(None, None),
        land_cover=PeriodOverride(None, None),
        soc=PeriodOverride(None, None),
    )
    widened = SubPeriods(
        overall=base.overall,
        trend=base.trend,
        state=base.state,
        performance=base.performance,
        land_cover=PeriodOverride(*land_cover),
        soc=PeriodOverride(*soc),
    )
    assert (
        resolve(default_spec(periods=widened)).integration_period
        == resolve(default_spec(periods=base)).integration_period
        == Period(start=2004, end=2016)
    )


MOD = "MODIS/061/MOD13Q1"
MYD = "MODIS/061/MYD13Q1"
NPP = "MODIS/006/MOD17A3HGF"
S2 = "COPERNICUS/S2_SR_HARMONIZED"
L4 = "LANDSAT/LT04/C02/T1_L2"
L5 = "LANDSAT/LT05/C02/T1_L2"
L7 = "LANDSAT/LE07/C02/T1_L2"
L8 = "LANDSAT/LC08/C02/T1_L2"
L9 = "LANDSAT/LC09/C02/T1_L2"
DVI_NDVI = "LANDSAT/COMPOSITES/C02/T1_L2_32DAY_NDVI"
DVI_EVI = "LANDSAT/COMPOSITES/C02/T1_L2_32DAY_EVI"

# Selections reachable through sensor_select.py:62-90, which resets v_model only
# when the sensor being ADDED shares no family substring with what is already there.
REACHABLE = [
    (("MODIS MOD13Q1",), ViProcessor.MODIS, (MOD,)),
    (("MODIS MYD13Q1",), ViProcessor.MODIS, (MYD,)),
    (("MODIS MOD13Q1", "MODIS MYD13Q1"), ViProcessor.MODIS, (MOD, MYD)),
    (("MODIS MYD13Q1", "MODIS MOD13Q1"), ViProcessor.MODIS, (MYD, MOD)),
    (("Terra NPP",), ViProcessor.TERRA_NPP, (NPP,)),
    (("Sentinel 2",), ViProcessor.SENTINEL2, (S2,)),
    (("Derived VI Landsat",), ViProcessor.DERIVED_VI_LANDSAT, (DVI_NDVI,)),
    (("Landsat 4",), ViProcessor.LANDSAT_SENSORS, (L4,)),
    (("Landsat 5",), ViProcessor.LANDSAT_SENSORS, (L5,)),
    (("Landsat 7",), ViProcessor.LANDSAT_SENSORS, (L7,)),
    (("Landsat 8",), ViProcessor.LANDSAT_SENSORS, (L8,)),
    (("Landsat 9",), ViProcessor.LANDSAT_SENSORS, (L9,)),
    (("Landsat 4", "Landsat 5", "Landsat 7"), ViProcessor.LANDSAT_SENSORS, (L4, L5, L7)),
    (("Landsat 8", "Landsat 9"), ViProcessor.LANDSAT_SENSORS, (L8, L9)),
    # The ladder's precedence, observable: adding "Derived VI Landsat" to a Landsat
    # selection is NOT blocked, the derived branch wins over the landsat branch, and
    # integration.py:66-71 then indexes the FIRST selected sensor's asset — a plain
    # string here — by character. Legacy behaviour, transcribed (spec §6).
    (("Landsat 8", "Derived VI Landsat"), ViProcessor.DERIVED_VI_LANDSAT, ("L",)),
    # Not reachable through the widget; pins that the branch reads sensors[0].
    (("Derived VI Landsat", "Landsat 8"), ViProcessor.DERIVED_VI_LANDSAT, (DVI_NDVI,)),
]


@pytest.mark.parametrize("names,processor,assets", REACHABLE)
def test_sensor_ladder(names, processor, assets):
    r = resolve(default_spec(vi_source=SensorSelection(names)))
    assert r.vi_processor is processor
    assert r.vi_assets == assets


@pytest.mark.parametrize(
    "names,processor",
    [
        (("Terra NPP", "Sentinel 2"), ViProcessor.TERRA_NPP),  # :54 before :56
        (("Sentinel 2", "Terra NPP"), ViProcessor.TERRA_NPP),  # order-independent
        (("Sentinel 2", "Landsat 8"), ViProcessor.SENTINEL2),  # :56 before :81
        (("MODIS MOD13Q1", "Sentinel 2"), ViProcessor.MODIS),  # :45 first
    ],
)
def test_ladder_rung_order(names, processor):
    # REACHABLE above is single-family except the derived-VI/Landsat pairs, so it
    # cannot tell an ordered ladder from a family lookup for rungs 1-3. These
    # selections are not all widget-reachable (sensor_select.py:62-90); that is
    # the point, matching the existing Derived-VI/Landsat precedent.
    assert resolve(default_spec(vi_source=SensorSelection(names))).vi_processor is processor


def test_precomputed_vi_asset_is_its_own_rung():
    r = resolve(default_spec(vi_source=PrecomputedViAsset(asset_id="users/x/vi", scale=30)))
    assert r.vi_processor is ViProcessor.PRECOMPUTED
    assert r.vi_assets == ("users/x/vi",)


@pytest.mark.parametrize(
    "index,asset",
    [
        (VegetationIndex.NDVI, DVI_NDVI),
        (VegetationIndex.EVI, DVI_EVI),
        (VegetationIndex.MSVI, DVI_EVI),
    ],
)
def test_derived_vi_asset_selection(index, asset):
    # integration.py:66-71 — everything that is not ndvi takes the EVI asset.
    r = resolve(
        default_spec(vi_source=SensorSelection(("Derived VI Landsat",)), vegetation_index=index)
    )
    assert r.vi_assets == (asset,)


def test_derived_vi_msvi_raises_when_the_compatibility_flag_is_off():
    spec = default_spec(
        vi_source=SensorSelection(("Derived VI Landsat",)),
        vegetation_index=VegetationIndex.MSVI,
        compatibility=Compatibility(derived_vi_msvi_uses_evi_asset=False),
    )
    with pytest.raises(SpecError):
        resolve(spec)


def test_derived_vi_evi_is_unaffected_by_the_msvi_flag():
    spec = default_spec(
        vi_source=SensorSelection(("Derived VI Landsat",)),
        vegetation_index=VegetationIndex.EVI,
        compatibility=Compatibility(derived_vi_msvi_uses_evi_asset=False),
    )
    assert resolve(spec).vi_assets == (DVI_EVI,)


def test_an_empty_sensor_selection_raises():
    with pytest.raises(SpecError):
        resolve(default_spec(vi_source=SensorSelection(())))


def test_unknown_sensor_name_raises_spec_error_not_keyerror():
    # An out-of-catalog name would otherwise escape SENSORS[key] as a bare KeyError.
    with pytest.raises(SpecError):
        resolve(default_spec(vi_source=SensorSelection(("Not A Sensor",))))


_NO_OVERRIDE = PeriodOverride(None, None)


@pytest.mark.parametrize(
    ("periods", "field"),
    [
        (_periods("trend", _NO_OVERRIDE, base=Period(None, 2020)), "soc.start"),
        # the end side needs a sub-period end so `_integration_period`'s max() has
        # something to reduce -- see the companion test below
        (
            _periods("trend", PeriodOverride(None, 2015), base=Period(2000, None)),
            "land_cover.end",
        ),
    ],
)
def test_a_missing_period_endpoint_is_named_rather_than_escaping_as_a_type_error(periods, field):
    """`_require_year` -- a divergence with no EXPECTED_DIVERGENCES note in
    `resolve.py`. The legacy reached the same missing endpoint inside
    `min(max(None, 1992), 2022)` (indicator_model.py:156-168) and raised an
    unannotated TypeError; resolve() names the field instead. Task 17's parity
    register carries it as `resolve_requires_a_year`."""
    with pytest.raises(SpecError, match=re.escape(field)):
        resolve(default_spec(periods=periods))


def test_an_all_none_end_side_still_escapes_as_a_bare_value_error():
    """`_require_year` is NOT reached when every end is unset: `_integration_period`
    reduces an empty sequence first and `max()` raises ValueError.

    That is legacy-faithful -- integration.py:19 is the same `max(filter(...))` over
    the same four values and raises the same ValueError -- so it is not a divergence
    and must not be "fixed" into a SpecError while parity is the rule. Pinned here so
    the `resolve_requires_a_year` entry above is not read as covering it."""
    with pytest.raises(ValueError, match="empty"):
        resolve(default_spec(periods=_periods("trend", _NO_OVERRIDE, base=Period(2000, None))))


CUSTOM_SCHEME = LandCoverScheme(
    start_names=("Forest", "Crops", "Water"),
    start_codes=(3, 1, 2),
    end_names=("Forest", "Crops", "Water"),
    end_codes=(3, 1, 2),
    matrix=TransitionMatrix(rows=((0, 1, -1), (1, 0, -1), (-1, -1, 0))),
    is_custom=True,
)


def test_default_land_cover_uses_the_default_vocabulary():
    r = resolve(default_spec(land_cover=EsaCciSource()))
    assert r.scheme.start_names == DEFAULT_LC_CLASS_NAMES
    assert r.scheme.end_names == DEFAULT_LC_CLASS_NAMES
    assert r.scheme.start_codes == DEFAULT_LC_CODES
    assert r.scheme.is_custom is False
    assert r.lc_class_combinations == IPCC_TRANSITION_CODES
    assert r.trans_matrix_flatten == TransitionMatrix.default().flatten()
    assert dict(r.lc_color_by_class) == dict(DEFAULT_LC_COLORS)
    assert r.lc_palette == tuple(DEFAULT_LC_COLORS.values())


def test_half_custom_uses_the_default_vocabulary():
    # land_cover.py:40 takes the custom-asset branch on the two assets alone, while
    # indicator_model.py:183-242 needs the CSV too. Precedence stated once here.
    r = resolve(
        default_spec(
            land_cover=CustomLandCoverSource(
                start_asset="users/x/lc_start", end_asset="users/x/lc_end", scheme=None
            )
        )
    )
    assert r.scheme.start_names == DEFAULT_LC_CLASS_NAMES
    assert r.scheme.is_custom is False
    assert r.lc_class_combinations == IPCC_TRANSITION_CODES
    assert r.trans_matrix_flatten == TransitionMatrix.default().flatten()
    assert dict(r.lc_color_by_class) == dict(DEFAULT_LC_COLORS)


def test_the_edited_default_matrix_reaches_trans_matrix_flatten():
    # indicator_model.py:231-242, else branch — the flatten of model.transition_matrix.
    edited = TransitionMatrix(rows=((0, 1), (-1, 0)))
    r = resolve(default_spec(transition_matrix=edited))
    assert r.trans_matrix_flatten == (0, 1, -1, 0)


def test_custom_scheme_drives_the_whole_vocabulary():
    r = resolve(
        default_spec(
            land_cover=CustomLandCoverSource(
                start_asset="users/x/lc_start",
                end_asset="users/x/lc_end",
                scheme=CUSTOM_SCHEME,
            ),
            transition_matrix=TransitionMatrix(rows=((0, 0), (0, 0))),
        )
    )
    assert r.scheme is CUSTOM_SCHEME
    # indicator_model.py:221-227 — int(str(start) + str(end)), start-major. Built by
    # LandCoverScheme.class_combinations (Task 3); resolve() only reads it through.
    assert r.lc_class_combinations == (33, 31, 32, 13, 11, 12, 23, 21, 22)
    assert r.lc_class_combinations == CUSTOM_SCHEME.class_combinations
    # :231-238 — the CSV matrix wins over model.transition_matrix.
    assert r.trans_matrix_flatten == (0, 1, -1, 1, 0, -1, -1, -1, 0)


def test_custom_scheme_colours_are_sampled_by_code_order():
    # indicator_model.py:244-266 — seed(100), sample(cnames), classes sorted by code.
    # LandCoverScheme.palette()/.color_by_class() (Task 3) own that sampling; this
    # pins that resolve() surfaces them unchanged.
    r = resolve(
        default_spec(land_cover=CustomLandCoverSource("users/x/a", "users/x/b", CUSTOM_SCHEME))
    )
    expected = random.Random(100).sample(CSS4_HEX, 3)
    assert r.lc_palette == tuple(expected)
    assert dict(r.lc_color_by_class) == dict(
        zip(("Crops", "Water", "Forest"), expected, strict=True)
    )


@pytest.mark.parametrize(
    "lookup,table",
    [
        (ProductivityLookup.GPGV2, PRODUCTIVITY_GPGV2),
        (ProductivityLookup.GPGV1, PRODUCTIVITY_GPGV1),
    ],
)
def test_productivity_table_branch(lookup, table):
    # run_15_3_1.py:184-197 — GPGv2 takes productivity_final, anything else GPG1.
    assert resolve(default_spec(productivity_lookup=lookup)).productivity_table is table


GOLDEN = Path(__file__).parent / "golden" / "derived_snapshot_default.json"


def test_derived_snapshot_omits_the_spec_and_is_json_serializable():
    snapshot = resolve(default_spec()).derived_snapshot()
    assert "spec" not in snapshot
    assert json.loads(json.dumps(snapshot, sort_keys=True)) == snapshot


def test_derived_snapshot_matches_the_committed_golden():
    golden = json.loads(GOLDEN.read_text())

    # The golden is generated, so pin the values that matter by hand as well.
    assert golden["analysis_scale"] == 250
    assert golden["zonal_scale"] == 300
    assert golden["integration_period"] == {"start": 2000, "end": 2020}
    assert golden["trend"] == {"start": 2000, "end": 2020}
    assert golden["soc_period"] == {"start": 2000, "end": 2020}
    assert golden["lc_year_start_esa"] == 2000
    assert golden["lc_year_end_esa"] == 2020
    assert golden["soc_year_start"] == 2000
    assert golden["soc_year_end_esa"] == 2020
    assert golden["vi_processor"] == "modis"
    assert golden["vi_assets"] == ["MODIS/061/MOD13Q1"]
    assert golden["lc_class_combinations"] == list(IPCC_TRANSITION_CODES)
    assert golden["lc_palette"] == list(DEFAULT_LC_COLORS.values())

    assert resolve(default_spec()).derived_snapshot() == golden


def test_the_two_data_models_share_no_field_name():
    """Spec §13 risk 1's named mitigation, which was specified and never written.

    > "**Two data models is a standing tax.** ... Enforce with a test asserting the
    > two field-name sets are disjoint. Without it the split rots within two
    > features."

    A name on both sides is how the split rots: `RunSpec.threshold` and a
    `ResolvedSpec.threshold` would read alike at every call site, and the engine
    reads BOTH objects -- `r.spec.threshold` and `r.integration_period` in the same
    function -- so nothing at the point of use would say which one was meant. The
    property holds today (13 fields against 20); the app-layer phase is when both
    models start growing, which is what makes the guard worth having now.

    `spec` is excluded because it is not a derived value: it is the RunSpec itself,
    hanging off the ResolvedSpec so the engine can reach both through one object.
    """
    run_fields = {field.name for field in dataclasses.fields(RunSpec)}
    derived_fields = {field.name for field in dataclasses.fields(ResolvedSpec)} - {"spec"}

    # both directions of the premise: an empty set is disjoint from everything, so
    # a dataclass that lost its fields would make the assertion below vacuous
    assert len(run_fields) > 10, sorted(run_fields)
    assert len(derived_fields) > 10, sorted(derived_fields)
    assert run_fields & derived_fields == set(), sorted(run_fields & derived_fields)


def test_resolve_is_on_the_json_half_roster():
    # tests/test_isolation.py:98-110 already parametrizes a strictly stronger ee-import
    # guard (bans the ten UI libraries too, proves the blocker isn't inert, runs from
    # REPO_ROOT) over the JSON_HALF roster. This only pins that sdg1531.resolve stays
    # on it, rather than re-rolling a weaker, cwd-fragile copy of that guard here.
    from test_isolation import JSON_HALF

    assert "sdg1531.resolve" in JSON_HALF
