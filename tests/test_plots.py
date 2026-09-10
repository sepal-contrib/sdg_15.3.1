"""Chart options are plain, JSON-serialisable dicts. No ipecharts, no matplotlib.

The option dict is the whole deliverable: the app layer hands it to
``ipecharts.echarts.EChartsRawWidget``, whose ``option`` trait is a bare
``traitlets.Dict`` (ipecharts/echarts.py:11-14), so nothing between this module and
the browser inspects it. ``json.dumps`` proves only that a dict is *serialisable* --
an invented series type, a link naming a node nothing declares, or a repeated node
name all survive it and then render an empty canvas. Those are asserted here
directly, against the legacy chart each option replaces (component/scripts/sankey.py
:15-235, component/scripts/bar_plot.py:1-26) and against the option keys ipecharts
itself declares.
"""

import json

import pandas as pd
import pytest
from helpers_stats import FakeResolved, load_fixture

from sdg1531.enums import IndicatorLayer
from sdg1531.scheme import LandCoverScheme, TransitionMatrix
from sdg1531.stats.decode import (
    decode_areas_by_land_cover,
    decode_transition_areas,
    pivot_areas_by_land_cover,
)
from sdg1531.stats.plots import distribution_option, sankey_option

# Transcribed from the ipecharts 1.0.x sources, which are generated from the ECharts
# option schema: every trait name declared on ``Option`` (ipecharts/option/option.py
# :93-266), on ``Sankey`` (ipecharts/option/seriesitems/sankey.py:44-300) and on ``Bar``
# (ipecharts/option/seriesitems/bar.py:31-520). ipecharts may not be imported from this
# repo at all (tests/test_isolation.py:20), so the rosters are copied rather than read
# off the package; their one job is to fail a key ECharts has never heard of.
OPTION_KEYS = frozenset(
    {
        "angleAxis", "animation", "animationDelay", "animationDelayUpdate",
        "animationDuration", "animationDurationUpdate", "animationEasing",
        "animationEasingUpdate", "animationThreshold", "aria", "axisPointer",
        "backgroundColor", "blendMode", "brush", "calendar", "color", "darkMode",
        "dataZoom", "dataset", "geo", "geo3D", "globe", "graphic", "grid", "grid3D",
        "hoverLayerThreshold", "legend", "mapbox3D", "media", "options", "parallel",
        "parallelAxis", "polar", "radar", "radiusAxis", "series", "singleAxis",
        "stateAnimation", "textStyle", "timeline", "title", "toolbox", "tooltip",
        "useUTC", "visualMap", "xAxis", "xAxis3D", "yAxis", "yAxis3D", "zAxis3D",
    }
)  # fmt: skip
SANKEY_SERIES_KEYS = frozenset(
    {
        "animation", "animationDelay", "animationDelayUpdate", "animationDuration",
        "animationDurationUpdate", "animationEasing", "animationEasingUpdate",
        "animationThreshold", "blur", "bottom", "data", "draggable", "edgeLabel",
        "edges", "emphasis", "height", "id", "itemStyle", "label", "labelLayout",
        "layoutIterations", "left", "levels", "lineStyle", "links", "name",
        "nodeAlign", "nodeGap", "nodeWidth", "nodes", "orient", "right", "select",
        "selectedMode", "silent", "tooltip", "top", "type", "width", "z", "zlevel",
    }
)  # fmt: skip
BAR_SERIES_KEYS = frozenset(
    {
        "animation", "animationDelay", "animationDelayUpdate", "animationDuration",
        "animationDurationUpdate", "animationEasing", "animationEasingUpdate",
        "animationThreshold", "backgroundStyle", "barCategoryGap", "barGap",
        "barMaxWidth", "barMinAngle", "barMinHeight", "barMinWidth", "barWidth", "blur",
        "clip", "colorBy", "coordinateSystem", "cursor", "data", "dataGroupId",
        "datasetIndex", "dimensions", "emphasis", "encode", "id", "itemStyle", "label",
        "labelLayout", "labelLine", "large", "largeThreshold", "legendHoverLink",
        "markArea", "markLine", "markPoint", "name", "polarIndex", "progressive",
        "progressiveChunkMode", "progressiveThreshold", "realtimeSort", "roundCap",
        "sampling", "select", "selectedMode", "seriesLayoutBy", "showBackground",
        "silent", "stack", "stackStrategy", "tooltip", "type", "universalTransition",
        "xAxisIndex", "yAxisIndex", "z", "zlevel",
    }
)  # fmt: skip

