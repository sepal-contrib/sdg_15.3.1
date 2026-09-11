"""The payload -> frame decoders, driven entirely from committed fixtures.

No ee, no network: every function under test takes a plain decoded JSON payload.
tests/helpers_stats.py documents where each fixture came from.
"""

import geopandas as gpd
import pytest
from helpers_stats import FakeResolved, load_fixture

from sdg1531.enums import IndicatorLayer
from sdg1531.errors import StatisticsError
from sdg1531.stats.decode import (
    decode_areas_by_land_cover,
    decode_distinct_pixel_values,
    decode_transition_areas,
    decode_zonal_areas,
    pivot_areas_by_land_cover,
)
from sdg1531.tables import (
    DEGRADATION_LABELS,
    PROD_PERFORMANCE_LABELS,
    PROD_STATE_5_LABELS,
    PROD_TREND_5_LABELS,
)


def test_decode_transition_areas_splits_the_combination_code_into_two_columns():
    r = FakeResolved(start_year=2001, end_year=2015)
    groups = load_fixture("transition_areas.json")["groups"]

    df = decode_transition_areas(groups, r)

    assert list(df.columns) == [2001, 2015, "Area"]
    assert len(df) == 5
    # Every row, in payload order and with both halves of the code named. A
    # per-row spot check cannot see a systematic transposition of start and end:
    # 1010/2020/7070 are symmetric, so only the 1030/3010 pair distinguishes
    # `code // 100 -> start` from `code % 100 -> start`.
    names = r.scheme.start_names
    assert [list(row) for row in df.itertuples(index=False)] == [
        [names[0], names[0], 1250.5],  # 1010: first class onto itself
        [names[0], names[2], 40.25],  # 1030: start 10 -> end 30
        [names[1], names[1], 800.0],  # 2020
        [names[2], names[0], 12.75],  # 3010: start 30 -> end 10, the mirror of 1030
        [names[6], names[6], 5.5],  # 7070: last class onto itself
    ]
    assert df["Area"].sum() == pytest.approx(2109.0)


def test_decode_transition_areas_column_labels_follow_the_run_years():
    """The two year columns are the run's own, not the fixture's or a constant."""
    r = FakeResolved(start_year=2004, end_year=2019)
    df = decode_transition_areas([{"lc_comb": 1010, "sum": 1.0}], r)
    assert list(df.columns) == [2004, 2019, "Area"]


def test_decode_transition_areas_rejects_a_code_outside_the_vocabulary():
    r = FakeResolved()
    with pytest.raises(StatisticsError, match=r"transition code 9999"):
        decode_transition_areas([{"lc_comb": 9999, "sum": 1.0}], r)


def test_decode_transition_areas_chains_the_missing_key():
    r = FakeResolved()
    with pytest.raises(StatisticsError) as excinfo:
        decode_transition_areas([{"lc_comb": 9999, "sum": 1.0}], r)
    assert isinstance(excinfo.value.__cause__, KeyError)


@pytest.mark.parametrize("missing", ["lc_comb", "sum"])
def test_decode_transition_areas_names_a_group_entry_missing_a_field(missing):
    """A bare ``KeyError('lc_comb')`` four frames down is an error with no context."""
    entry = {"lc_comb": 1010, "sum": 1.0}
    del entry[missing]

    with pytest.raises(StatisticsError, match=rf"no {missing!r} field") as excinfo:
        decode_transition_areas([entry], FakeResolved())

    assert "land cover transitions" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, KeyError)


def test_decode_transition_areas_names_a_group_entry_that_is_not_a_mapping():
    """A non-mapping entry fails at the subscript, not the lookup -- TypeError."""
    with pytest.raises(StatisticsError, match=r"no 'lc_comb' field") as excinfo:
        decode_transition_areas(["not-a-mapping"], FakeResolved())
    assert isinstance(excinfo.value.__cause__, TypeError)


def test_decode_transition_areas_names_a_non_numeric_transition_code():
    """A malformed VALUE is the same context-free error a malformed key was.

    ``int("not-a-code")`` would otherwise escape as
    ``ValueError: invalid literal for int() with base 10: 'not-a-code'``, which names
    neither the request nor the field.
    """
    with pytest.raises(StatisticsError, match=r"'lc_comb' field is not a number") as excinfo:
        decode_transition_areas([{"lc_comb": "not-a-code", "sum": 1.0}], FakeResolved())

    assert "land cover transitions" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, ValueError)


