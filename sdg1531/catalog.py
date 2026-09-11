"""Sensors, asset ids, year bounds and the two scalar helpers.

The value halves of component/parameter/sensor.py, computation.py and ui.py.
ui.py's translated labels and its four viz dicts stay in the app layer.

No EXPECTED_DIVERGENCES: frozen data, retyped with every value unchanged.
``tools/check_transcription.py`` imports the legacy modules and diffs them against
this one directly.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from sdg1531.enums import Trajectory

__all__ = [
    "ASSETS",
    "CLIMATE_COEFFICIENTS",
    "DISABLED_TRAJECTORIES",
    "INT16_MIN",
    "JRC_SEASONALITY_TICKS",
    "L4_START",
    "LAND_COVER_FIRST_YEAR",
    "LAND_COVER_MAX_YEAR",
    "SENSORS",
    "SensorInfo",
    "z_coefficient",
]


@dataclass(frozen=True, slots=True)
class SensorInfo:
    """One row of parameter/sensor.py:14-33, named.

    ``collection_id`` is a pair for "Derived VI Landsat" only: sensor.py:16-24
    stores two ids, and integration.py:66-71 picks between them by index.
    """

    collection_id: str | tuple[str, str]
    scale: int
    code: str
    level: str


# transcribed from parameter/sensor.py:14-33. Insertion order is load-bearing:
# the dispatch ladder at integration.py:45-94 makes precedence observable.
SENSORS: Mapping[str, SensorInfo] = MappingProxyType(
    {
        "Landsat 4": SensorInfo("LANDSAT/LT04/C02/T1_L2", 30, "l4", "SR"),
        "Derived VI Landsat": SensorInfo(
            (
                "LANDSAT/COMPOSITES/C02/T1_L2_32DAY_NDVI",
                "LANDSAT/COMPOSITES/C02/T1_L2_32DAY_EVI",
            ),
            30,
            "",
            "VI",
        ),
        "Landsat 5": SensorInfo("LANDSAT/LT05/C02/T1_L2", 30, "l5", "SR"),
        "Landsat 7": SensorInfo("LANDSAT/LE07/C02/T1_L2", 30, "l7", "SR"),
        "MODIS MOD13Q1": SensorInfo("MODIS/061/MOD13Q1", 250, "modis", ""),
        "Terra NPP": SensorInfo("MODIS/006/MOD17A3HGF", 250, "modis", ""),
        "MODIS MYD13Q1": SensorInfo("MODIS/061/MYD13Q1", 250, "modis", ""),
        "Landsat 8": SensorInfo("LANDSAT/LC08/C02/T1_L2", 30, "l8", "SR"),
        "Sentinel 2": SensorInfo("COPERNICUS/S2_SR_HARMONIZED", 10, "s2", "SR"),
        "Landsat 9": SensorInfo("LANDSAT/LC09/C02/T1_L2", 30, "l9", "SR"),
    }
)

# transcribed from parameter/sensor.py:36-47. `soc_isric` is dropped: zero call
# sites in the whole tree, so it is dead code rather than a behaviour change.
ASSETS: Mapping[str, str] = MappingProxyType(
    {
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
)

# transcribed from parameter/sensor.py:4, 7, 11
L4_START = 1982
LAND_COVER_FIRST_YEAR = 1992
LAND_COVER_MAX_YEAR = 2022

# transcribed from parameter/computation.py:5 — np.iinfo(np.int16).min is a plain
# Python int, so the literal encodes identically and numpy leaves the domain deps.
INT16_MIN = -32768

# transcribed from parameter/ui.py:39
JRC_SEASONALITY_TICKS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)

# transcribed from parameter/ui.py:41-47; the translated labels stay in the app
CLIMATE_COEFFICIENTS: Mapping[str, float] = MappingProxyType(
    {
        "temperate_dry": 0.80,
        "temperate_moist": 0.69,
        "tropical_dry": 0.58,
        "tropical_moist": 0.48,
        "tropical_montane": 0.64,
    }
)

# parameter/ui.py:35 carries "disabled": True, and productivity.py:42-43 raises a
# bare NameError if it is selected anyway. validate() rejects it up front.
DISABLED_TRAJECTORIES: tuple[Trajectory, ...] = (Trajectory.S_RES_TREND,)


def z_coefficient(n: int) -> float:
    """transcribed from parameter/computation.py:8-10."""
    z = (3 * math.sqrt(n * (n - 1))) / (math.sqrt(2 * (2 * n + 5)))
    return z