_JSON_SCALARS = (str, bool, int, float, type(None))


def assert_plain_json(value, path="option"):
    """Every leaf is EXACTLY a builtin scalar, by type identity rather than isinstance.

    ``isinstance`` cannot do this job: ``numpy.float64`` subclasses ``float``, so a
    numpy float passes both ``isinstance(v, float)`` and ``json.dumps`` (verified on
    numpy 2.5.2 -- ``json.dumps(np.float64(1.5))`` returns ``"1.5"``). Only
    ``type(v) is float`` sees it. ``numpy.int64`` and ``numpy.float32`` do not
    subclass their builtins, and ``json.dumps`` rejects those two; this walk closes
    the ``float64`` half that json alone leaves open.

    Containers must be ``dict``/``list`` for the same reason: ``json.dumps`` accepts a
    tuple and an int dict key by silently rewriting them, so neither shows up as an
    error at the boundary this function stands in for.
    """
    if isinstance(value, dict):
        for key, item in value.items():
            assert type(key) is str, f"{path}: key {key!r} is {type(key).__name__}, not str"
            assert_plain_json(item, f"{path}[{key!r}]")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_plain_json(item, f"{path}[{index}]")
    else:
        assert type(value) in _JSON_SCALARS, f"{path} is a {type(value).__name__}: {value!r}"


def transitions(r):
    forest, grass, crop = r.scheme.start_names[0], r.scheme.start_names[1], r.scheme.start_names[2]
    return pd.DataFrame(
        [
            [forest, forest, 100.0],
            [forest, crop, 25.0],
            [grass, grass, 50.0],
            [crop, forest, 5.0],
        ],
        columns=[r.lc_year_start_esa, r.lc_year_end_esa, "Area"],
    )


def decoded_transitions(r):
    """The real Task 15 output for the same chart, straight off the committed fixture.

    ``transitions`` above is hand-built and could agree with a wrong assumption about
    the frame's shape; this one cannot -- ``decode_transition_areas`` names its columns
    and orders them itself (sdg1531/stats/decode.py:176).
    """
    return decode_transition_areas(load_fixture("transition_areas.json")["groups"], r)


def decoded_pivot(r):
    """The real Task 15 pivot the distribution chart consumes."""
    df = decode_areas_by_land_cover(
        load_fixture("areas_by_land_cover.json")["groups"],
        r,
        layer=IndicatorLayer.INDICATOR_15_3_1,
    )
    return pivot_areas_by_land_cover(df, IndicatorLayer.INDICATOR_15_3_1)


# --- sankey -----------------------------------------------------------------


def test_sankey_nodes_carry_the_year_so_echarts_cannot_merge_them():
    r = FakeResolved(start_year=2001, end_year=2015)
    option = sankey_option(transitions(r), r)

    names = [node["name"] for node in option["series"][0]["data"]]
    forest = r.scheme.start_names[0]
    assert f"{forest} 2001" in names
    assert f"{forest} 2015" in names
    assert names.count(f"{forest} 2001") == 1


def test_sankey_has_no_self_loop_for_an_unchanged_class():
    r = FakeResolved(start_year=2001, end_year=2015)
    option = sankey_option(transitions(r), r)

    for link in option["series"][0]["links"]:
        assert link["source"] != link["target"]


