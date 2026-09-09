"""sdg1531.naming — run labels and GEE asset ids. Pure; no ee, no filesystem."""

import re
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import sdg1531
from sdg1531 import naming
from sdg1531.catalog import SENSORS
from sdg1531.enums import (
    IndicatorLayer,
    Lceu,
    ProductivityLookup,
    Trajectory,
    VegetationIndex,
)
from sdg1531.scheme import TransitionMatrix
from sdg1531.spec import (
    AssetAoi,
    Compatibility,
    CustomLandCoverSource,
    EsaCciSource,
    FixedClimate,
    JrcSeasonalityMask,
    Period,
    PeriodOverride,
    PerPixelClimate,
    PrecomputedViAsset,
    RunSpec,
    SensorSelection,
    SubPeriods,
)


def _spec(**changes) -> RunSpec:
    """A complete, valid RunSpec; `changes` are applied through evolve()."""
    base = RunSpec(
        periods=SubPeriods(overall=Period(2000, 2015)),
        vi_source=SensorSelection(names=("Landsat 8",)),
        vegetation_index=VegetationIndex.NDVI,
        threshold=None,
        trajectory=Trajectory.NDVI_TREND,
        lceu=Lceu.GAES,
        productivity_lookup=ProductivityLookup.GPGV2,
        transition_matrix=TransitionMatrix.default(),
        land_cover=EsaCciSource(),
        water_mask=JrcSeasonalityMask(threshold=6),
        climate=PerPixelClimate(),
        aoi=AssetAoi("users/test/aoi", "test-aoi"),
        compatibility=Compatibility(),
    )
    return base.evolve(**changes) if changes else base


def test_normalize_str_scrubs_to_asset_safe_characters():
    assert naming.normalize_str("Côte d'Ivoire") == "Cote_d_Ivoire"
    assert naming.normalize_str("2000_2015_l8-ndvi") == "2000_2015_l8-ndvi"
    assert naming.normalize_str("a/b c.d") == "a_b_c_d"


def test_normalize_str_display_mode_keeps_spaces_and_apostrophes():
    assert naming.normalize_str("Côte d'Ivoire", folder=False) == "Cote d'Ivoire"


def test_naming_does_not_import_ee():
    # sys.modules["ee"] = None makes any `import ee` raise ImportError, so the
    # subprocess exits non-zero if naming (or anything it imports) pulls ee in.
    code = "import sys; sys.modules['ee'] = None; import sdg1531.naming"
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(sdg1531.__file__).parents[1],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_run_label_has_the_legacy_shape():
    # indicator_model.py:312 — {start}_{end}_{sensor}_{vi}_{lceu}_{lc_matrix}_{climate}
    assert naming.run_label(_spec()) == "2000_2015_l8_ndvi_gaes_default_crpix"


def test_run_label_omits_the_trajectory():
    # indicator_model.py:299 binds `trajectory` and :312 never interpolates it.
    assert naming.run_label(_spec(trajectory=Trajectory.UE_TREND)) == naming.run_label(_spec())


def test_run_label_varies_with_index_and_lceu():
    label = naming.run_label(_spec(vegetation_index=VegetationIndex.EVI, lceu=Lceu.WTE))
    assert label == "2000_2015_l8_evi_wte_default_crpix"


def test_run_label_is_total_on_the_default_climate_regime():
    # indicator_model.py:310 raises TypeError here: conversion_coef defaults to
    # None and climate_regime.py:23 defaults the regime to "per pixel".
    assert naming.run_label(_spec(climate=PerPixelClimate())).endswith("_crpix")


@pytest.mark.parametrize(
    "coefficient,token",
    [
        (0.80, "cr80"),
        (0.69, "cr69"),
        # int(0.58 * 100) == 57 in binary floating point; :310's formula is
        # preserved verbatim, so the label says cr57.
        (0.58, "cr57"),
        (0.48, "cr48"),
        (0.64, "cr64"),
    ],
)
def test_run_label_is_total_over_every_fixed_coefficient(coefficient, token):
    # the five values of parameter/ui.py:41-47
    label = naming.run_label(_spec(climate=FixedClimate(coefficient)))
    assert label == f"2000_2015_l8_ndvi_gaes_default_{token}"


def test_custom_land_cover_labels_the_run_custom():
    spec = _spec(
        land_cover=CustomLandCoverSource(
            start_asset="users/test/lc2000", end_asset="users/test/lc2015"
        )
    )
    assert naming.run_label(spec).split("_")[-2] == "custom"


def test_precomputed_vi_still_produces_a_label():
    spec = _spec(vi_source=PrecomputedViAsset(asset_id="users/test/vi", scale=30))
    assert naming.run_label(spec) == "2000_2015_asset_ndvi_gaes_default_crpix"


