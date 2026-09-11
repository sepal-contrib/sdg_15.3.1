"""Run labels and GEE asset ids.

Pure: no ``ee``, no filesystem, no network. This is the transcription of
``component/model/indicator_model.py:280-312`` (``IndicatorModel.folder_name``),
with its two label defects handled explicitly and nothing else changed.

EXPECTED_DIVERGENCES note -- one divergence from the legacy. The parity harness
must carry it:

1. **Behaviour-changing, scoped to the LABEL.** :func:`run_label` is total where
   ``folder_name()`` raised. indicator_model.py:310 is
   ``climate = f"cr{int(self.conversion_coef*100)}"``, ``conversion_coef`` defaults
   to ``None``, and the default regime is per-pixel -- so the legacy's own default
   path raised ``TypeError`` at input_tile.py:336, before anything was computed.
   ``PerPixelClimate`` carries the token ``crpix`` instead, and a non-finite
   coefficient gets a token rather than an exception. The label names the result
   DIRECTORY (run_15_3_1.py:313-317 globs it to find an existing run), so this
   changes a string and never a graph; the third label defect on this path,
   ``"l" in self.sensors[0]``, is PRESERVED behind
   ``Compatibility.legacy_sensor_folder_token`` and is not part of this entry.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from types import MappingProxyType

from anyascii import anyascii

from sdg1531.catalog import SENSORS
from sdg1531.enums import IndicatorLayer
from sdg1531.spec import (
    Climate,
    CustomLandCoverSource,
    FixedClimate,
    PrecomputedViAsset,
    RunSpec,
    SensorSelection,
)

__all__ = [
    "LAYER_BASENAMES",
    "asset_path",
    "layer_basenames",
    "normalize_str",
    "run_id",
    "run_label",
]

_FOLDER_RE = re.compile(r"[^a-zA-Z\d\-_]")
_DISPLAY_RE = re.compile(r"[^a-zA-Z\d\-_ ']")

# The asset basename of each layer. Keyed by IndicatorLayer *value*.
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

    Transcribed from ``pysepal`` ``scripts/utils.py:128-140`` verbatim
    (``re.sub(regex, "_", anyascii(msg))``): ``anyascii`` *transliterates*
    rather than strips, so e.g. "Ørsted" becomes "Orsted" and "Кавказ"
    becomes "Kavkaz" instead of both losing their non-Latin letters. That
    matters here because the AOI name it sanitises is user-supplied and
    ends up in ``run_label``, which names a directory users already have on
    disk (``run_15_3_1.py:313-317`` globs on it) — a divergent transliteration
    would orphan an existing user's results.

    Args:
        msg: the string to sanitise.
        folder: when False, spaces and apostrophes survive (display form).

    Returns:
        ``msg`` folded to ASCII with every remaining unsafe character replaced
        by ``_``.
    """
    regex = _FOLDER_RE if folder else _DISPLAY_RE

    return regex.sub("_", anyascii(msg))


def _sensor_catalog_token(name: str) -> str:
    """``pm.sensors[name][2]`` — the folder token of one sensor."""
    sensor = SENSORS.get(name)

    return sensor.code if sensor is not None else normalize_str(name).lower()


def _sensor_token(spec: RunSpec) -> str:
    """The ``{sensor}`` slot of the label. indicator_model.py:287-293."""
    source = spec.vi_source
    if not isinstance(source, SensorSelection) or not source.names:
        # :288 index-errors on an empty selection, and the legacy has no
        # counterpart for a precomputed asset at all -- its "GEE Asset" branch was
        # doubly dead. Both are given a value here so run_label is total.
        return "asset" if isinstance(source, PrecomputedViAsset) else ""

    names = tuple(source.names)
    tokens = tuple(_sensor_catalog_token(name) for name in names)

    if spec.compatibility.legacy_sensor_folder_token:
        # :288 tests for a lowercase "l" in the *display* name, meaning to
        # detect Landsat; of the ten names only "Sentinel 2" has one, so the
        # branch fires for Sentinel alone and yields "l2". :290 then subscripts
        # token[1], which index-errors on a token shorter than two characters;
        # token[1:2] keeps that path total instead.
        if "l" in names[0]:
            return "l" + "".join(token[1:2] for token in tokens)
        return tokens[0]

    # Flag off: detect the Landsat family from the catalog token rather than
    # from the display name, which is what :288-291 meant to do.
    if all(token[:1] == "l" and token[1:].isdigit() for token in tokens):
        return "l" + "".join(token[1:] for token in tokens)

    return tokens[0]