def test_sankey_ribbons_take_their_left_class_colour():
    r = FakeResolved()
    option = sankey_option(transitions(r), r)

    assert option["series"][0]["lineStyle"] == {"color": "source", "curveness": 0.5}
    forest = r.scheme.start_names[0]
    node = next(
        n for n in option["series"][0]["data"] if n["name"] == f"{forest} {r.lc_year_start_esa}"
    )
    assert node["itemStyle"]["color"] == r.lc_color_by_class[forest]


def test_sankey_link_values_are_plain_floats_and_conserve_area():
    r = FakeResolved()
    df = transitions(r)
    option = sankey_option(df, r)

    links = option["series"][0]["links"]
    assert all(type(link["value"]) is float for link in links)
    assert sum(link["value"] for link in links) == pytest.approx(df["Area"].sum())
    json.dumps(option)  # must be plain JSON, no numpy scalars


def test_sankey_aggregates_duplicate_pairs():
    r = FakeResolved()
    forest = r.scheme.start_names[0]
    df = pd.DataFrame(
        [[forest, forest, 1.0], [forest, forest, 2.0]],
        columns=[r.lc_year_start_esa, r.lc_year_end_esa, "Area"],
    )
    option = sankey_option(df, r)
    assert len(option["series"][0]["links"]) == 1
    assert option["series"][0]["links"][0]["value"] == 3.0


def test_sankey_is_one_series_declared_as_a_sankey():
    """``series[0]["type"]`` is what makes ECharts draw a sankey at all.

    ipecharts' ``Sankey`` defaults ``type`` to ``"sankey"`` (seriesitems/sankey.py:44),
    but ``EChartsRawWidget`` never constructs one -- it forwards the dict, so the type
    has to be in the dict.
    """
    r = FakeResolved()
    option = sankey_option(decoded_transitions(r), r)

    assert isinstance(option["series"], list)
    assert len(option["series"]) == 1
    series = option["series"][0]
    assert series["type"] == "sankey"
    assert isinstance(series["data"], list) and series["data"]
    assert isinstance(series["links"], list) and series["links"]


def test_every_sankey_link_names_a_declared_node():
    """A link whose source or target is not in ``data`` silently drops the ribbon."""
    r = FakeResolved()
    series = sankey_option(decoded_transitions(r), r)["series"][0]

    declared = {node["name"] for node in series["data"]}
    for link in series["links"]:
        assert link["source"] in declared, link
        assert link["target"] in declared, link


def test_sankey_node_names_are_never_repeated():
    """ECharts: "The name of the node cannot be repeated."

    (ipecharts/option/seriesitems/sankey.py:281, transcribing the ECharts docs for
    ``series-sankey.data``.) A repeat is how the legacy's two columns would collapse
    into one self-looping node.
    """
    r = FakeResolved()
    names = [node["name"] for node in sankey_option(decoded_transitions(r), r)["series"][0]["data"]]

    assert len(names) == len(set(names)), sorted(names)


def test_sankey_does_not_repeat_a_node_when_the_vocabulary_does():
    """Two start classes can carry the SAME name, and then so can two nodes.

    ``_scrub`` (sdg1531/scheme.py:40-50) deletes digits, so a custom matrix CSV whose
    rows read "Forest 1" and "Forest 2" yields two classes both named ``"Forest "``.
    """
    r = FakeResolved()
    names = ("Forest ", "Forest ", "Water bodies")
    r.scheme = LandCoverScheme(
        start_names=names,
        start_codes=(10, 20, 30),
        end_names=names,
        end_codes=(10, 20, 30),
        matrix=TransitionMatrix(rows=((0, 0, 0),) * 3),
        is_custom=True,
    )
    df = pd.DataFrame(
        [["Forest ", "Water bodies", 4.0]],
        columns=[r.lc_year_start_esa, r.lc_year_end_esa, "Area"],
    )

    node_names = [node["name"] for node in sankey_option(df, r)["series"][0]["data"]]

    assert len(node_names) == len(set(node_names)), node_names


