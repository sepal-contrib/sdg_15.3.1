"""Closed vocabularies. Values are the legacy strings the science and the JSON
round-trip both carry; the translated display labels stay in the app layer.

Every enum mixes in ``str`` rather than using ``enum.StrEnum``: consumers read
``.value`` everywhere (JSON payloads, GEE parameters, RunSpec fields), and the
``(str, Enum)`` spelling is pinned across tasks — don't "modernize" it.
No EXPECTED_DIVERGENCES: closed vocabularies whose members carry the legacy strings
verbatim. Nothing here decides anything; the translated display labels the legacy
mixed in with them stay in the app layer (spec §4), which is a MOVE, not a change.
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "IndicatorLayer",
    "Lceu",
    "ProductivityLookup",
    "Trajectory",
    "VegetationIndex",
]


class VegetationIndex(str, Enum):  # noqa: UP042
    """transcribed from parameter/ui.py:5-9."""

    NDVI = "ndvi"
    EVI = "evi"
    MSVI = "msvi"


class Trajectory(str, Enum):  # noqa: UP042
    """transcribed from parameter/ui.py:32-37."""

    NDVI_TREND = "ndvi_trend"
    P_RES_TREND = "p_res_trend"
    S_RES_TREND = "s_res_trend"
    UE_TREND = "ue_trend"


class Lceu(str, Enum):  # noqa: UP042
    """Land-cover ecological units. transcribed from parameter/ui.py:11-25."""

    GAES = "gaes"
    AEZ = "aez"
    WTE = "wte"
    HRU = "hru"
    CALCULATE = "calculate"


class ProductivityLookup(str, Enum):  # noqa: UP042
    """transcribed from parameter/ui.py:27-30."""

    GPGV2 = "GPGv2"
    GPGV1 = "GPGv1"


class IndicatorLayer(str, Enum):  # noqa: UP042
    """The seven outputs. transcribed from indicator_model.py:272-278."""

    LAND_COVER = "land_cover"
    SOC = "soc"
    PRODUCTIVITY = "productivity"
    PRODUCTIVITY_TREND = "productivity_trend"
    PRODUCTIVITY_STATE = "productivity_state"
    PRODUCTIVITY_PERFORMANCE = "productivity_performance"
    INDICATOR_15_3_1 = "indicator_15_3_1"
