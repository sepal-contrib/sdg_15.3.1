"""Light/dark presentation for the two charts, merged on top of the domain's
own option.

Every case below runs against a REAL option from ``sdg1531.stats.plots`` --
not a hand-written dict shaped like one -- so a change to what the domain
builds reaches these tests instead of sliding past a stand-in that agrees with
itself. The sankey and the distribution chart have deliberately different
shapes (no axes vs two, no legend vs one), which is what makes them worth
testing as a pair.
"""

from __future__ import annotations

import pandas as pd

from app.panels.chart_theme import themed_option
from sdg1531.resolve import resolve
from sdg1531.stats.plots import distribution_option, sankey_option
from sdg1531.tables import DEGRADATION_COLORS
from tests.spec_factory import default_spec

_RESOLVED = resolve(default_spec(threshold=0.0))

_TRANSITIONS = pd.DataFrame(
    {2000: ["Forest", "Cropland"], 2020: ["Cropland", "Cropland"], "Area": [1.0, 2.0]}
)
_PIVOT = pd.DataFrame(
    {"Degraded": [1.0, 0.0], "Stable": [2.0, 3.0], "Improved": [0.0, 1.0]},
    index=["Forest", "Cropland"],
)


def _sankey() -> dict:
    return sankey_option(_TRANSITIONS, _RESOLVED)


def _distribution() -> dict:
    return distribution_option(_PIVOT, _RESOLVED)


def test_the_domains_option_is_never_mutated():
    """The option lives in a ``solara.Reactive`` the fetch task wrote once, and
    the panel re-themes it on every theme flip. Theming in place would make the
    second flip read values the first one wrote."""
    option = _distribution()
    before = repr(option)

    themed_option(option, dark=True)

    assert repr(option) == before


def test_the_label_halo_is_switched_off_on_every_series():
    """The repo owner's actual complaint: *"text has that `halo` white that is
    annoying"*. ECharts draws series labels with a contrast stroke by default,
    which on the sankey is a white outline around every class name. Checked on
    BOTH charts and in BOTH themes -- the halo is wrong on a light background
    too, it is merely invisible there.
    """
    for build in (_sankey, _distribution):
        for dark in (True, False):
            themed = themed_option(build(), dark=dark)
            assert themed["series"], "the fixture built a chart with no series"
            for series in themed["series"]:
                assert series["label"]["textBorderWidth"] == 0


def test_text_colour_actually_differs_between_the_two_themes():
    """The floor under everything else here: a themer that returned the same
    colours either way would satisfy every "is it set" assertion in this file.
    """
    light = themed_option(_distribution(), dark=False)
    dark = themed_option(_distribution(), dark=True)

    assert light["textStyle"]["color"] != dark["textStyle"]["color"]
    assert light["legend"]["textStyle"]["color"] != dark["legend"]["textStyle"]["color"]
    assert light["xAxis"]["axisLabel"]["color"] != dark["xAxis"]["axisLabel"]["color"]
    assert (
        light["yAxis"]["axisLine"]["lineStyle"]["color"]
        != (dark["yAxis"]["axisLine"]["lineStyle"]["color"])
    )
    assert light["series"][0]["label"]["color"] != dark["series"][0]["label"]["color"]


def test_the_data_palette_is_left_alone_in_both_themes():
    """The land-cover and degradation colours are the domain's, and the map and
    the floating legend are painted from the same tables -- a chart that
    re-tinted them for dark mode would stop matching either. This is the one
    thing the themer must NOT touch.
    """
    for dark in (True, False):
        bars = themed_option(_distribution(), dark=dark)
        assert [s["itemStyle"]["color"] for s in bars["series"]] == [
            DEGRADATION_COLORS[klass] for klass in ("Degraded", "Stable", "Improved")
        ]

        sankey = themed_option(_sankey(), dark=dark)
        original = _sankey()
        assert [n["itemStyle"] for n in sankey["series"][0]["data"]] == [
            n["itemStyle"] for n in original["series"][0]["data"]
        ]
        assert sankey["series"][0]["lineStyle"] == original["series"][0]["lineStyle"]


def test_the_chart_background_is_transparent_so_the_panel_shows_through():
    """Not a fix -- ECharts 5 already defaults to transparent, measured in a
    browser (an untouched chart's canvas came back with the same share of
    fully-transparent pixels as a themed one). Pinned so that reaching for an
    ECharts theme preset later, which DOES paint a background, has to be a
    deliberate change rather than a silent one."""
    for build in (_sankey, _distribution):
        for dark in (True, False):
            assert themed_option(build(), dark=dark)["backgroundColor"] == "transparent"


def test_a_chart_with_no_axes_or_legend_is_themed_without_inventing_them():
    """``sankey_option`` has neither, and the themer must not add empty ones --
    ECharts renders an axis it is given, so a fabricated ``xAxis`` would draw a
    stray line across the sankey.
    """
    themed = themed_option(_sankey(), dark=True)

    assert "xAxis" not in themed
    assert "yAxis" not in themed
    assert "legend" not in themed
    assert themed["textStyle"]["color"]  # ... but the chart is still themed


def test_the_domains_own_content_survives_theming():
    """Node names, link values and bar data are what the chart IS; theming adds
    presentation beside them and must not drop or reorder any of it."""
    original = _sankey()
    themed = themed_option(original, dark=True)

    assert themed["series"][0]["data"] == original["series"][0]["data"]
    assert themed["series"][0]["links"] == original["series"][0]["links"]
    assert themed["tooltip"] == original["tooltip"]

    bars_before = _distribution()
    bars_after = themed_option(bars_before, dark=True)
    assert bars_after["yAxis"]["data"] == bars_before["yAxis"]["data"]
    assert [s["data"] for s in bars_after["series"]] == [s["data"] for s in bars_before["series"]]
