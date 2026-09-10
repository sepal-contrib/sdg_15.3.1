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

EXPECTED_DIVERGENCES note -- four divergences from the legacy. Task 17's parity
harness must carry all four:

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
   zero-filled column and nothing else. It also covers one input the legacy did
   NOT treat as an error: ``{"features": []}`` passed ``:546``'s guard (the key is
   present) and decoded to an empty frame, which then failed further downstream at
   ``to_file``; :func:`decode_zonal_areas` raises on it, naming the likely cause.
   That makes the entry deliberately wider than "reporting only" by exactly one
   input shape.
2. **Behaviour-changing.** :func:`decode_distinct_pixel_values` returns the values
   SORTED; ``custom_lc_values`` (run_15_3_1.py:421-422) returned them in the
   frequency histogram's own key order. The entry is the ORDER and nothing else --
   the same integers, the same count. Every legacy consumer wrapped the result in
   ``set()`` (input_tile.py:271, :273, :286, :291), so no shipped behaviour depended
   on the order; sorting makes the value deterministic for a caller that does not.
3. **Behaviour-changing.** :func:`decode_transition_areas` zips the transition codes
   against the class-name pairs with ``strict=True`` and raises where
   ``run_15_3_1.py:241``'s bare ``zip`` truncated to the shorter of the two. Scoped
   to a scheme whose code list and name list disagree in length -- which cannot
   happen for a scheme built by :mod:`sdg1531.scheme` and means the scheme itself is
   malformed, not that odd input arrived from Earth Engine. For every well-formed
   scheme the two are identical. Truncating instead produced a silently
   MISLABELLED table, which is the failure mode worth trading a raise for.
4. **Behaviour-changing, scoped to one COLUMN NAME** -- the class column is
   ``layer.value`` (the snake id) where ``run_15_3_1.py:297`` used the translated
   ``indicator_name``; no value, row or ordering differs.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    # Typing only, and `sdg1531.resolve` is on the ee-free JSON half anyway
    # (tests/test_isolation.py), so this stays true even at runtime.
    from sdg1531.resolve import ResolvedSpec

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


def _field(entry: Any, key: str, *, what: str) -> Any:
    """One field off a group entry, naming the payload when it is absent.

    The unknown-*code* paths below already raise a domain error; the missing-*key*
    paths used to surface as a bare ``KeyError('lc_comb')`` from four frames down,
    which is a milder form of the same "error with no context" that spec §7's fix is
    about. ``TypeError`` is caught alongside because a group entry that is not a
    mapping at all (a bare string, say) fails at the subscript rather than the lookup.
    """
    try:
        return entry[key]
    except (KeyError, TypeError) as exc:
        raise StatisticsError(
            f"Earth Engine returned a {what} entry with no {key!r} field: {entry!r}"
        ) from exc


def _int_field(entry: Any, key: str, *, what: str) -> int:
    """A class code off a group entry, with both of its failure modes named.

    :func:`_field` covers an absent key; this covers a value that is not a number.
    ``int("abc")`` raises ``ValueError: invalid literal for int() with base 10:
    'abc'`` four frames down, which is the same context-free error the missing-key
    guard exists to prevent -- closing one half of that class and leaving the other
    open would be worse than closing neither. ``TypeError`` is caught alongside for
    a value that is not convertible at all, such as ``None``.
    """
    value = _field(entry, key, what=what)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise StatisticsError(
            f"Earth Engine returned a {what} entry whose {key!r} field is not a number: {value!r}"
        ) from exc


def decode_transition_areas(groups: Sequence[Mapping[str, Any]], r: ResolvedSpec) -> pd.DataFrame:
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
    # itself is malformed, not that odd input arrived from Earth Engine. See the
    # module docstring's EXPECTED_DIVERGENCES note 3.
    try:
        labels = dict(zip(r.lc_class_combinations, name_pairs, strict=True))
    except ValueError as exc:
        raise StatisticsError(
            f"This run's land cover scheme is malformed: {len(r.lc_class_combinations)} "
            f"transition codes for {len(name_pairs)} class-name pairs."
        ) from exc

    rows: list[list[Any]] = []
    for group in groups:
        code = _int_field(group, "lc_comb", what="land cover transitions")
        try:
            start_name, end_name = labels[code]
        except KeyError as exc:
            raise StatisticsError(
                f"Earth Engine returned the transition code {code}, which is not in the "
                "land cover vocabulary of this run."
            ) from exc
        rows.append([start_name, end_name, _field(group, "sum", what="land cover transitions")])

    return pd.DataFrame(data=rows, columns=[r.lc_year_start_esa, r.lc_year_end_esa, "Area"])


def decode_areas_by_land_cover(
    groups: Sequence[Mapping[str, Any]], r: ResolvedSpec, *, layer: IndicatorLayer
) -> pd.DataFrame:
    """Nested (indicator, land cover) groups -> a long frame.

    Reads ``r.scheme``. The class column is named for ``layer.value`` -- the snake
    id -- where the legacy named it for the translated widget string it was called
    with (run_15_3_1.py:297, ``indicator_name``); display strings are the app
    layer's (spec §4). See the module docstring's EXPECTED_DIVERGENCES note 4.
    """
    # transcribed from run_15_3_1.py:291-297
    labels = _STATS_LABELS[layer]
    code_to_name = r.scheme.code_to_name_start()

    what = f"areas by land cover for {layer.value}"
    rows: list[list[Any]] = []
    for outer in groups:
        class_code = _int_field(outer, "indicator", what=what)
        try:
            class_label = labels[class_code]
        except KeyError as exc:
            raise StatisticsError(
                f"Earth Engine returned class {class_code} for {layer.value}, which has no label."
            ) from exc
        for inner in _field(outer, "groups", what=what):
            code = _int_field(inner, "lc", what=what)
            try:
                lc_label = code_to_name[code]
            except KeyError as exc:
                raise StatisticsError(
                    f"Earth Engine returned the land cover code {code}, which is not in "
                    "the land cover vocabulary of this run."
                ) from exc
            rows.append([lc_label, class_label, _field(inner, "sum", what=what)])

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