def test_sankey_links_only_ever_run_from_a_start_node_to_an_end_node():
    """The bipartite shape is what guarantees the DAG ECharts requires.

    (ipecharts/option/seriesitems/sankey.py:285 -- "the Sankey diagram theoretically
    only supports Directed Acyclic Graph".) Every source sits in the start-year column
    and every target in the end-year column, so no cycle can exist.
    """
    r = FakeResolved(start_year=2001, end_year=2015)
    series = sankey_option(decoded_transitions(r), r)["series"][0]

    for link in series["links"]:
        assert link["source"].endswith(" 2001"), link
        assert link["target"].endswith(" 2015"), link


def test_sankey_orders_its_columns_by_the_land_cover_vocabulary():
    """sankey.py:66-70 drew the columns in first-appearance order; this uses the scheme's."""
    r = FakeResolved(start_year=2001, end_year=2015)
    names = r.scheme.start_names

    node_names = [
        node["name"] for node in sankey_option(decoded_transitions(r), r)["series"][0]["data"]
    ]

    assert node_names == [
        f"{names[0]} 2001",
        f"{names[1]} 2001",
        f"{names[2]} 2001",
        f"{names[6]} 2001",
        f"{names[0]} 2015",
        f"{names[1]} 2015",
        f"{names[2]} 2015",
        f"{names[6]} 2015",
    ]


def test_sankey_falls_back_to_grey_for_a_class_with_no_colour():
    """sankey.py:136 indexed ``colorDict[leftLabel]`` and raised KeyError instead."""
    r = FakeResolved()
    r.lc_color_by_class = {}
    option = sankey_option(transitions(r), r)

    assert {node["itemStyle"]["color"] for node in option["series"][0]["data"]} == {"#9ea7ad"}


def test_sankey_declares_one_start_node_for_a_class_outside_the_vocabulary():
    """``ordered()``'s tail, and the ``dict.fromkeys`` that feeds it, in one shape.

    Drop the tail and the option carries a link naming a node that was never declared --
    a ribbon ECharts draws as nothing, the exact silent failure this file exists to
    catch. Keep the tail but stop deduplicating ``left_present`` and the opposite
    happens: ``grouped`` carries one row per (start, end) pair, so a class leaving for
    two different end classes appears twice and the tail declares its node twice, which
    ECharts also forbids. The known-class half of ``ordered()`` iterates the vocabulary
    and so cannot show either defect -- only an out-of-vocabulary class can, and it
    needs the two rows below to do it.

    Not reachable through ``decode_transition_areas``, which raises ``StatisticsError``
    on any code outside ``lc_class_combinations`` (sdg1531/stats/decode.py:168-173), so
    it is pinned here rather than left to the integration path.
    """
    r = FakeResolved(start_year=2001, end_year=2015)
    first, second = r.scheme.start_names[0], r.scheme.start_names[1]
    df = pd.DataFrame(
        [["Mangrove", first, 3.0], ["Mangrove", second, 1.0]],
        columns=[r.lc_year_start_esa, r.lc_year_end_esa, "Area"],
    )

    series = sankey_option(df, r)["series"][0]

    names = [node["name"] for node in series["data"]]
    assert names.count("Mangrove 2001") == 1
    declared = set(names)
    assert all(link["source"] in declared for link in series["links"]), series["links"]


def test_sankey_declares_one_end_node_for_a_class_outside_the_vocabulary():
    """The end-side mirror of the test above, and the fourth instance of one bug class.

    ``left_present`` and ``right_present`` are separate expressions with separate
    ``dict.fromkeys`` calls, so a test built on the start side cannot see the end one:
    ``grouped`` repeats an end class once per start class that reaches it, exactly as it
    repeats a start class once per end class it leaves for. Two rows ARRIVING at the same
    out-of-vocabulary class is the only shape that shows it, because ``ordered()``'s
    known half iterates ``r.scheme.end_names`` and is immune either way.
    """
    r = FakeResolved(start_year=2001, end_year=2015)
    first, second = r.scheme.start_names[0], r.scheme.start_names[1]
    df = pd.DataFrame(
        [[first, "Mangrove", 3.0], [second, "Mangrove", 1.0]],
        columns=[r.lc_year_start_esa, r.lc_year_end_esa, "Area"],
    )

    series = sankey_option(df, r)["series"][0]

    names = [node["name"] for node in series["data"]]
    assert names.count("Mangrove 2015") == 1
    declared = set(names)
    assert all(link["target"] in declared for link in series["links"]), series["links"]


