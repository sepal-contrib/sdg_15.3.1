"""Pure payload -> frame decoders. The only pandas/geopandas import in the package.

Nothing here touches ``ee``, the network or the filesystem: every function takes a
plain decoded JSON payload, so each one is testable from a committed fixture.

This module owns half of the STATISTICS vocabulary -- the legend each layer's
classes are named in (:data:`_STATS_LABELS`). The other half, the band each layer
is counted on, lives beside the request that selects it in
``sdg1531/stats/requests.py`` (:data:`~sdg1531.stats.requests._STATS_BAND`); the
two tables are written out in full, at the two sites that use them, and are
deliberately NOT derived from :class:`~sdg1531.engine.indicator.ClassifiedLayer`.
See ``requests.py``'s docstring for why they must be allowed to disagree.

EXPECTED_DIVERGENCES note -- one divergence from the legacy. Task 17's parity
harness must carry it:

1. **Behaviour-changing.** ``zonal_statistics_to_geodataframe``
   (run_15_3_1.py:475-569) prints four progress and failure lines (:485, :543,
   :560, :565, :568), catches every exception at :564 and returns ``None``; its
   caller then raises a generic ``Exception("Failed to compute zonal statistics")``
   at :339-340 with the original traceback already discarded.
   :func:`decode_zonal_areas` raises :class:`~sdg1531.errors.StatisticsError`
   chaining the original instead, and prints nothing. The entry is scoped to error
   REPORTING: on a payload the legacy decoded successfully the two produce the same
   frame, and the four ``if "Class_N" in columns`` guards of :343-350 are ported as
   a total loop that adds the column when it is missing (see
   :func:`decode_zonal_areas`), which changes a KeyError-free omission into a
   zero-filled column and nothing else.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from types import MappingProxyType
from typing import Any

import geopandas as gpd
import pandas as pd

from sdg1531.enums import IndicatorLayer
from sdg1531.errors import StatisticsError
from sdg1531.tables import (
    DEGRADATION_LABELS,
    PROD_PERFORMANCE_LABELS,
    PROD_STATE_5_LABELS,
    PROD_TREND_5_LABELS,
)

__all__ = [
    "decode_areas_by_land_cover",
    "decode_distinct_pixel_values",
    "decode_transition_areas",
    "decode_zonal_areas",
    "pivot_areas_by_land_cover",
]

# transcribed from run_15_3_1.py:425-450 (indicator_n_category_label): which label
# vocabulary each layer's statistics are counted in. Trend and state are counted on
# their 5-level band, so they do not use the degradation labels -- their legends here
# have SIX entries where the export legend has four. That disagreement with
# `ClassifiedLayer.labels` is deliberate; requests.py's docstring states why, and
# tests/test_stats_requests.py fails if either table drifts onto the other.
_STATS_LABELS: Mapping[IndicatorLayer, Mapping[int, str]] = MappingProxyType(
    {
        IndicatorLayer.PRODUCTIVITY: DEGRADATION_LABELS,  # :428-430
        IndicatorLayer.SOC: DEGRADATION_LABELS,  # :431-433
        IndicatorLayer.LAND_COVER: DEGRADATION_LABELS,  # :434-436
        IndicatorLayer.PRODUCTIVITY_STATE: PROD_STATE_5_LABELS,  # :437-439
        IndicatorLayer.PRODUCTIVITY_TREND: PROD_TREND_5_LABELS,  # :440-442
        IndicatorLayer.PRODUCTIVITY_PERFORMANCE: PROD_PERFORMANCE_LABELS,  # :443-445
        IndicatorLayer.INDICATOR_15_3_1: DEGRADATION_LABELS,  # :446-448
    }
)

_ZONAL_DECIMALS = 2  # run_15_3_1.py:333 decimal_places=2, as passed by the caller


def decode_transition_areas(groups: Sequence[Mapping[str, Any]], r: Any) -> pd.DataFrame:
    """Land cover transition areas -> a three column frame.

    Reads ``r.lc_class_combinations``, ``r.scheme``, ``r.lc_year_start_esa`` and
    ``r.lc_year_end_esa``.
    """
    # transcribed from run_15_3_1.py:216-247. The legacy zipped the combination codes
    # against "start_end" strings and split them back apart; the pairs are carried
    # whole here, which removes the split and is otherwise identical. The split was a
    # latent hazard: a class name containing an underscore would have produced three
    # fields and an unpacking error at :243.
    name_pairs = [
        (start_name, end_name)
        for start_name in r.scheme.start_names
        for end_name in r.scheme.end_names
    ]
    # strict=True where the legacy truncated: both sequences are the start x end
    # cartesian product of the same scheme, so a length mismatch means the scheme
    # itself is malformed, not that odd input arrived from Earth Engine.
    labels = dict(zip(r.lc_class_combinations, name_pairs, strict=True))

    rows: list[list[Any]] = []
    for group in groups:
        code = int(group["lc_comb"])
        try:
            start_name, end_name = labels[code]
        except KeyError as exc:
            raise StatisticsError(
                f"Earth Engine returned the transition code {code}, which is not in the "
                "land cover vocabulary of this run."
            ) from exc
        rows.append([start_name, end_name, group["sum"]])

    return pd.DataFrame(data=rows, columns=[r.lc_year_start_esa, r.lc_year_end_esa, "Area"])


def decode_areas_by_land_cover(
    groups: Sequence[Mapping[str, Any]], r: Any, *, layer: IndicatorLayer
) -> pd.DataFrame:
    """Nested (indicator, land cover) groups -> a long frame.

    Reads ``r.scheme``. The class column is named for ``layer.value`` -- the snake
    id -- where the legacy named it for the translated widget string it was called
    with (run_15_3_1.py:297, ``indicator_name``); display strings are the app
    layer's (spec §4).
    """
    # transcribed from run_15_3_1.py:291-297
    labels = _STATS_LABELS[layer]
    code_to_name = r.scheme.code_to_name_start()

    rows: list[list[Any]] = []
    for outer in groups:
        raw_class = outer["indicator"]
        try:
            class_label = labels[int(raw_class)]
        except KeyError as exc:
            raise StatisticsError(
                f"Earth Engine returned class {raw_class!r} for {layer.value}, which has no label."
            ) from exc
        for inner in outer["groups"]:
            code = int(inner["lc"])
            try:
                lc_label = code_to_name[code]
            except KeyError as exc:
                raise StatisticsError(
                    f"Earth Engine returned the land cover code {code}, which is not in "
                    "the land cover vocabulary of this run."
                ) from exc
            rows.append([lc_label, class_label, inner["sum"]])

    return pd.DataFrame(rows, columns=["landcover", layer.value, "Area"])


def pivot_areas_by_land_cover(df: pd.DataFrame, layer: IndicatorLayer) -> pd.DataFrame:
    """Long frame -> land cover x class area matrix, missing cells filled with 0."""
    pivot = df.pivot_table(
        index="landcover",
        columns=layer.value,
        values="Area",
        aggfunc="sum",
        fill_value=0.0,
    )
    pivot.columns.name = None
    return pivot


def decode_zonal_areas(geojson: Any, *, labels: Mapping[int, str]) -> gpd.GeoDataFrame:
    """Zonal FeatureCollection payload -> GeoDataFrame.

    Transcribed from run_15_3_1.py:544-562, with the four prints and the
    ``return None`` at :565-569 replaced by a raise: a caller that gets ``None``
    loses the traceback (:339-340). See the module docstring's EXPECTED_DIVERGENCES
    note 1.
    """
    if not isinstance(geojson, Mapping) or not geojson.get("features"):
        raise StatisticsError(
            "Earth Engine returned no features for the zonal request. Check that the "
            "zones overlap the indicator and that the scale is not too coarse."
        )

    try:
        gdf = gpd.GeoDataFrame.from_features(geojson)
    except Exception as exc:  # re-raised as a domain error, with the cause kept
        raise StatisticsError(f"Could not read the zonal payload: {exc}") from exc

    if gdf.empty:
        raise StatisticsError("The zonal payload decoded to an empty table.")

    gdf = gdf.set_crs("EPSG:4326")

    class_cols = [c for c in gdf.columns if str(c).startswith("Class_")]
    if class_cols:
        gdf[class_cols] = gdf[class_cols].fillna(0).round(_ZONAL_DECIMALS)

    # run_15_3_1.py:343-350 adds the named columns beside the Class_N ones rather
    # than renaming them; kept, so a consumer keyed on either shape still works. The
    # legacy guarded each of the four with `if "Class_N" in columns`, which silently
    # omitted the named column for a class no zone reported; here the raw column is
    # created at 0.0 instead, so the frame's shape does not depend on the data.
    for code, name in labels.items():
        column = f"Class_{code}"
        if column not in gdf.columns:
            gdf[column] = 0.0
        gdf[name] = gdf[column]

    return gdf[gdf.geom_type != "LineString"]


def decode_distinct_pixel_values(values: Iterable[Any] | None) -> tuple[int, ...]:
    """Frequency-histogram keys -> sorted ints (run_15_3_1.py:421-422)."""
    if values is None:
        raise StatisticsError("Earth Engine returned no pixel values for this asset.")
    try:
        return tuple(sorted(int(v) for v in values))
    except (TypeError, ValueError) as exc:
        raise StatisticsError(f"Could not read the pixel values: {exc}") from exc