def _climate_token(climate: Climate) -> str:
    """The ``{climate}`` slot of the label. indicator_model.py:310.

    ``FixedClimate.token`` truncates ``coefficient`` with ``int()``, faithfully
    inheriting the legacy's crash on a non-finite value: ``nan`` raises
    ``ValueError``, ``inf``/``-inf`` raises ``OverflowError``. Neither is
    reachable from the UI (parameter/ui.py:41-47's five fixed values, or the
    custom slider's bounded range), but ``run_label`` must be total over the
    whole ``RunSpec`` space regardless. The three sentinel tokens below all
    contain a letter, so none collides with ``f"cr{int(coefficient * 100)}"``
    for any finite coefficient, whose digits are the only thing that varies.
    """
    if isinstance(climate, FixedClimate):
        coefficient = climate.coefficient
        if math.isnan(coefficient):
            return "crnan"
        if math.isinf(coefficient):
            return "crposinf" if coefficient > 0 else "crneginf"

    return climate.token


def run_label(spec: RunSpec) -> str:
    """The legacy result-folder name for ``spec``.

    Transcribed from indicator_model.py:280-312. Two deliberate departures, neither
    touching the ee graph: the climate slot reads the climate union's ``.token``
    instead of ``int(conversion_coef * 100)`` on a None default (:310) — with
    ``nan``/``inf`` also guarded, see
    :func:`_climate_token` — and the transition-matrix test compares by value
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
    climate = _climate_token(spec.climate)  # :310, total

    return f"{start}_{end}_{sensor}_{vegetation_index}_{lceu}_{lc_matrix}_{climate}"  # :312


def run_id(spec: RunSpec) -> str:
    """``run_label`` scrubbed to the character set a GEE asset id accepts."""
    return normalize_str(run_label(spec))


def layer_basenames(spec: RunSpec) -> dict[str, str]:
    """The asset basename of each of the seven layers, keyed by layer id.

    Takes the spec so call sites stay stable if a basename ever has to vary
    per run; the table is currently constant.
    """
    del spec

    return dict(LAYER_BASENAMES)


def asset_path(
    root: str,
    spec: RunSpec,
    layer: IndicatorLayer | str,
    taken: Iterable[str] = (),
) -> str:
    """The GEE asset id for one layer of one run, avoiding ids already in use.

    ``root`` is the destination folder, ``taken`` the ids the caller already
    knows about; a collision appends ``_1``, ``_2``, ... to the *id*, never to
    the layer basename.

    Re-running with identical parameters produces an identical run label, so
    without this every re-run collides. This **reduces** collisions rather than
    removing them: ``taken`` only covers what the caller listed, two AOIs share
    a label under one root, and the user can still edit the id in the export
    dialog. The stock pysepal engine raises ``FileExistsError``
    (``export_engine.py:327-332``) instead of suffixing, so a collision that
    slips through still fails loudly at submit time.
    """
    basename = layer_basenames(spec)[IndicatorLayer(layer).value]
    prefix = root.rstrip("/")
    stem = f"{run_id(spec)}_{basename}"
    used = {str(identifier) for identifier in taken}

    candidate = f"{prefix}/{stem}"
    suffix = 1
    while candidate in used:
        candidate = f"{prefix}/{stem}_{suffix}"
        suffix += 1

    return candidate
