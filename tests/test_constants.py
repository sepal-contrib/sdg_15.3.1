"""The constants layer is a transcription of component/parameter/*.

Every assertion here is against a hardcoded literal, pinning the port's shape and
values in place — it does not re-derive them from the legacy source. The
against-legacy comparison lives in tools/check_transcription.py, which imports
component/parameter/matrix.py and sensor.py directly and diffs them against
sdg1531.tables and sdg1531.catalog."""

from __future__ import annotations

import math
import re
from dataclasses import FrozenInstanceError

import pytest

# The two modules allowed to name a colour: `tables.py` holds the two legacy legend
# dicts (parameter/ui.py:48-69) and `palette.py` the vendored CSS4 sequence
# LandCoverScheme.palette() samples. Everything else reads from one of them.
COLOUR_MODULES = ("sdg1531/palette.py", "sdg1531/tables.py")


# --------------------------------------------------------------------------
# errors
# --------------------------------------------------------------------------
def test_error_hierarchy() -> None:
    from sdg1531.errors import CustomMatrixError, DomainError, SpecError, StatisticsError

    assert issubclass(DomainError, Exception)
    for sub in (SpecError, CustomMatrixError, StatisticsError):
        assert issubclass(sub, DomainError)
    assert SpecError is not CustomMatrixError


# --------------------------------------------------------------------------
# enums — values are the legacy strings the science and the JSON both carry
# --------------------------------------------------------------------------
def test_vegetation_index_values() -> None:
    from sdg1531.enums import VegetationIndex

    # parameter/ui.py:5-9
    assert [v.value for v in VegetationIndex] == ["ndvi", "evi", "msvi"]
    assert VegetationIndex.NDVI == "ndvi"


def test_trajectory_values_in_legacy_order() -> None:
    from sdg1531.enums import Trajectory

    # parameter/ui.py:32-37
    assert [v.value for v in Trajectory] == [
        "ndvi_trend",
        "p_res_trend",
        "s_res_trend",
        "ue_trend",
    ]


def test_lceu_values_in_legacy_order() -> None:
    from sdg1531.enums import Lceu

    # parameter/ui.py:11-25
    assert [v.value for v in Lceu] == ["gaes", "aez", "wte", "hru", "calculate"]


def test_productivity_lookup_values() -> None:
    from sdg1531.enums import ProductivityLookup

    # parameter/ui.py:27-30
    assert [v.value for v in ProductivityLookup] == ["GPGv2", "GPGv1"]


def test_indicator_layer_is_exactly_the_seven_outputs() -> None:
    from sdg1531.enums import IndicatorLayer

    # indicator_model.py:272-278, in that order
    assert [v.value for v in IndicatorLayer] == [
        "land_cover",
        "soc",
        "productivity",
        "productivity_trend",
        "productivity_state",
        "productivity_performance",
        "indicator_15_3_1",
    ]
    assert len(IndicatorLayer) == 7


# --------------------------------------------------------------------------
# catalog
# --------------------------------------------------------------------------
def test_sensor_table_matches_the_legacy_dict() -> None:
    from sdg1531.catalog import SENSORS

    # parameter/sensor.py:14-33 — order is load-bearing (the ladder in
    # integration.py:45-94 makes precedence observable)
    assert list(SENSORS) == [
        "Landsat 4",
        "Derived VI Landsat",
        "Landsat 5",
        "Landsat 7",
        "MODIS MOD13Q1",
        "Terra NPP",
        "MODIS MYD13Q1",
        "Landsat 8",
        "Sentinel 2",
        "Landsat 9",
    ]
    l4 = SENSORS["Landsat 4"]
    assert (l4.collection_id, l4.scale, l4.code, l4.level) == (
        "LANDSAT/LT04/C02/T1_L2",
        30,
        "l4",
        "SR",
    )
    s2 = SENSORS["Sentinel 2"]
    assert (s2.collection_id, s2.scale, s2.code, s2.level) == (
        "COPERNICUS/S2_SR_HARMONIZED",
        10,
        "s2",
        "SR",
    )
    derived = SENSORS["Derived VI Landsat"]
    assert derived.collection_id == (
        "LANDSAT/COMPOSITES/C02/T1_L2_32DAY_NDVI",
        "LANDSAT/COMPOSITES/C02/T1_L2_32DAY_EVI",
    )
    assert (derived.scale, derived.code, derived.level) == (30, "", "VI")
    assert SENSORS["Terra NPP"].collection_id == "MODIS/006/MOD17A3HGF"
    assert SENSORS["MODIS MOD13Q1"].collection_id == "MODIS/061/MOD13Q1"
    assert SENSORS["MODIS MYD13Q1"].collection_id == "MODIS/061/MYD13Q1"
    assert SENSORS["Landsat 9"].code == "l9"