def test_sankey_option_uses_only_keys_ipecharts_declares():
    r = FakeResolved()
    option = sankey_option(decoded_transitions(r), r)

    assert set(option) <= OPTION_KEYS, sorted(set(option) - OPTION_KEYS)
    series = option["series"][0]
    assert set(series) <= SANKEY_SERIES_KEYS, sorted(set(series) - SANKEY_SERIES_KEYS)


def test_sankey_pins_the_interaction_values_a_key_check_cannot_see():
    """A key-set assertion passes on any legal-but-wrong value, so the values are pinned.

    ``emphasis.focus`` is a real ECharts option path -- ipecharts references
    ``series-sankey.emphasis.focus`` from ``blur``'s help
    (option/seriesitems/sankey.py:246) -- but ``emphasis`` there is a bare ``Dict`` with
    no schema for its contents, so ``"adjacency"`` is transcribed from the ECharts docs
    and cannot be checked against the package. ``tooltip.trigger``/``triggerOn`` can be:
    both are enumerated in option/tooltip.py:50-72 and :199-215.
    """
    r = FakeResolved()
    option = sankey_option(decoded_transitions(r), r)

    assert option["tooltip"] == {"trigger": "item", "triggerOn": "mousemove"}
    series = option["series"][0]
    assert series["emphasis"] == {"focus": "adjacency"}
    # {b} is the node name; sankey.py:139-145 and :154-160 drew the class name beside
    # each bar, and {c} (the value) would print the ribbon totals instead.
    assert series["label"] == {"formatter": "{b}"}


# --- distribution -----------------------------------------------------------


def test_distribution_fills_a_missing_improved_group_instead_of_raising():
    """bar_plot.py:8 hard-selects three columns and KeyErrors when GEE returned
    no Improved group for the AOI."""
    r = FakeResolved()
    pivot = pd.DataFrame(
        {"Degraded": [50.0, 10.0], "Stable": [50.0, 90.0]},
        index=[r.scheme.start_names[0], r.scheme.start_names[1]],
    )
    pivot.index.name = "landcover"

    option = distribution_option(pivot, r)

    improved = next(s for s in option["series"] if s["name"] == "Improved")
    assert improved["data"] == [0.0, 0.0]


def test_distribution_normalises_rows_to_percent():
    r = FakeResolved()
    pivot = pd.DataFrame(
        {"Degraded": [25.0], "Stable": [25.0], "Improved": [50.0]},
        index=[r.scheme.start_names[0]],
    )
    pivot.index.name = "landcover"

    option = distribution_option(pivot, r)

    values = {s["name"]: s["data"][0] for s in option["series"]}
    assert values == {"Degraded": 25.0, "Stable": 25.0, "Improved": 50.0}
    assert option["xAxis"]["max"] == 100
    assert option["series"][0]["stack"] == "Total"


def test_distribution_survives_an_all_zero_row():
    r = FakeResolved()
    pivot = pd.DataFrame(
        {"Degraded": [0.0], "Stable": [0.0], "Improved": [0.0]},
        index=[r.scheme.start_names[0]],
    )
    pivot.index.name = "landcover"

    option = distribution_option(pivot, r)

    assert [s["data"][0] for s in option["series"]] == [0.0, 0.0, 0.0]
    json.dumps(option)


