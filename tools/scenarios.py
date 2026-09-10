"""The parity scenario corpus. Imports only the JSON half of sdg1531 (no ee).

One row per scenario, one column per axis. The corpus is a pairwise REDUCTION,
not an exhaustive product, so `tests/parity/test_scenarios.py` asserts what it
actually covers rather than trusting the table to be right by inspection.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from sdg1531.enums import Lceu, ProductivityLookup, Trajectory, VegetationIndex
from sdg1531.scheme import TransitionMatrix, parse_custom_matrix_csv, read_matrix_csv
from sdg1531.spec import (
    AssetAoi,
    AssetBandMask,
    Compatibility,
    CustomLandCoverSource,
    EsaCciSource,
    FixedClimate,
    GeoJsonAoi,
    JrcSeasonalityMask,
    Period,
    PeriodOverride,
    PerPixelClimate,
    PixelValueMask,
    RunSpec,
    SensorSelection,
    SubPeriods,
)

__all__ = ["AXES", "SCENARIOS", "axis_levels"]

# a 10 km box in Senegal; small enough that the network smoke test can reuse it
_AOI_GEOJSON: dict[str, Any] = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"name": "test-box"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-15.60, 14.60],
                        [-15.50, 14.60],
                        [-15.50, 14.70],
                        [-15.60, 14.70],
                        [-15.60, 14.60],
                    ]
                ],
            },
        }
    ],
}

_GEOJSON_AOI = GeoJsonAoi(geojson=_AOI_GEOJSON, name="test box")
_ASSET_AOI = AssetAoi(asset_id="users/amitghosh/sdg_module/parity_aoi", name="parity aoi")

_CUSTOM_START = "users/amitghosh/sdg_module/parity_lc_start"
_CUSTOM_END = "users/amitghosh/sdg_module/parity_lc_end"

# The custom arm has to be genuinely custom. LandCoverScheme.default() carries
# is_custom=False, so if resolve() keys its custom-vocabulary precedence on
# scheme.is_custom, custom_full and custom_half would collapse onto the same
# behaviour and the half-custom defect would never be exercised. The golden CSV
# Task 3 committed parses to a 13-class vocabulary with is_custom=True.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_MATRIX_CSV = _REPO_ROOT / "tests" / "data" / "ipccsx_matrix.csv"
_CUSTOM_SCHEME = parse_custom_matrix_csv(read_matrix_csv(_MATRIX_CSV.read_text()))

_NO_OVERRIDES = SubPeriods(
    trend=PeriodOverride(None, None),
    state=PeriodOverride(None, None),
    performance=PeriodOverride(None, None),
    land_cover=PeriodOverride(None, None),
    soc=PeriodOverride(None, None),
)

AXES: dict[str, tuple[str, ...]] = {
    "sensor": ("modis", "modis_pair", "landsat_pair", "sentinel2", "derived_vi", "terra_npp"),
    "index": ("ndvi", "evi", "msvi"),
    "trajectory": ("ndvi_trend", "p_res_trend", "ue_trend"),
    "lceu": ("gaes", "aez", "wte", "hru", "calculate"),
    "lookup": ("GPGv2", "GPGv1"),
    "climate": ("per_pixel", "fixed_080", "fixed_048"),
    "land_cover": ("esa", "custom_full", "custom_half"),
    "water": ("jrc", "pixel_70", "pixel_10", "asset_band"),
    "matrix": ("default", "edited"),
    "sub_periods": ("none", "trend_state", "lc_soc"),
    "window": ("inside", "before_cci", "after_cci", "soc_after_cci"),
    "aoi": ("geojson", "asset"),
    "compat": ("default", "soc_scale_100", "clamp_soc_start"),
    "threshold": ("zero", "positive", "negative"),
}

_SENSORS = {
    "modis": SensorSelection(names=("MODIS MOD13Q1",)),
    "modis_pair": SensorSelection(names=("MODIS MOD13Q1", "MODIS MYD13Q1")),
    "landsat_pair": SensorSelection(names=("Landsat 8", "Landsat 9")),
    "sentinel2": SensorSelection(names=("Sentinel 2",)),
    "derived_vi": SensorSelection(names=("Derived VI Landsat",)),
    "terra_npp": SensorSelection(names=("Terra NPP",)),
}
_INDEX = {
    "ndvi": VegetationIndex.NDVI,
    "evi": VegetationIndex.EVI,
    "msvi": VegetationIndex.MSVI,
}
_TRAJECTORY = {
    "ndvi_trend": Trajectory.NDVI_TREND,
    "p_res_trend": Trajectory.P_RES_TREND,
    "ue_trend": Trajectory.UE_TREND,
}
_LCEU = {
    "gaes": Lceu.GAES,
    "aez": Lceu.AEZ,
    "wte": Lceu.WTE,
    "hru": Lceu.HRU,
    "calculate": Lceu.CALCULATE,
}
_LOOKUP = {"GPGv2": ProductivityLookup.GPGV2, "GPGv1": ProductivityLookup.GPGV1}
_CLIMATE = {
    "per_pixel": PerPixelClimate(),
    "fixed_080": FixedClimate(coefficient=0.80),
    "fixed_048": FixedClimate(coefficient=0.48),
}
_LAND_COVER = {
    "esa": EsaCciSource(),
    "custom_full": CustomLandCoverSource(
        start_asset=_CUSTOM_START, end_asset=_CUSTOM_END, scheme=_CUSTOM_SCHEME
    ),
    "custom_half": CustomLandCoverSource(
        start_asset=_CUSTOM_START, end_asset=_CUSTOM_END, scheme=None
    ),
}
_WATER = {
    "jrc": JrcSeasonalityMask(threshold=6),
    "pixel_70": PixelValueMask(value=70),
    "pixel_10": PixelValueMask(value=10),
    "asset_band": AssetBandMask(asset_id="users/amitghosh/sdg_module/parity_water", band="water"),
}
_MATRIX = {
    "default": TransitionMatrix.default(),
    "edited": TransitionMatrix.default().with_cell(1, 2, -1),
}
_SUB_PERIODS = {
    "none": _NO_OVERRIDES,
    "trend_state": SubPeriods(
        trend=PeriodOverride(2003, 2013),
        state=PeriodOverride(2005, None),
        performance=PeriodOverride(None, None),
        land_cover=PeriodOverride(None, None),
        soc=PeriodOverride(None, None),
    ),
    "lc_soc": SubPeriods(
        trend=PeriodOverride(None, None),
        state=PeriodOverride(None, None),
        performance=PeriodOverride(None, None),
        land_cover=PeriodOverride(2001, 2014),
        soc=PeriodOverride(None, 2012),
    ),
}
_WINDOW = {
    "inside": Period(2000, 2015),
    "before_cci": Period(1985, 2015),
    "after_cci": Period(2010, 2030),
    "soc_after_cci": Period(2023, 2030),
}
_AOI = {"geojson": _GEOJSON_AOI, "asset": _ASSET_AOI}
_COMPAT = {
    "default": Compatibility(),
    "soc_scale_100": Compatibility(soc_subsequent_transition_scale=100),
    "clamp_soc_start": Compatibility(clamp_soc_start_year=True),
}
# input_tile.py:31-38 -- a slider over [-1, 1] step 0.01, v_model=0. The value
# reaches `img.gt(threshold)` on five of the six VI rungs (integration.py:410-415),
# so it varies across the corpus: a port that ignored spec.threshold and hardcoded
# one number would still match a corpus that only ever used that number.
_THRESHOLD = {"zero": 0.0, "positive": 0.15, "negative": -0.25}

# name -> the level of every axis. 28 rows: sensor x index is exhaustive across the
# first 18, land_cover x water across the whole table, everything else 1-wise.
# fmt: off
_TABLE: tuple[tuple[str, dict[str, str]], ...] = (
    ("s01", {"sensor": "modis", "index": "ndvi", "trajectory": "ndvi_trend", "lceu": "gaes", "lookup": "GPGv2", "climate": "per_pixel", "land_cover": "esa", "water": "jrc", "matrix": "default", "sub_periods": "none", "window": "inside", "aoi": "geojson", "compat": "default", "threshold": "zero"}),
    ("s02", {"sensor": "modis", "index": "evi", "trajectory": "p_res_trend", "lceu": "aez", "lookup": "GPGv1", "climate": "fixed_080", "land_cover": "esa", "water": "pixel_70", "matrix": "edited", "sub_periods": "trend_state", "window": "before_cci", "aoi": "asset", "compat": "soc_scale_100", "threshold": "positive"}),
    ("s03", {"sensor": "modis", "index": "msvi", "trajectory": "ue_trend", "lceu": "wte", "lookup": "GPGv2", "climate": "fixed_048", "land_cover": "esa", "water": "pixel_10", "matrix": "default", "sub_periods": "lc_soc", "window": "after_cci", "aoi": "geojson", "compat": "clamp_soc_start", "threshold": "negative"}),
    ("s04", {"sensor": "modis_pair", "index": "ndvi", "trajectory": "p_res_trend", "lceu": "hru", "lookup": "GPGv1", "climate": "per_pixel", "land_cover": "esa", "water": "asset_band", "matrix": "edited", "sub_periods": "none", "window": "soc_after_cci", "aoi": "asset", "compat": "default", "threshold": "zero"}),
    ("s05", {"sensor": "modis_pair", "index": "evi", "trajectory": "ue_trend", "lceu": "calculate", "lookup": "GPGv2", "climate": "fixed_080", "land_cover": "custom_full", "water": "jrc", "matrix": "default", "sub_periods": "trend_state", "window": "inside", "aoi": "geojson", "compat": "soc_scale_100", "threshold": "positive"}),
    ("s06", {"sensor": "modis_pair", "index": "msvi", "trajectory": "ndvi_trend", "lceu": "gaes", "lookup": "GPGv1", "climate": "fixed_048", "land_cover": "custom_full", "water": "pixel_70", "matrix": "edited", "sub_periods": "lc_soc", "window": "before_cci", "aoi": "asset", "compat": "clamp_soc_start", "threshold": "negative"}),
    ("s07", {"sensor": "landsat_pair", "index": "ndvi", "trajectory": "ue_trend", "lceu": "aez", "lookup": "GPGv2", "climate": "per_pixel", "land_cover": "custom_full", "water": "pixel_10", "matrix": "default", "sub_periods": "none", "window": "after_cci", "aoi": "geojson", "compat": "default", "threshold": "zero"}),
    ("s08", {"sensor": "landsat_pair", "index": "evi", "trajectory": "ndvi_trend", "lceu": "wte", "lookup": "GPGv1", "climate": "fixed_080", "land_cover": "custom_full", "water": "asset_band", "matrix": "edited", "sub_periods": "trend_state", "window": "soc_after_cci", "aoi": "asset", "compat": "soc_scale_100", "threshold": "positive"}),
    ("s09", {"sensor": "landsat_pair", "index": "msvi", "trajectory": "p_res_trend", "lceu": "hru", "lookup": "GPGv2", "climate": "fixed_048", "land_cover": "custom_half", "water": "jrc", "matrix": "default", "sub_periods": "lc_soc", "window": "inside", "aoi": "geojson", "compat": "clamp_soc_start", "threshold": "negative"}),
    ("s10", {"sensor": "sentinel2", "index": "ndvi", "trajectory": "ndvi_trend", "lceu": "calculate", "lookup": "GPGv1", "climate": "per_pixel", "land_cover": "custom_half", "water": "pixel_70", "matrix": "edited", "sub_periods": "none", "window": "inside", "aoi": "asset", "compat": "default", "threshold": "zero"}),
    ("s11", {"sensor": "sentinel2", "index": "evi", "trajectory": "p_res_trend", "lceu": "gaes", "lookup": "GPGv2", "climate": "fixed_080", "land_cover": "custom_half", "water": "pixel_10", "matrix": "default", "sub_periods": "trend_state", "window": "after_cci", "aoi": "geojson", "compat": "soc_scale_100", "threshold": "positive"}),
    ("s12", {"sensor": "sentinel2", "index": "msvi", "trajectory": "ue_trend", "lceu": "aez", "lookup": "GPGv1", "climate": "fixed_048", "land_cover": "custom_half", "water": "asset_band", "matrix": "edited", "sub_periods": "lc_soc", "window": "before_cci", "aoi": "asset", "compat": "clamp_soc_start", "threshold": "negative"}),
    ("s13", {"sensor": "derived_vi", "index": "ndvi", "trajectory": "p_res_trend", "lceu": "wte", "lookup": "GPGv2", "climate": "per_pixel", "land_cover": "esa", "water": "jrc", "matrix": "default", "sub_periods": "none", "window": "inside", "aoi": "geojson", "compat": "default", "threshold": "zero"}),
    ("s14", {"sensor": "derived_vi", "index": "evi", "trajectory": "ue_trend", "lceu": "hru", "lookup": "GPGv1", "climate": "fixed_080", "land_cover": "esa", "water": "pixel_70", "matrix": "edited", "sub_periods": "trend_state", "window": "inside", "aoi": "asset", "compat": "soc_scale_100", "threshold": "positive"}),
    ("s15", {"sensor": "derived_vi", "index": "msvi", "trajectory": "ndvi_trend", "lceu": "calculate", "lookup": "GPGv2", "climate": "fixed_048", "land_cover": "esa", "water": "pixel_10", "matrix": "default", "sub_periods": "lc_soc", "window": "inside", "aoi": "geojson", "compat": "clamp_soc_start", "threshold": "negative"}),
    ("s16", {"sensor": "terra_npp", "index": "ndvi", "trajectory": "ue_trend", "lceu": "gaes", "lookup": "GPGv1", "climate": "per_pixel", "land_cover": "esa", "water": "asset_band", "matrix": "edited", "sub_periods": "none", "window": "inside", "aoi": "asset", "compat": "default", "threshold": "zero"}),
    ("s17", {"sensor": "terra_npp", "index": "evi", "trajectory": "ndvi_trend", "lceu": "aez", "lookup": "GPGv2", "climate": "fixed_080", "land_cover": "custom_full", "water": "jrc", "matrix": "default", "sub_periods": "trend_state", "window": "inside", "aoi": "geojson", "compat": "soc_scale_100", "threshold": "positive"}),
    ("s18", {"sensor": "terra_npp", "index": "msvi", "trajectory": "p_res_trend", "lceu": "wte", "lookup": "GPGv1", "climate": "fixed_048", "land_cover": "custom_half", "water": "jrc", "matrix": "edited", "sub_periods": "lc_soc", "window": "inside", "aoi": "asset", "compat": "clamp_soc_start", "threshold": "negative"}),
    ("s19", {"sensor": "modis", "index": "ndvi", "trajectory": "ndvi_trend", "lceu": "hru", "lookup": "GPGv2", "climate": "per_pixel", "land_cover": "custom_full", "water": "pixel_10", "matrix": "default", "sub_periods": "none", "window": "inside", "aoi": "geojson", "compat": "default", "threshold": "zero"}),
    ("s20", {"sensor": "modis", "index": "evi", "trajectory": "p_res_trend", "lceu": "calculate", "lookup": "GPGv1", "climate": "fixed_080", "land_cover": "custom_full", "water": "asset_band", "matrix": "edited", "sub_periods": "trend_state", "window": "inside", "aoi": "asset", "compat": "default", "threshold": "positive"}),
    ("s21", {"sensor": "landsat_pair", "index": "ndvi", "trajectory": "ue_trend", "lceu": "gaes", "lookup": "GPGv2", "climate": "fixed_048", "land_cover": "custom_half", "water": "pixel_70", "matrix": "default", "sub_periods": "lc_soc", "window": "inside", "aoi": "geojson", "compat": "soc_scale_100", "threshold": "negative"}),
    ("s22", {"sensor": "landsat_pair", "index": "evi", "trajectory": "ndvi_trend", "lceu": "aez", "lookup": "GPGv1", "climate": "per_pixel", "land_cover": "esa", "water": "jrc", "matrix": "edited", "sub_periods": "none", "window": "before_cci", "aoi": "asset", "compat": "clamp_soc_start", "threshold": "zero"}),
    ("s23", {"sensor": "sentinel2", "index": "ndvi", "trajectory": "p_res_trend", "lceu": "wte", "lookup": "GPGv2", "climate": "fixed_080", "land_cover": "esa", "water": "pixel_70", "matrix": "default", "sub_periods": "trend_state", "window": "after_cci", "aoi": "geojson", "compat": "default", "threshold": "positive"}),
    ("s24", {"sensor": "sentinel2", "index": "evi", "trajectory": "ue_trend", "lceu": "hru", "lookup": "GPGv1", "climate": "fixed_048", "land_cover": "esa", "water": "pixel_10", "matrix": "edited", "sub_periods": "lc_soc", "window": "soc_after_cci", "aoi": "asset", "compat": "soc_scale_100", "threshold": "negative"}),
    ("s25", {"sensor": "derived_vi", "index": "ndvi", "trajectory": "ndvi_trend", "lceu": "calculate", "lookup": "GPGv2", "climate": "per_pixel", "land_cover": "custom_full", "water": "pixel_70", "matrix": "default", "sub_periods": "none", "window": "before_cci", "aoi": "geojson", "compat": "clamp_soc_start", "threshold": "zero"}),
    ("s26", {"sensor": "derived_vi", "index": "msvi", "trajectory": "p_res_trend", "lceu": "gaes", "lookup": "GPGv1", "climate": "fixed_080", "land_cover": "custom_half", "water": "asset_band", "matrix": "edited", "sub_periods": "trend_state", "window": "after_cci", "aoi": "asset", "compat": "default", "threshold": "positive"}),
    ("s27", {"sensor": "modis_pair", "index": "ndvi", "trajectory": "ue_trend", "lceu": "aez", "lookup": "GPGv2", "climate": "fixed_048", "land_cover": "custom_full", "water": "pixel_10", "matrix": "default", "sub_periods": "lc_soc", "window": "soc_after_cci", "aoi": "geojson", "compat": "soc_scale_100", "threshold": "negative"}),
    ("s28", {"sensor": "terra_npp", "index": "ndvi", "trajectory": "ndvi_trend", "lceu": "calculate", "lookup": "GPGv1", "climate": "per_pixel", "land_cover": "custom_half", "water": "jrc", "matrix": "edited", "sub_periods": "none", "window": "after_cci", "aoi": "asset", "compat": "clamp_soc_start", "threshold": "zero"}),
)
# fmt: on


def _build(levels: dict[str, str]) -> RunSpec:
    return RunSpec(
        periods=replace(_SUB_PERIODS[levels["sub_periods"]], overall=_WINDOW[levels["window"]]),
        vi_source=_SENSORS[levels["sensor"]],
        vegetation_index=_INDEX[levels["index"]],
        threshold=_THRESHOLD[levels["threshold"]],
        trajectory=_TRAJECTORY[levels["trajectory"]],
        lceu=_LCEU[levels["lceu"]],
        productivity_lookup=_LOOKUP[levels["lookup"]],
        transition_matrix=_MATRIX[levels["matrix"]],
        land_cover=_LAND_COVER[levels["land_cover"]],
        water_mask=_WATER[levels["water"]],
        climate=_CLIMATE[levels["climate"]],
        aoi=_AOI[levels["aoi"]],
        compatibility=_COMPAT[levels["compat"]],
    )


SCENARIOS: dict[str, RunSpec] = {name: _build(levels) for name, levels in _TABLE}
_LEVELS: dict[str, dict[str, str]] = {name: dict(levels) for name, levels in _TABLE}


def axis_levels(name: str) -> dict[str, str]:
    """The axis levels of one scenario, for the coverage test."""
    return dict(_LEVELS[name])