def test_sensor_records_are_frozen() -> None:
    from sdg1531.catalog import SENSORS

    with pytest.raises(FrozenInstanceError):
        SENSORS["Landsat 4"].scale = 60  # type: ignore[misc]


def test_sensor_table_is_not_mutable() -> None:
    from sdg1531.catalog import SENSORS

    with pytest.raises(TypeError):
        SENSORS["Landsat 4"] = None  # type: ignore[index]


def test_asset_ids_match_the_legacy_module() -> None:
    from sdg1531.catalog import ASSETS

    # parameter/sensor.py:36-47; soc_isric is dropped (zero call sites, spec §7)
    assert ASSETS == {
        "precipitation": "NOAA/PERSIANN-CDR",
        "land_cover_ic": "users/amitghosh/sdg_module/esa/cci_landcover",
        "jrc_water": "JRC/GSW1_3/GlobalSurfaceWater",
        "soil_taxonomy": "OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02",
        "soc": "users/geflanddegradation/toolbox_datasets/soc_sgrid_30cm",
        "ipcc_climate_zones": "users/geflanddegradation/toolbox_datasets/ipcc_climate_zones",
        "wte": "users/amitghosh/sdg_module/wte_2020",
        "gaes": "users/amitghosh/sdg_module/fao/GAES_L4",
        "aez": "users/amitghosh/sdg_module/fao/aez_v9v2_CRUTS32_Hist_8110_100_avg",
        "hru": "users/amitghosh/sdg_module/hru_250",
    }
    assert "soc_isric" not in ASSETS


def test_int16_min_is_the_numpy_value_without_numpy() -> None:
    from sdg1531.catalog import INT16_MIN

    # parameter/computation.py:5 — np.iinfo(np.int16).min is a plain int, so the
    # literal keeps the encoded graph byte-identical while numpy leaves the deps
    assert INT16_MIN == -32768
    assert type(INT16_MIN) is int


@pytest.mark.parametrize("n", [4, 5, 10, 23, 40])
def test_z_coefficient_matches_the_legacy_formula(n: int) -> None:
    from sdg1531.catalog import z_coefficient

    # parameter/computation.py:8-10
    expected = (3 * math.sqrt(n * (n - 1))) / (math.sqrt(2 * (2 * n + 5)))
    assert z_coefficient(n) == expected


def test_climate_coefficients_are_the_five_from_ui() -> None:
    from sdg1531.catalog import CLIMATE_COEFFICIENTS

    # parameter/ui.py:41-47, in that order
    assert list(CLIMATE_COEFFICIENTS.values()) == [0.80, 0.69, 0.58, 0.48, 0.64]
    assert list(CLIMATE_COEFFICIENTS) == [
        "temperate_dry",
        "temperate_moist",
        "tropical_dry",
        "tropical_moist",
        "tropical_montane",
    ]


def test_jrc_seasonality_ticks() -> None:
    from sdg1531.catalog import JRC_SEASONALITY_TICKS

    # parameter/ui.py:39
    assert JRC_SEASONALITY_TICKS == (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)


def test_year_constants() -> None:
    from sdg1531.catalog import L4_START, LAND_COVER_FIRST_YEAR, LAND_COVER_MAX_YEAR

    # parameter/sensor.py:4, 7, 11
    assert L4_START == 1982
    assert LAND_COVER_FIRST_YEAR == 1992
    assert LAND_COVER_MAX_YEAR == 2022


def test_s_res_trend_is_marked_disabled() -> None:
    from sdg1531.catalog import DISABLED_TRAJECTORIES
    from sdg1531.enums import Trajectory

    # parameter/ui.py:35 carries "disabled": True; productivity.py:42-43 raises a
    # bare NameError if it is ever selected
    assert DISABLED_TRAJECTORIES == (Trajectory.S_RES_TREND,)


