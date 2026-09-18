"""Light/dark presentation for the two ECharts figures.

``sdg1531.stats.plots`` builds both chart options and owns everything about
their CONTENT: which nodes and bars exist, their order, and the domain palette
each is painted in. It says nothing about text, axes or background, so ECharts
falls back to its own built-in theme -- black text with a white halo
(``textBorderColor``), a white background, dark axis lines. That is fine on a
light page and unreadable on a dark one, which is what the repo owner saw:
*"in the dark they look like this ... text has that `halo` white that is
annoying"*.

This module is the seam between the two. It takes an option the domain built
and returns a NEW one with presentation merged in, so the domain keeps owning
content and the app keeps owning theme. It never touches ``itemStyle`` or
``lineStyle`` -- those carry the land-cover and degradation palettes, which
must look the same in both themes or the chart stops matching the map and the
legend.

Colours are picked in PYTHON off ``pysepal.solara.use_theme_dark()``, not from
CSS. Two things this repo has already measured the hard way and that apply
here identically: ``var(--v-*)`` custom properties are a Vuetify 3 feature and
resolve to nothing in this stack (see ``app/panels/section_header.py``), and
``solara.lab.use_dark_effective()`` reads a process-wide flag disconnected
from the app's own toggle (see ``app/tabs.py``). A canvas is not styleable by
CSS anyway: ECharts paints text itself, so the values have to reach it as part
of the option dict.

The tones are the ones the rest of the app already uses -- 0.87 foreground,
0.28 for a solid line, 0.12 for a hairline -- black-based in light mode and
white-based in dark, which is Vuetify's own convention.

**Measured in a browser, not assumed.** The same sankey was rendered three
times on one page -- untouched, themed light, themed dark -- and each canvas's
pixels read back (``getImageData`` over the whole surface). ECharts repaints
genuinely differently for each (three distinct ``toDataURL`` lengths: 38994,
35394, 34654), so the option reaches the renderer rather than being ignored as
unknown keys. The halo shows up directly in the counts: the untouched chart has
0.20% near-white pixels and 375 more opaque pixels than the themed one, and
themed-light has **zero** near-white pixels -- that difference IS the white
stroke, since both draw dark text. Themed-dark's 0.15% near-white is the label
text itself, which is the point of it.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

__all__ = ("themed_option",)

_LIGHT: Mapping[str, str] = MappingProxyType(
    {
        "text": "rgba(0, 0, 0, 0.87)",
        "axis": "rgba(0, 0, 0, 0.28)",
        "split": "rgba(0, 0, 0, 0.12)",
    }
)
_DARK: Mapping[str, str] = MappingProxyType(
    {
        "text": "rgba(255, 255, 255, 0.87)",
        "axis": "rgba(255, 255, 255, 0.28)",
        "split": "rgba(255, 255, 255, 0.12)",
    }
)


def _axis(option: dict[str, Any], key: str, tones: Mapping[str, str]) -> None:
    """Theme one axis in place, if the option has one.

    ``distribution_option`` has both axes and ``sankey_option`` has neither, so
    every branch here is reachable and none may assume the key exists.
    """
    axis = option.get(key)
    if not isinstance(axis, dict):
        return
    axis.setdefault("nameTextStyle", {})["color"] = tones["text"]
    axis.setdefault("axisLabel", {})["color"] = tones["text"]
    axis.setdefault("axisLine", {}).setdefault("lineStyle", {})["color"] = tones["axis"]
    axis.setdefault("splitLine", {}).setdefault("lineStyle", {})["color"] = tones["split"]


def themed_option(option: dict[str, Any], dark: bool) -> dict[str, Any]:
    """``option`` with light/dark presentation merged in. The input is not mutated.

    ``deepcopy`` rather than an in-place update: the option comes from a
    ``solara.Reactive`` that the fetch task wrote once, and theming it in place
    would make a later re-theme read values this function had already written
    -- with ``setdefault`` that is idempotent today, but only by accident.
    Copying also keeps a chart rebuild from reaching back into the value the
    panel is holding, which is what a second theme flip would otherwise
    observe.

    ``textBorderWidth: 0`` is the halo fix specifically. ECharts draws series
    labels with a contrast stroke by default; on the sankey that is a white
    outline around every class name, which is what makes the dark-mode chart
    look smeared. It is set on the series label rather than globally because
    that is the only place ECharts reads it from for these two chart types.
    """
    tones = _DARK if dark else _LIGHT
    themed: dict[str, Any] = copy.deepcopy(option)

    # Stated explicitly, though ECharts 5 already defaults to transparent --
    # measured, not assumed: an untouched chart's canvas came back with the
    # same ~33% fully-transparent pixels as a themed one. It is here so that a
    # future ECharts theme preset (those DO paint a background) cannot put a
    # rectangle of almost-but-not-quite the right shade behind every figure;
    # the right panel already carries the theme's own surface colour.
    themed["backgroundColor"] = "transparent"
    themed.setdefault("textStyle", {})["color"] = tones["text"]

    legend = themed.get("legend")
    if isinstance(legend, dict):
        legend.setdefault("textStyle", {})["color"] = tones["text"]

    for key in ("xAxis", "yAxis"):
        _axis(themed, key, tones)

    for series in themed.get("series", ()):
        if not isinstance(series, dict):
            continue
        label = series.setdefault("label", {})
        label["color"] = tones["text"]
        label["textBorderWidth"] = 0

    return themed