def test_distribution_orders_rows_by_the_land_cover_vocabulary():
    r = FakeResolved()
    names = r.scheme.start_names
    pivot = pd.DataFrame(
        {"Degraded": [1.0, 1.0], "Stable": [1.0, 1.0], "Improved": [1.0, 1.0]},
        index=[names[2], names[0]],
    )
    pivot.index.name = "landcover"

    option = distribution_option(pivot, r)

    assert option["yAxis"]["data"] == [names[0], names[2]]


def test_distribution_discards_the_nodata_column():
    """bar_plot.py:8 selects three columns, dropping the NoData group before the
    percentages are taken, so the shares are of the CLASSIFIED area only."""
    r = FakeResolved()
    pivot = pd.DataFrame(
        {"NoData": [100.0], "Degraded": [25.0], "Stable": [25.0], "Improved": [50.0]},
        index=[r.scheme.start_names[0]],
    )
    pivot.index.name = "landcover"

    option = distribution_option(pivot, r)

    assert [s["name"] for s in option["series"]] == ["Degraded", "Stable", "Improved"]
    assert [s["data"][0] for s in option["series"]] == [25.0, 25.0, 50.0]


def test_distribution_keeps_the_legacy_legend_colours():
    """parameter/ui.py:49-53, keyed here on the untranslated class names bar_plot.py:8
    selects on rather than on the ``cm.legend.*`` strings the legacy used."""
    r = FakeResolved()
    option = distribution_option(decoded_pivot(r), r)

    assert {s["name"]: s["itemStyle"]["color"] for s in option["series"]} == {
        "Degraded": "#d7191c",
        "Stable": "#ffffbf",
        "Improved": "#2c7bb6",
    }


def test_distribution_axes_are_wired_for_a_horizontal_bar_chart():
    """barh: the categories are on y and the percentage on x (bar_plot.py:14-19)."""
    r = FakeResolved()
    option = distribution_option(decoded_pivot(r), r)

    assert option["xAxis"]["type"] == "value"
    assert option["yAxis"]["type"] == "category"
    categories = option["yAxis"]["data"]
    for series in option["series"]:
        assert series["type"] == "bar"
        assert len(series["data"]) == len(categories), series["name"]


def test_distribution_legend_names_every_series():
    r = FakeResolved()
    option = distribution_option(decoded_pivot(r), r)

    assert option["legend"]["data"] == [s["name"] for s in option["series"]]


def test_distribution_option_uses_only_keys_ipecharts_declares():
    r = FakeResolved()
    option = distribution_option(decoded_pivot(r), r)

    assert set(option) <= OPTION_KEYS, sorted(set(option) - OPTION_KEYS)
    for series in option["series"]:
        assert set(series) <= BAR_SERIES_KEYS, sorted(set(series) - BAR_SERIES_KEYS)


def test_distribution_pins_the_layout_values_a_key_check_cannot_see():
    """``grid.containLabel`` is what keeps the land cover names inside the canvas, and
    ``axisPointer.type`` is enumerated at option/axispointer.py:155. Both are legal
    ECharts either way, so the key-set test above cannot tell a wrong value from a
    right one.
    """
    r = FakeResolved()
    option = distribution_option(decoded_pivot(r), r)

    assert option["grid"] == {"containLabel": True}
    assert option["tooltip"] == {"trigger": "axis", "axisPointer": {"type": "shadow"}}


def test_distribution_keeps_the_legacy_axis_labels():
    """The two display strings kept in the domain on purpose (EXPECTED_DIVERGENCES note
    8): bar_plot.py:17 and :19 hardcode them in English rather than routing them through
    the message catalogue, so they are transcriptions. A decision with no test rots.
    """
    r = FakeResolved()
    option = distribution_option(decoded_pivot(r), r)

    assert option["xAxis"]["name"] == "Percentage of area"  # bar_plot.py:17
    assert option["yAxis"]["name"] == "Land cover type"  # bar_plot.py:19