def test_matrix_edit_flips_the_label():
    # indicator_model.py:305 compares pm.default_trans_matrix with itself and is
    # permanently False, so a matrix-only edit was labelled "default" and
    # overwrote the previous run's directory (spec §7).
    edited = TransitionMatrix.default().with_cell(0, 1, 1)

    assert naming.run_label(_spec()).split("_")[-2] == "default"
    assert naming.run_label(_spec(transition_matrix=edited)).split("_")[-2] == "custom"


def test_custom_matrix_and_custom_land_cover_together_stay_custom():
    edited = TransitionMatrix.default().with_cell(0, 1, 1)
    spec = _spec(
        transition_matrix=edited,
        land_cover=CustomLandCoverSource(
            start_asset="users/test/lc2000", end_asset="users/test/lc2015"
        ),
    )
    assert naming.run_label(spec).split("_")[-2] == "custom"


def test_legacy_sensor_folder_token_is_l2_for_sentinel():
    # Preserved by default: that string names the result directory whose
    # existing zip run_15_3_1.py:313-317 checks for.
    spec = _spec(vi_source=SensorSelection(names=("Sentinel 2",)))
    assert naming.run_label(spec).split("_")[2] == "l2"


def test_sensor_folder_token_is_s2_with_the_flag_off():
    spec = _spec(
        vi_source=SensorSelection(names=("Sentinel 2",)),
        compatibility=Compatibility(legacy_sensor_folder_token=False),
    )
    assert naming.run_label(spec).split("_")[2] == "s2"


@pytest.mark.parametrize(
    "sensors,legacy,fixed",
    [
        (("Landsat 8",), "l8", "l8"),
        # the legacy Landsat join is unreachable: "Landsat 4" has no lowercase l
        (("Landsat 4", "Landsat 8"), "l4", "l48"),
        (("Landsat 5", "Landsat 7", "Landsat 9"), "l5", "l579"),
        (("MODIS MOD13Q1",), "modis", "modis"),
        (("Terra NPP",), "modis", "modis"),
        (("Sentinel 2",), "l2", "s2"),
        (("Derived VI Landsat",), "", ""),
    ],
)
def test_sensor_token_both_ways(sensors, legacy, fixed):
    on = _spec(vi_source=SensorSelection(names=sensors))
    off = _spec(
        vi_source=SensorSelection(names=sensors),
        compatibility=Compatibility(legacy_sensor_folder_token=False),
    )
    assert naming.run_label(on).split("_")[2] == legacy
    assert naming.run_label(off).split("_")[2] == fixed


def test_sensor_token_is_total_for_a_short_unknown_name_containing_l():
    # :290 subscripts token[1], which index-errors on a token shorter than two
    # characters (spec §7). A name outside the catalog that is itself just "l"
    # reproduces exactly that: "l" in names[0] is True, and the catalog-token
    # fallback (normalize_str(name).lower()) hands back the single character
    # "l" right back — none of the catalog sensors are this short, so this is
    # the one case the fuzz strategy below (which only draws catalog names)
    # cannot reach.
    spec = _spec(vi_source=SensorSelection(names=("l",)))
    assert naming.run_label(spec).split("_")[2] == "l"


# --- run_label totality over the whole RunSpec space (mirrors test_validate's
# run_specs fuzz, but also varies climate/vegetation_index/lceu/compatibility,
# which validate() does not need to and run_label does interpolate). ---

_SENSOR_NAMES = (*SENSORS, "Unknown Sensor")

_years = st.one_of(st.none(), st.integers(min_value=1900, max_value=2100))
_periods = st.builds(Period, start=_years, end=_years)
_overrides = st.builds(PeriodOverride, start=_years, end=_years)
_sub_periods = st.builds(
    SubPeriods,
    overall=_periods,
    trend=_overrides,
    state=_overrides,
    performance=_overrides,
    land_cover=_overrides,
    soc=_overrides,
)


@st.composite
def _matrices(draw: st.DrawFn) -> TransitionMatrix:
    rows = draw(st.integers(min_value=1, max_value=3))
    cols = draw(st.integers(min_value=1, max_value=3))
    values = draw(
        st.lists(st.integers(min_value=-3, max_value=3), min_size=rows * cols, max_size=rows * cols)
    )
    return TransitionMatrix(tuple(tuple(values[i * cols : (i + 1) * cols]) for i in range(rows)))