@pytest.mark.parametrize(
    "payload,field,cause",
    [
        ([{"indicator": "x", "groups": [{"lc": 10, "sum": 1.0}]}], "indicator", ValueError),
        ([{"indicator": 1, "groups": [{"lc": "x", "sum": 1.0}]}], "lc", ValueError),
        # None is not convertible at all, so it fails with TypeError rather than
        # ValueError -- both have to be caught for the guard to be total
        ([{"indicator": None, "groups": [{"lc": 10, "sum": 1.0}]}], "indicator", TypeError),
        ([{"indicator": 1, "groups": [{"lc": None, "sum": 1.0}]}], "lc", TypeError),
    ],
)
def test_decode_areas_by_land_cover_names_a_non_numeric_code(payload, field, cause):
    """Both coerced fields, at both nesting levels, for both failure modes."""
    with pytest.raises(StatisticsError, match=rf"{field!r} field is not a number") as excinfo:
        decode_areas_by_land_cover(payload, FakeResolved(), layer=IndicatorLayer.SOC)

    assert "areas by land cover for soc" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, cause)


def test_decode_areas_by_land_cover_still_accepts_a_numeric_string_class():
    """Coercion, not validation: a class Earth Engine sent as a string still decodes."""
    df = decode_areas_by_land_cover(
        [{"indicator": "1", "groups": [{"lc": "10", "sum": 2.0}]}],
        FakeResolved(),
        layer=IndicatorLayer.SOC,
    )

    assert list(df.itertuples(index=False)) == [("Tree-covered areas", "Degraded", 2.0)]


def test_decode_transition_areas_rejects_a_malformed_scheme():
    """``zip(strict=True)`` where run_15_3_1.py:241 truncated -- a code list and a name
    list of different lengths mislabels every row after the mismatch."""
    r = FakeResolved()
    r.lc_class_combinations = r.lc_class_combinations[:-1]

    with pytest.raises(StatisticsError, match=r"scheme is malformed") as excinfo:
        decode_transition_areas([{"lc_comb": 1010, "sum": 1.0}], r)

    assert "48 transition codes for 49 class-name pairs" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, ValueError)


def test_decode_areas_by_land_cover_flattens_the_nested_groups():
    r = FakeResolved()
    groups = load_fixture("areas_by_land_cover.json")["groups"]

    df = decode_areas_by_land_cover(groups, r, layer=IndicatorLayer.INDICATOR_15_3_1)

    assert list(df.columns) == ["landcover", "indicator_15_3_1", "Area"]
    # Each outer group's inner list contributes one row, in payload order. The
    # payload is ragged (2, 1, 2), so a decoder that zipped the two levels instead
    # of nesting them would produce three rows, not five.
    names = r.scheme.start_names
    assert [list(row) for row in df.itertuples(index=False)] == [
        [names[0], "Degraded", 100.0],
        [names[2], "Degraded", 50.0],
        [names[0], "Stable", 300.0],
        [names[2], "Improved", 25.0],
        [names[6], "Improved", 5.0],
    ]
    assert df["Area"].sum() == pytest.approx(480.0)


def test_decode_areas_by_land_cover_uses_the_five_class_labels_for_productivity_state():
    """run_15_3_1.py:437-439 counts state in pm.prod_state_5_class, not degradation_class."""
    r = FakeResolved()
    groups = [{"indicator": 4, "groups": [{"lc": 10, "sum": 3.0}]}]

    df = decode_areas_by_land_cover(groups, r, layer=IndicatorLayer.PRODUCTIVITY_STATE)

    assert list(df.columns) == ["landcover", "productivity_state", "Area"]
    assert df.iloc[0]["productivity_state"] == PROD_STATE_5_LABELS[4]
    assert df.iloc[0]["productivity_state"] == "Potentially improving"
    # class 4 exists ONLY in the 5-class vocabularies, so this row is unreachable
    # under the degradation legend -- which is what makes the assertion above proof
    # that the state layer is not sharing DEGRADATION_LABELS.
    assert 4 not in DEGRADATION_LABELS
    with pytest.raises(StatisticsError, match=r"class 4 for indicator_15_3_1"):
        decode_areas_by_land_cover(groups, r, layer=IndicatorLayer.INDICATOR_15_3_1)


