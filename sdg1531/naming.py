"""Run labels and GEE asset ids.

Pure: no ``ee``, no filesystem, no network. This is the transcription of
``component/model/indicator_model.py:280-312`` (``IndicatorModel.folder_name``),
with the two label defects of spec §7 handled explicitly and nothing else
changed.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from types import MappingProxyType

from .catalog import SENSORS
from .enums import IndicatorLayer
from .spec import (
    CustomLandCoverSource,
    PrecomputedViAsset,
    RunSpec,
    SensorSelection,
)

__all__ = [
    "LAYER_BASENAMES",
    "normalize_str",
    "run_label",
]

# pysepal scripts/utils.py:138 verbatim. anyascii is replaced by an NFKD fold
# so the domain keeps a stdlib-only dependency set; the two agree on the Latin
# text that reaches an AOI name.
_FOLDER_RE = re.compile(r"[^a-zA-Z\d\-_]")
_DISPLAY_RE = re.compile(r"[^a-zA-Z\d\-_ ']")

# spec §8, the "Asset basename" column. Keyed by IndicatorLayer *value*.
LAYER_BASENAMES: Mapping[str, str] = MappingProxyType(
    {
        IndicatorLayer.LAND_COVER.value: "land_cover",
        IndicatorLayer.SOC.value: "soc",
        IndicatorLayer.PRODUCTIVITY.value: "productivity_indicator",
        IndicatorLayer.PRODUCTIVITY_TREND.value: "productivity_trend",
        IndicatorLayer.PRODUCTIVITY_STATE.value: "productivity_state",
        IndicatorLayer.PRODUCTIVITY_PERFORMANCE.value: "productivity_performance",
        IndicatorLayer.INDICATOR_15_3_1.value: "indicator_15_3_1",
    }
)


def normalize_str(msg: str, folder: bool = True) -> str:
    """Make ``msg`` safe for a folder or GEE asset id.

    Args:
        msg: the string to sanitise.
        folder: when False, spaces and apostrophes survive (display form).

    Returns:
        ``msg`` folded to ASCII with every remaining unsafe character replaced
        by ``_``.
    """
    ascii_only = unicodedata.normalize("NFKD", msg).encode("ascii", "ignore").decode()
    regex = _FOLDER_RE if folder else _DISPLAY_RE

    return regex.sub("_", ascii_only)


def _sensor_catalog_token(name: str) -> str:
    """``pm.sensors[name][2]`` — the folder token of one sensor."""
    sensor = SENSORS.get(name)

    return sensor.code if sensor is not None else normalize_str(name).lower()


def _sensor_token(spec: RunSpec) -> str:
    """The ``{sensor}`` slot of the label. indicator_model.py:287-293."""
    source = spec.vi_source
    if not isinstance(source, SensorSelection) or not source.names:
        # :288 index-errors on an empty selection, and the legacy has no
        # counterpart for a precomputed asset at all (spec §7, the doubly-dead
        # "GEE Asset" branch). Both are given a value here so run_label is total.
        return "asset" if isinstance(source, PrecomputedViAsset) else ""

    names = tuple(source.names)
    tokens = tuple(_sensor_catalog_token(name) for name in names)

    if spec.compatibility.legacy_sensor_folder_token:
        # :288 tests for a lowercase "l" in the *display* name, meaning to
        # detect Landsat; of the ten names only "Sentinel 2" has one, so the
        # branch fires for Sentinel alone and yields "l2" (spec §7). :290 then
        # subscripts token[1], which index-errors on a token shorter than two
        # characters; token[1:2] keeps that path total instead.
        if "l" in names[0]:
            return "l" + "".join(token[1:2] for token in tokens)
        return tokens[0]

    # Flag off: detect the Landsat family from the catalog token rather than
    # from the display name, which is what :288-291 meant to do.
    if all(token[:1] == "l" and token[1:].isdigit() for token in tokens):
        return "l" + "".join(token[1:] for token in tokens)

    return tokens[0]


def run_label(spec: RunSpec) -> str:
    """The legacy result-folder name for ``spec``.

    Transcribed from indicator_model.py:280-312. Two departures, both recorded
    in spec §7 and neither touching the ee graph: the climate slot reads the
    climate union's ``.token`` instead of ``int(conversion_coef * 100)`` on a
    None default (:310), and the transition-matrix test compares by value
    instead of comparing the module-level list with itself (:305).
    """
    start = spec.periods.overall.start  # :284
    end = spec.periods.overall.end  # :285
    sensor = _sensor_token(spec)  # :287-293
    vegetation_index = spec.vegetation_index.value  # :296
    lceu = spec.lceu.value  # :302
    custom_matrix = not spec.transition_matrix.is_default()  # :305, fixed
    custom_lc = isinstance(spec.land_cover, CustomLandCoverSource)  # :306
    lc_matrix = "custom" if custom_matrix or custom_lc else "default"  # :307
    climate = spec.climate.token  # :310

    return f"{start}_{end}_{sensor}_{vegetation_index}_{lceu}_{lc_matrix}_{climate}"  # :312
