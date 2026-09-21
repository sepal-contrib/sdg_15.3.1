"""Sensors, asset ids, year bounds and the two scalar helpers.

The value halves of component/parameter/sensor.py, computation.py and ui.py.
ui.py's translated labels and its four viz dicts stay in the app layer.

No EXPECTED_DIVERGENCES: frozen data, retyped with every value unchanged.
``tools/check_transcription.py`` imports the legacy modules and diffs them against
this one directly.

``SensorInfo.first_year``/``last_year`` are the one exception: the legacy carries
no such fields (``parameter/sensor.py:14-33`` has only the four transcribed
above), so there is nothing to diff them against. They are external facts about
the real Earth Engine collections, hand-typed here the way any such roster must
be, and ``tests/test_sensor_bounds.py`` -- a nightly-only ``@pytest.mark.network``
suite -- asks each real collection for its own coverage and asserts these values
still match. See that module's docstring for which sensors are still open
(``last_year=None``) and why.
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
    """One row of parameter/sensor.py:14-33, named, plus its real coverage.

    ``collection_id`` is a pair for "Derived VI Landsat" only: sensor.py:16-24
    stores two ids, and integration.py:66-71 picks between them by index.

    ``first_year``/``last_year`` are not from the legacy (see the module
    docstring): the year of the real collection's first and last image, read
    off ``system:time_start``. ``last_year=None`` means the mission is still
    active and the collection is still gaining images -- not "unknown".
    """

    collection_id: str | tuple[str, str]
    scale: int
    code: str
    level: str
    first_year: int
    last_year: int | None


# transcribed from parameter/sensor.py:14-33. Insertion order is load-bearing:
# the dispatch ladder at integration.py:45-94 makes precedence observable.
#
# `first_year`/`last_year` are read off `system:time_start` on the real collection
# (min and max, verified in tests/test_sensor_bounds.py): the year of the earliest
# and latest image actually in the archive. `last_year=None` marks a mission still
# being ingested -- Landsat 4/5/7 and Terra NPP's MOD17A3HGF are retired archives
# with a real ceiling; every other sensor here is still active.
SENSORS: Mapping[str, SensorInfo] = MappingProxyType(
    {
        "Landsat 4": SensorInfo(
            "LANDSAT/LT04/C02/T1_L2", 30, "l4", "SR", first_year=1982, last_year=1993
        ),
        "Derived VI Landsat": SensorInfo(
            (
                "LANDSAT/COMPOSITES/C02/T1_L2_32DAY_NDVI",
                "LANDSAT/COMPOSITES/C02/T1_L2_32DAY_EVI",
            ),
            30,
            "",
            "VI",
            # A composite over whichever raw Landsat missions are selected upstream
            # (integration.py's own 32-day compositor), not a single archive: both
            # of its two collections start in 1984 and are still being extended
            # today, because Landsat 8/9 keep feeding it.
            first_year=1984,
            last_year=None,
        ),
        "Landsat 5": SensorInfo(
            "LANDSAT/LT05/C02/T1_L2", 30, "l5", "SR", first_year=1984, last_year=2012
        ),
        "Landsat 7": SensorInfo(
            "LANDSAT/LE07/C02/T1_L2", 30, "l7", "SR", first_year=1999, last_year=2024
        ),
        "MODIS MOD13Q1": SensorInfo(
            "MODIS/061/MOD13Q1", 250, "modis", "", first_year=2000, last_year=None
        ),
        # MOD17A3HGF's 006 collection is USGS-deprecated (superseded by 061) and
        # receives no further data -- its own real ceiling, not a stand-in for
        # "still active" the way the other None-less entries are not either.
        "Terra NPP": SensorInfo(
            "MODIS/006/MOD17A3HGF", 250, "modis", "", first_year=2000, last_year=2021
        ),
        "MODIS MYD13Q1": SensorInfo(
            "MODIS/061/MYD13Q1", 250, "modis", "", first_year=2002, last_year=None
        ),
        "Landsat 8": SensorInfo(
            "LANDSAT/LC08/C02/T1_L2", 30, "l8", "SR", first_year=2013, last_year=None
        ),
        "Sentinel 2": SensorInfo(
            "COPERNICUS/S2_SR_HARMONIZED", 10, "s2", "SR", first_year=2015, last_year=None
        ),
        "Landsat 9": SensorInfo(
            "LANDSAT/LC09/C02/T1_L2", 30, "l9", "SR", first_year=2021, last_year=None
        ),
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