def test_decode_areas_by_land_cover_uses_the_five_class_labels_for_productivity_trend():
    """run_15_3_1.py:440-442 counts trend in pm.prod_trend_5_class."""
    r = FakeResolved()
    groups = [{"indicator": 5, "groups": [{"lc": 10, "sum": 3.0}]}]

    df = decode_areas_by_land_cover(groups, r, layer=IndicatorLayer.PRODUCTIVITY_TREND)

    assert df.iloc[0]["productivity_trend"] == PROD_TREND_5_LABELS[5]
    assert df.iloc[0]["productivity_trend"] == "Improving"
    assert 5 not in DEGRADATION_LABELS


def test_decode_areas_by_land_cover_uses_the_performance_labels_for_performance():
    """run_15_3_1.py:443-445 counts performance in pm.prod_performance_class."""
    r = FakeResolved()
    groups = [{"indicator": 2, "groups": [{"lc": 10, "sum": 3.0}]}]

    df = decode_areas_by_land_cover(groups, r, layer=IndicatorLayer.PRODUCTIVITY_PERFORMANCE)

    assert df.iloc[0]["productivity_performance"] == PROD_PERFORMANCE_LABELS[2]
    assert df.iloc[0]["productivity_performance"] == "Not degraded"
    # the same code means something different under the degradation legend, which is
    # why performance may not share it
    assert DEGRADATION_LABELS[2] == "Stable"


def test_decode_areas_by_land_cover_rejects_an_unlabelled_class():
    r = FakeResolved()
    with pytest.raises(StatisticsError, match=r"class 9 for soc"):
        decode_areas_by_land_cover(
            [{"indicator": 9, "groups": [{"lc": 10, "sum": 1.0}]}],
            r,
            layer=IndicatorLayer.SOC,
        )


def test_decode_areas_by_land_cover_rejects_an_unknown_land_cover_code():
    r = FakeResolved()
    with pytest.raises(StatisticsError, match=r"land cover code 99"):
        decode_areas_by_land_cover(
            [{"indicator": 1, "groups": [{"lc": 99, "sum": 1.0}]}],
            r,
            layer=IndicatorLayer.SOC,
        )


@pytest.mark.parametrize(
    "payload,missing",
    [
        ([{"groups": [{"lc": 10, "sum": 1.0}]}], "indicator"),
        ([{"indicator": 1}], "groups"),
        ([{"indicator": 1, "groups": [{"sum": 1.0}]}], "lc"),
        ([{"indicator": 1, "groups": [{"lc": 10}]}], "sum"),
    ],
)
def test_decode_areas_by_land_cover_names_a_group_entry_missing_a_field(payload, missing):
    """All four fields the nested payload is read by, guarded at both levels."""
    with pytest.raises(StatisticsError, match=rf"no {missing!r} field") as excinfo:
        decode_areas_by_land_cover(payload, FakeResolved(), layer=IndicatorLayer.SOC)

    assert "areas by land cover for soc" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, KeyError)


def test_pivot_areas_by_land_cover_sums_into_a_class_matrix():
    r = FakeResolved()
    groups = load_fixture("areas_by_land_cover.json")["groups"]
    df = decode_areas_by_land_cover(groups, r, layer=IndicatorLayer.INDICATOR_15_3_1)

    pivot = pivot_areas_by_land_cover(df, IndicatorLayer.INDICATOR_15_3_1)

    assert pivot.index.name == "landcover"
    assert pivot.columns.name is None
    names = r.scheme.start_names
    assert pivot.loc[names[0], "Degraded"] == 100.0
    assert pivot.loc[names[0], "Stable"] == 300.0
    # this land cover class has no improved area at all: filled, not missing
    assert pivot.loc[names[0], "Improved"] == 0.0
    # the whole matrix, so a fill that leaked into an occupied cell is visible too
    assert pivot.to_dict() == {
        "Degraded": {names[0]: 100.0, names[2]: 50.0, names[6]: 0.0},
        "Improved": {names[0]: 0.0, names[2]: 25.0, names[6]: 5.0},
        "Stable": {names[0]: 300.0, names[2]: 0.0, names[6]: 0.0},
    }