def test_distribution_keeps_a_land_cover_row_outside_the_vocabulary():
    """The order's tail. Drop it and the row is not reordered but DELETED -- an AOI's
    land cover silently missing from the chart rather than drawn out of order.
    """
    r = FakeResolved()
    known = r.scheme.start_names[0]
    pivot = pd.DataFrame(
        {"Degraded": [4.0, 1.0], "Stable": [0.0, 0.0], "Improved": [0.0, 0.0]},
        index=["Mangrove", known],
    )
    pivot.index.name = "landcover"

    option = distribution_option(pivot, r)

    assert option["yAxis"]["data"] == [known, "Mangrove"]
    assert len(option["series"][0]["data"]) == 2


def test_distribution_does_not_repeat_a_row_when_the_vocabulary_does():
    """The twin of ``test_sankey_does_not_repeat_a_node_when_the_vocabulary_does``.

    Reindexing on a repeated label does not raise -- it duplicates that land cover into
    a phantom second bar carrying the same numbers, which is worse than a crash because
    the chart is silently wrong.
    """
    r = FakeResolved()
    names = ("Forest ", "Forest ", "Water bodies")
    r.scheme = LandCoverScheme(
        start_names=names,
        start_codes=(10, 20, 30),
        end_names=names,
        end_codes=(10, 20, 30),
        matrix=TransitionMatrix(rows=((0, 0, 0),) * 3),
        is_custom=True,
    )
    pivot = pd.DataFrame(
        {"Degraded": [10.0, 5.0], "Stable": [10.0, 15.0], "Improved": [0.0, 0.0]},
        index=["Forest ", "Water bodies"],
    )
    pivot.index.name = "landcover"

    option = distribution_option(pivot, r)

    assert option["yAxis"]["data"] == ["Forest ", "Water bodies"]
    assert {s["name"]: s["data"] for s in option["series"]} == {
        "Degraded": [50.0, 25.0],
        "Stable": [50.0, 75.0],
        "Improved": [0.0, 0.0],
    }


def test_distribution_reads_the_pivot_task_15_actually_produces():
    """End to end over the committed fixture: decode -> pivot -> option.

    Percentages are of the classified area per land cover row -- 400 ha of
    Tree-covered areas (100 degraded, 300 stable), 75 of Cropland (50 degraded,
    25 improved) and 5 of Water bodies (all improved).
    """
    r = FakeResolved()
    names = r.scheme.start_names

    option = distribution_option(decoded_pivot(r), r)

    assert option["yAxis"]["data"] == [names[0], names[2], names[6]]
    assert {s["name"]: s["data"] for s in option["series"]} == {
        "Degraded": [25.0, 66.67, 0.0],
        "Stable": [75.0, 0.0, 0.0],
        "Improved": [0.0, 33.33, 100.0],
    }


# --- both -------------------------------------------------------------------


@pytest.mark.parametrize("name", ["sankey", "distribution"])
def test_option_carries_no_numpy_scalar_anywhere(name):
    """Both shapes, not just one: ``.item()``/``float()``/``.tolist()`` each fix one site."""
    r = FakeResolved()
    option = (
        sankey_option(decoded_transitions(r), r)
        if name == "sankey"
        else distribution_option(decoded_pivot(r), r)
    )

    assert_plain_json(option)
    json.dumps(option)


@pytest.mark.parametrize(
    "planted",
    [
        pytest.param({"series": [{"value": pd.Series([1.0]).iloc[0]}]}, id="numpy-float64"),
        pytest.param({"series": [{"value": pd.Series([1]).iloc[0]}]}, id="numpy-int64"),
        pytest.param({"series": (1.0, 2.0)}, id="tuple"),
        pytest.param({1: "one"}, id="int-key"),
    ],
)
def test_the_plain_json_walk_is_not_a_no_op(planted):
    """``assert_plain_json`` is a test helper, so it gets tested: it must reject what
    ``json.dumps`` silently accepts (a float64, a tuple, an int key) as well as what
    json rejects outright (an int64). Two of the plan's own defects were bugs inside
    the helpers written to prevent them."""
    with pytest.raises(AssertionError):
        assert_plain_json(planted)