# --------------------------------------------------------------------------
# tables
# --------------------------------------------------------------------------
def test_default_transition_matrix() -> None:
    from sdg1531.tables import DEFAULT_TRANSITION_MATRIX

    # parameter/matrix.py:1-17
    assert DEFAULT_TRANSITION_MATRIX == (
        (0, -1, -1, -1, -1, -1, 0),
        (1, 0, 1, -1, -1, -1, 0),
        (1, -1, 0, -1, -1, -1, 0),
        (-1, -1, -1, 0, -1, -1, 0),
        (1, 1, 1, 1, 0, 1, 0),
        (1, 1, 1, 1, -1, 0, 0),
        (0, 0, 0, 0, 0, 0, 0),
    )
    assert all(isinstance(row, tuple) for row in DEFAULT_TRANSITION_MATRIX)


def test_ipcc_transition_codes() -> None:
    from sdg1531.tables import DEFAULT_LC_CODES, IPCC_TRANSITION_CODES

    # parameter/matrix.py:49-99 — the 49 codes 1010..7070, one per (start, end)
    # class pair: code = start * 100 + end, over the seven-class vocabulary
    assert len(IPCC_TRANSITION_CODES) == 49
    assert (
        tuple(start * 100 + end for start in DEFAULT_LC_CODES for end in DEFAULT_LC_CODES)
        == IPCC_TRANSITION_CODES
    )
    assert IPCC_TRANSITION_CODES[0] == 1010
    assert IPCC_TRANSITION_CODES[-1] == 7070


def test_translation_matrix() -> None:
    from sdg1531.tables import TRANSLATION_MATRIX

    # parameter/matrix.py:179-258 — 37 ESA codes onto {10,20,30,40,50,60,70}
    assert len(TRANSLATION_MATRIX) == 2
    assert len(TRANSLATION_MATRIX[0]) == 37
    assert len(TRANSLATION_MATRIX[1]) == 37
    assert TRANSLATION_MATRIX[0][:5] == (10, 11, 12, 20, 30)
    assert TRANSLATION_MATRIX[0][-3:] == (202, 210, 220)
    assert TRANSLATION_MATRIX[1][:6] == (30, 30, 30, 30, 30, 30)
    assert TRANSLATION_MATRIX[1][-3:] == (60, 70, 60)
    assert set(TRANSLATION_MATRIX[1]) == {10, 20, 30, 40, 50, 60, 70}


def test_esa_and_reclassification_lists_pair_up() -> None:
    from sdg1531.tables import ESA_LC_CLASSES, RECLASSIFICATION_MATRIX

    # parameter/matrix.py:101-177, consumed together at productivity.py:111
    assert len(ESA_LC_CLASSES) == 36
    assert tuple(range(1, 37)) == RECLASSIFICATION_MATRIX
    assert ESA_LC_CLASSES[:6] == (10, 11, 12, 20, 30, 40)
    assert ESA_LC_CLASSES[-4:] == (200, 201, 202, 210)


def test_label_dicts() -> None:
    from sdg1531.tables import (
        DEGRADATION_LABELS,
        PROD_PERFORMANCE_LABELS,
        PROD_STATE_5_LABELS,
        PROD_TREND_5_LABELS,
    )

    # parameter/matrix.py:30-47 — the misspellings are transcribed, not fixed
    assert DEGRADATION_LABELS == {0: "NoData", 1: "Degraded", 2: "Stable", 3: "Improved"}
    five = {
        0: "NoData",
        1: "Degraded",
        2: "At risk of degrading",
        3: "No significant chnage",
        4: "Potentially improving",
        5: "Improving",
    }
    assert five == PROD_TREND_5_LABELS
    assert five == PROD_STATE_5_LABELS
    assert PROD_PERFORMANCE_LABELS == {0: "NoData", 1: "Degraded", 2: "Not degraded"}


def test_degradation_colours_key_on_the_degradation_labels() -> None:
    """The palette and the legend it colours are one vocabulary, in one module.

    The four hexes lived only in ``stats/plots.py``, split across a private
    three-entry dict and a separate ``_UNKNOWN_CLASS_COLOR`` -- so an app layer
    building the seven ``visualization_*`` property sets and the map legend had to
    reach into a private name, retype the hexes (which spec §4 forbids) or invent a
    fourth colour for NoData that the charts would not agree with. This is the
    derivation that keeps them one thing: the palette's keys are not a second
    roster, they are ``DEGRADATION_LABELS``' own values.
    """
    from sdg1531.tables import DEGRADATION_COLORS, DEGRADATION_LABELS

    assert list(DEGRADATION_COLORS) == list(DEGRADATION_LABELS.values())