def test_pivot_areas_by_land_cover_sums_repeated_cells():
    """A land cover class can appear under the same indicator class twice."""
    r = FakeResolved()
    df = decode_areas_by_land_cover(
        [
            {"indicator": 1, "groups": [{"lc": 10, "sum": 2.0}]},
            {"indicator": 1, "groups": [{"lc": 10, "sum": 3.0}]},
        ],
        r,
        layer=IndicatorLayer.SOC,
    )

    pivot = pivot_areas_by_land_cover(df, IndicatorLayer.SOC)

    assert pivot.loc[r.scheme.start_names[0], "Degraded"] == 5.0


def test_decode_zonal_areas_labels_classes_drops_lines_and_rounds():
    geojson = load_fixture("zonal_features.json")
    labels = {0: "NoData", 1: "Degrade", 2: "Stable", 3: "Improve"}

    gdf = decode_zonal_areas(geojson, labels=labels)

    assert isinstance(gdf, gpd.GeoDataFrame)
    assert gdf.crs == "EPSG:4326"
    assert len(gdf) == 2  # the LineString is gone
    assert "LineString" not in set(gdf.geom_type)
    assert set(gdf["name"]) == {"zone-a", "zone-b"}
    assert gdf.iloc[0]["NoData"] == 1.23  # rounded to 2 decimals
    assert gdf.iloc[0]["Improve"] == 2.0
    assert gdf.iloc[1]["Class_3"] == 0.0  # missing class filled with 0
    assert gdf.iloc[1]["Improve"] == 0.0
    assert "Class_0" in gdf.columns  # the raw columns survive alongside the labels
    # every label lands on its own class, so a table applied off by one is visible
    assert [gdf.iloc[0][name] for name in ("NoData", "Degrade", "Stable", "Improve")] == [
        1.23,
        10.5,
        20.25,
        2.0,
    ]


def test_decode_zonal_areas_adds_a_column_for_a_class_no_zone_reported():
    """A class absent from every feature still gets a column, filled with 0."""
    geojson = load_fixture("zonal_features.json")

    gdf = decode_zonal_areas(geojson, labels={4: "Extra"})

    assert "Class_4" in gdf.columns
    assert list(gdf["Extra"]) == [0.0, 0.0]


def test_decode_zonal_areas_adds_the_label_columns_in_table_order():
    """The named columns land in ``labels`` iteration order, not sorted by code.

    That is the mechanism which makes ``_ZONAL_LABELS``' own (legacy) order the field
    order of the shapefile the export writes, so it is pinned here independently of that
    table's contents.
    """
    geojson = load_fixture("zonal_features.json")

    gdf = decode_zonal_areas(geojson, labels={3: "Improve", 0: "NoData", 1: "Degrade"})

    named = [c for c in gdf.columns if c in {"Improve", "NoData", "Degrade"}]
    assert named == ["Improve", "NoData", "Degrade"]


def test_decode_zonal_areas_without_labels_keeps_the_raw_class_columns():
    geojson = load_fixture("zonal_features.json")

    gdf = decode_zonal_areas(geojson, labels={})

    assert {"Class_0", "Class_1", "Class_2", "Class_3"} <= set(gdf.columns)
    assert gdf.iloc[0]["Class_0"] == 1.23


def test_empty_payload_raises_statistics_error():
    with pytest.raises(StatisticsError, match=r"no features"):
        decode_zonal_areas({"type": "FeatureCollection", "features": []}, labels={})
    with pytest.raises(StatisticsError, match=r"no features"):
        decode_zonal_areas({}, labels={})


def test_decode_zonal_areas_chains_the_original_error():
    with pytest.raises(StatisticsError, match=r"Could not read the zonal payload") as excinfo:
        decode_zonal_areas({"features": [{"no": "geometry"}]}, labels={})
    assert excinfo.value.__cause__ is not None


def test_decode_distinct_pixel_values_returns_sorted_ints():
    assert decode_distinct_pixel_values(["30", "10", "20"]) == (10, 20, 30)
    with pytest.raises(StatisticsError, match=r"no pixel values"):
        decode_distinct_pixel_values(None)


def test_decode_distinct_pixel_values_rejects_a_non_numeric_key():
    with pytest.raises(StatisticsError, match=r"Could not read the pixel values") as excinfo:
        decode_distinct_pixel_values(["10", "not-a-number"])
    assert isinstance(excinfo.value.__cause__, ValueError)
