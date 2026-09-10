"""component/parameter/matrix.py retyped as tuples, plus the label dicts.

Every list in the legacy module is a shared mutable module-level default;
widget/transition_matrix.py:46 index-assigns into one of them, which under Solara
leaks one user's matrix into every other session in the worker (spec §7).
Tuples make that impossible.

No EXPECTED_DIVERGENCES: ``parameter/matrix.py`` and the two ``ui.py`` legend dicts,
retyped as tuples and ``MappingProxyType`` with every value unchanged. Freezing
them fixes the process-wide shared mutable default of ``widget/transition_matrix.py:46``,
which spec §7 records as no divergence: it is unobservable within a single run,
and the widget that wrote into them is not ported.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

__all__ = [
    "CLIMATE_CONVERSION_MATRIX",
    "C_CONVERSION_FACTOR",
    "DEFAULT_LC_CLASS_NAMES",
    "DEFAULT_LC_CODES",
    "DEFAULT_LC_COLORS",
    "DEFAULT_TRANSITION_MATRIX",
    "DEGRADATION_COLORS",
    "DEGRADATION_LABELS",
    "ESA_LC_CLASSES",
    "INPUT_FACTOR",
    "IPCC_TRANSITION_CODES",
    "MANAGEMENT_FACTOR",
    "PROD_PERFORMANCE_LABELS",
    "PROD_STATE_5_LABELS",
    "PROD_TREND_5_LABELS",
    "RECLASSIFICATION_MATRIX",
    "TRANSLATION_MATRIX",
]

# transcribed from parameter/matrix.py:1-17
# rows and columns are forest, grassland, cropland, wetland, artificial,
# bare land, water body
DEFAULT_TRANSITION_MATRIX: tuple[tuple[int, ...], ...] = (
    (0, -1, -1, -1, -1, -1, 0),
    (1, 0, 1, -1, -1, -1, 0),
    (1, -1, 0, -1, -1, -1, 0),
    (-1, -1, -1, 0, -1, -1, 0),
    (1, 1, 1, 1, 0, 1, 0),
    (1, 1, 1, 1, -1, 0, 0),
    (0, 0, 0, 0, 0, 0, 0),
)

# transcribed from parameter/matrix.py:19-28
DEFAULT_LC_CODES: tuple[int, ...] = (10, 20, 30, 40, 50, 60, 70)
DEFAULT_LC_CLASS_NAMES: tuple[str, ...] = (
    "Tree-covered areas",
    "Grassland",
    "Cropland",
    "Wetland",
    "Artificial surfaces",
    "Other land",
    "Water bodies",
)

# transcribed from parameter/ui.py:61-69. The legacy keys are cm.classes.*,
# which are byte-identical to matrix.py's hardcoded English lc_class in the `en`
# catalogue; keying on the same strings is what keeps the Sankey from KeyError-ing
# the day an es/ or fr/ catalogue is added (spec §10).
DEFAULT_LC_COLORS: Mapping[str, str] = MappingProxyType(
    {
        "Tree-covered areas": "#02A000",
        "Grassland": "#FFB432",
        "Cropland": "#FFFF64",
        "Wetland": "#04DC83",
        "Artificial surfaces": "#C31400",
        "Other land": "#FFF5D7",
        "Water bodies": "#0046C8",
    }
)

# transcribed from parameter/matrix.py:30-47; the two misspellings
# ("chnage") are transcribed verbatim, not fixed
DEGRADATION_LABELS: Mapping[int, str] = MappingProxyType(
    {0: "NoData", 1: "Degraded", 2: "Stable", 3: "Improved"}
)

# transcribed from parameter/ui.py:54-59 (pm.legend_bar). Keyed on the values of
# DEGRADATION_LABELS above, not on the translated cm.legend.* strings ui.py used:
# the frame columns and band legends the port keys colours against are the
# untranslated names, and the two lined up only in English (stats/plots.py's
# EXPECTED_DIVERGENCES note 7).
#
# This is the DEGRADATION palette, and it is the domain's only one. Its three
# non-NoData entries are also `legend` (ui.py:48-52), which every viz dict at
# :72-75 spreads for the productivity, land cover, soc and indicator layers -- so
# `tuple(DEGRADATION_COLORS.values())[1:]` is the palette of a {"min": 1, "max": 3}
# visualisation, and the app layer builds those from here rather than retyping the
# hexes (spec §4 bars re-deriving colours in the app layer).
#
# There is deliberately NO palette beside PROD_PERFORMANCE_LABELS. The legacy has
# none: parameter/ui.py defines exactly two colour dicts, and performance -- like
# the 5-level trend and state legends -- was never drawn. Inventing one here would
# be new design in a transcription, and would need its own divergence entry; the
# phase that first renders those layers is the one that gets to choose.
DEGRADATION_COLORS: Mapping[str, str] = MappingProxyType(
    {
        "NoData": "#9ea7ad",
        "Degraded": "#d7191c",
        "Stable": "#ffffbf",
        "Improved": "#2c7bb6",
    }
)
PROD_TREND_5_LABELS: Mapping[int, str] = MappingProxyType(
    {
        0: "NoData",
        1: "Degraded",
        2: "At risk of degrading",
        3: "No significant chnage",
        4: "Potentially improving",
        5: "Improving",
    }
)
PROD_STATE_5_LABELS: Mapping[int, str] = MappingProxyType(
    {
        0: "NoData",
        1: "Degraded",
        2: "At risk of degrading",
        3: "No significant chnage",
        4: "Potentially improving",
        5: "Improving",
    }
)
PROD_PERFORMANCE_LABELS: Mapping[int, str] = MappingProxyType(
    {0: "NoData", 1: "Degraded", 2: "Not degraded"}
)

# transcribed from parameter/matrix.py:49-99.
# `# fmt: off` keeps the seven-per-row shape of the legacy table: without it
# `ruff format` explodes the magic trailing comma to one element per line and
# Task 18's `ruff format --check` fails on a file nobody edited.
# fmt: off
IPCC_TRANSITION_CODES: tuple[int, ...] = (
    1010, 1020, 1030, 1040, 1050, 1060, 1070,
    2010, 2020, 2030, 2040, 2050, 2060, 2070,
    3010, 3020, 3030, 3040, 3050, 3060, 3070,
    4010, 4020, 4030, 4040, 4050, 4060, 4070,
    5010, 5020, 5030, 5040, 5050, 5060, 5070,
    6010, 6020, 6030, 6040, 6050, 6060, 6070,
    7010, 7020, 7030, 7040, 7050, 7060, 7070,
)
# fmt: on

# transcribed from parameter/matrix.py:101-138; paired with RECLASSIFICATION_MATRIX
# at productivity.py:111
# fmt: off
ESA_LC_CLASSES: tuple[int, ...] = (
    10, 11, 12, 20, 30, 40, 50, 60, 61, 62, 70, 71, 72, 80, 81, 82, 90, 100,
    160, 170, 110, 130, 180, 190, 120, 121, 122, 140, 150, 151, 152, 153,
    200, 201, 202, 210,
)
# fmt: on

# transcribed from parameter/matrix.py:140-177
RECLASSIFICATION_MATRIX: tuple[int, ...] = tuple(range(1, 37))

# transcribed from parameter/matrix.py:179-258. Row 0 is the 37 ESA codes,
# row 1 maps them onto the seven IPCC classes {10..70}.
# fmt: off
TRANSLATION_MATRIX: tuple[tuple[int, ...], ...] = (
    (
        10, 11, 12, 20, 30, 40, 50, 60, 61, 62, 70, 71, 72, 80, 81, 82, 90, 100,
        110, 120, 121, 122, 130, 140, 150, 151, 152, 153, 160, 170, 180, 190,
        200, 201, 202, 210, 220,
    ),
    (
        30, 30, 30, 30, 30, 30, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10,
        20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 40, 40, 40, 50,
        60, 60, 60, 70, 60,
    ),
)
# fmt: on

# transcribed from parameter/matrix.py:311-314
CLIMATE_CONVERSION_MATRIX: tuple[tuple[float, ...], ...] = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12),
    (0, 0.69, 0.8, 0.69, 0.8, 0.69, 0.8, 0.69, 0.8, 0.64, 0.48, 0.48, 0.58),
)

# transcribed from parameter/matrix.py:316-366. `1 / 0.71` is written as the
# expression, not its decimal expansion: the float that reaches the encoder must
# be bit-identical for graph parity.
# fmt: off
C_CONVERSION_FACTOR: tuple[float, ...] = (
    1, 1, 333, 1, 0.1, 0.1, 1,
    1, 1, 333, 1, 0.1, 0.1, 1,
    -333, -333, 1, 1 / 0.71, 0.1, 0.1, 1,
    1, 1, 0.71, 1, 0.1, 0.1, 1,
    2, 2, 2, 2, 1, 1, 1,
    2, 2, 2, 2, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1,
)
# fmt: on

# transcribed from parameter/matrix.py:368-418 and :420-470
MANAGEMENT_FACTOR: tuple[int, ...] = (1,) * 49
INPUT_FACTOR: tuple[int, ...] = (1,) * 49