def test_degradation_colours_are_the_legacy_legend_bar() -> None:
    """parameter/ui.py:54-59 (pm.legend_bar), whose first three entries are also
    ``legend`` (:48-52) -- the palette every ``viz_*`` dict at :72-75 spreads over a
    ``{"min": 1, "max": 3}`` visualisation."""
    from sdg1531.tables import DEGRADATION_COLORS

    assert list(DEGRADATION_COLORS.values()) == ["#9ea7ad", "#d7191c", "#ffffbf", "#2c7bb6"]
    # the three the legacy viz dicts actually draw, in min..max order
    assert list(DEGRADATION_COLORS.values())[1:] == ["#d7191c", "#ffffbf", "#2c7bb6"]


def test_the_domains_colours_live_in_the_two_colour_modules() -> None:
    """Two undeclared sources of truth is the thing the move was for.

    A module that re-types a hex passes every value assertion in this file --
    ``"#9ea7ad" == DEGRADATION_COLORS["NoData"]`` is true whether the second copy
    exists or not -- so the check that can actually fail is on the SOURCE. The
    degradation hexes lived only in ``stats/plots.py`` until now, which is what made
    them unreachable for the app layer.

    Both directions: a module that grows a colour fails, and a module named here
    that no longer holds one fails too, so the pair cannot go stale by rename.
    Scanned over ``iter_domain_sources()``, so the app package joins the rule the
    day it lands -- and spec §4 puts the app layer's four viz dicts on exactly these
    values.
    """
    from hygiene_rules import iter_domain_sources

    colour = re.compile(r"\"#[0-9a-fA-F]{6}\"")
    carriers = {rel for rel, source in iter_domain_sources() if colour.search(source)}

    assert carriers == set(COLOUR_MODULES), {
        "colours outside the colour modules": sorted(carriers - set(COLOUR_MODULES)),
        "colour modules that hold none": sorted(set(COLOUR_MODULES) - carriers),
    }


def test_default_land_cover_vocabulary() -> None:
    from sdg1531.tables import DEFAULT_LC_CLASS_NAMES, DEFAULT_LC_CODES, DEFAULT_LC_COLORS

    # parameter/matrix.py:19-28 and parameter/ui.py:61-69
    assert DEFAULT_LC_CODES == (10, 20, 30, 40, 50, 60, 70)
    assert DEFAULT_LC_CLASS_NAMES == (
        "Tree-covered areas",
        "Grassland",
        "Cropland",
        "Wetland",
        "Artificial surfaces",
        "Other land",
        "Water bodies",
    )
    assert list(DEFAULT_LC_COLORS) == list(DEFAULT_LC_CLASS_NAMES)
    assert list(DEFAULT_LC_COLORS.values()) == [
        "#02A000",
        "#FFB432",
        "#FFFF64",
        "#04DC83",
        "#C31400",
        "#FFF5D7",
        "#0046C8",
    ]


def test_soc_factor_tables() -> None:
    from sdg1531.tables import (
        C_CONVERSION_FACTOR,
        CLIMATE_CONVERSION_MATRIX,
        INPUT_FACTOR,
        MANAGEMENT_FACTOR,
    )

    # parameter/matrix.py:311-469
    assert CLIMATE_CONVERSION_MATRIX == (
        (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12),
        (0, 0.69, 0.8, 0.69, 0.8, 0.69, 0.8, 0.69, 0.8, 0.64, 0.48, 0.48, 0.58),
    )
    assert len(C_CONVERSION_FACTOR) == 49
    assert C_CONVERSION_FACTOR[:6] == (1, 1, 333, 1, 0.1, 0.1)
    assert C_CONVERSION_FACTOR[14:16] == (-333, -333)
    # matrix.py:334 is written `1 / 0.71`; the float repr is load-bearing for parity
    assert C_CONVERSION_FACTOR[17] == 1 / 0.71
    assert repr(C_CONVERSION_FACTOR[17]) == "1.4084507042253522"
    assert C_CONVERSION_FACTOR[23] == 0.71
    assert tuple([1] * 49) == MANAGEMENT_FACTOR
    assert tuple([1] * 49) == INPUT_FACTOR