_vi_sources = st.one_of(
    st.none(),
    st.builds(
        SensorSelection,
        names=st.lists(st.sampled_from(_SENSOR_NAMES), max_size=3).map(tuple),
    ),
    st.builds(
        PrecomputedViAsset,
        asset_id=st.text(max_size=8),
        scale=st.integers(min_value=1, max_value=300),
    ),
)
_land_cover_sources = st.one_of(
    st.just(EsaCciSource()),
    st.builds(
        CustomLandCoverSource,
        start_asset=st.text(max_size=8),
        end_asset=st.text(max_size=8),
        scheme=st.none(),
    ),
)
_climates = st.one_of(
    st.just(PerPixelClimate()),
    st.builds(
        FixedClimate,
        coefficient=st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False),
    ),
)
_run_specs = st.builds(
    RunSpec,
    periods=_sub_periods,
    vi_source=_vi_sources,
    vegetation_index=st.sampled_from(list(VegetationIndex)),
    trajectory=st.sampled_from(list(Trajectory)),
    lceu=st.sampled_from(list(Lceu)),
    productivity_lookup=st.sampled_from(list(ProductivityLookup)),
    transition_matrix=_matrices(),
    land_cover=_land_cover_sources,
    climate=_climates,
    aoi=st.none(),
    compatibility=st.builds(Compatibility, legacy_sensor_folder_token=st.booleans()),
)


@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
@given(_run_specs)
def test_run_label_never_raises(spec):
    label = naming.run_label(spec)
    assert isinstance(label, str)
    assert label != ""
    assert naming.run_id(spec) == naming.normalize_str(label)


def test_run_id_is_the_normalized_label():
    spec = _spec(lceu=Lceu.CALCULATE, climate=FixedClimate(0.69))
    identifier = naming.run_id(spec)

    assert identifier == naming.normalize_str(naming.run_label(spec))
    assert re.fullmatch(r"[A-Za-z\d_-]+", identifier)


def test_run_id_survives_an_empty_sensor_token():
    spec = _spec(vi_source=SensorSelection(names=("Derived VI Landsat",)))
    assert naming.run_id(spec) == "2000_2015__ndvi_gaes_default_crpix"


def test_layer_basenames_covers_every_indicator_layer():
    names = naming.layer_basenames(_spec())

    assert set(names) == {layer.value for layer in IndicatorLayer}
    assert names["land_cover"] == "land_cover"
    assert names["soc"] == "soc"
    assert names["productivity"] == "productivity_indicator"
    assert names["productivity_trend"] == "productivity_trend"
    assert names["productivity_state"] == "productivity_state"
    assert names["productivity_performance"] == "productivity_performance"
    assert names["indicator_15_3_1"] == "indicator_15_3_1"


def test_layer_basenames_returns_a_fresh_mapping():
    names = naming.layer_basenames(_spec())
    names["soc"] = "tampered"

    assert naming.layer_basenames(_spec())["soc"] == "soc"


ROOT = "projects/test/assets/sdg"
STEM = f"{ROOT}/2000_2015_l8_ndvi_gaes_default_crpix"


def test_asset_path_composes_root_run_and_basename():
    assert naming.asset_path(ROOT, _spec(), IndicatorLayer.SOC) == f"{STEM}_soc"
    assert (
        naming.asset_path(ROOT, _spec(), IndicatorLayer.PRODUCTIVITY)
        == f"{STEM}_productivity_indicator"
    )


def test_asset_path_accepts_a_bare_layer_id():
    assert naming.asset_path(ROOT, _spec(), "soc") == naming.asset_path(
        ROOT, _spec(), IndicatorLayer.SOC
    )


def test_asset_path_trims_a_trailing_slash_from_root():
    assert naming.asset_path(f"{ROOT}/", _spec(), IndicatorLayer.SOC) == f"{STEM}_soc"


def test_asset_path_suffixes_on_collision():
    spec = _spec()
    first = naming.asset_path(ROOT, spec, IndicatorLayer.INDICATOR_15_3_1)
    second = naming.asset_path(ROOT, spec, IndicatorLayer.INDICATOR_15_3_1, taken=(first,))
    third = naming.asset_path(ROOT, spec, IndicatorLayer.INDICATOR_15_3_1, taken=(first, second))

    assert first == f"{STEM}_indicator_15_3_1"
    assert second == f"{first}_1"
    assert third == f"{first}_2"


def test_asset_path_suffix_does_not_rename_the_layer():
    # "indicator_15_3_1" ends in a digit, so a next_string-style increment
    # (pysepal scripts/utils.py:184-202) would silently rename the layer.
    spec = _spec()
    first = naming.asset_path(ROOT, spec, IndicatorLayer.INDICATOR_15_3_1)
    bumped = naming.asset_path(ROOT, spec, IndicatorLayer.INDICATOR_15_3_1, taken=[first])

    assert bumped.endswith("indicator_15_3_1_1")


def test_asset_path_ignores_unrelated_taken_ids():
    spec = _spec()
    unrelated = (f"{STEM}_soc", "projects/other/assets/thing")

    assert (
        naming.asset_path(ROOT, spec, IndicatorLayer.LAND_COVER, taken=unrelated)
        == f"{STEM}_land_cover"
    )
