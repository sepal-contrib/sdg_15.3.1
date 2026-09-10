"""DataFrame -> plain ECharts option dicts.

No ipecharts import: the widget is constructed in the app layer, so chart data is
assertable without a display stack. Every value written into an option is coerced to a
plain ``float`` or ``str``, because a numpy scalar crosses the wire badly and does so
QUIETLY: ``json.dumps`` rejects ``numpy.int64`` and ``numpy.float32`` outright but
accepts ``numpy.float64``, which subclasses ``float``. The coercion is not always
observable from here -- ``Series.__iter__`` already boxes through ``ndarray.item`` --
but ``.iloc``, ``.sum()`` and ``.values`` all hand back numpy scalars, so the casts are
what make the option's types a property of this module rather than of pandas' internal
boxing rules. ``distribution_option``'s ``totals.where(totals != 0)`` is defence of the
same kind, and equally unobservable from here: pandas already yields NaN for 0/0, so
``.fillna(0.0)`` alone handles the all-zero row and deleting the ``where`` changes no
output any test can see. It guards the other zero-total shape -- a non-zero class over a
total of zero, which needs a negative area and so cannot come from a ``Reducer.sum`` --
because that one divides to ``inf``, which ``json.dumps`` writes as the bare literal
``Infinity`` and ``JSON.parse`` then rejects. ``str(name)`` over ``pct.index`` is the
third of these: the index holds ``code_to_name_start()`` values, which are already
``str``, so the cast is unobservable from here and exists so a non-string label could
never reach the option.

EXPECTED_DIVERGENCES note -- eight divergences from the legacy charts
(``component/scripts/sankey.py:15-235`` and ``component/scripts/bar_plot.py:1-26``).
Task 17's parity harness must carry all eight:

1. **No legacy counterpart.** The rendering itself. Both legacy functions returned a
   matplotlib ``(fig, ax)`` (sankey.py:42/:235, bar_plot.py:11/:26); these return
   option dicts and never draw. Everything purely visual therefore has nothing to
   compare against: node and bar geometry, the 2% inter-class gap (sankey.py:103),
   the 0.65 ribbon alpha (:199), the two rotated year watermarks (:212-233), the bold
   titles (:203-206, bar_plot.py:20), the hidden spines (bar_plot.py:21-23) and the
   legend placement (:24). The numbers behind them are unchanged.
2. **Behaviour-changing, scoped to node NAMES.** Sankey node names carry the year
   ("Cropland 2001"); the legacy drew two independent columns from
   ``left.unique()``/``right.unique()`` (:66-70) and could repeat a bare label across
   them. ECharts identifies nodes by name and forbids a repeat, so without the suffix
   an unchanged class collapses into one self-looping node. Label text only; no value
   or ribbon changes.
3. **Behaviour-changing, scoped to ORDER.** Sankey columns and distribution rows follow
   the scheme vocabulary. sankey.py:66-70 used the frame's first-appearance order, and
   bar_plot.py plotted the pivot's own (alphabetically sorted) index. Same members,
   same values, different drawing order.
4. **Behaviour-changing.** A class outside ``r.lc_color_by_class`` is drawn in
   ``#9ea7ad`` -- the "no data" grey of parameter/ui.py:55-60 -- where sankey.py:136
   and :150 raised ``KeyError`` on ``colorDict[label]``. The companion
   ``ValueError("specify a colour palette")`` (:73-74) is gone with the argument it
   guarded: the palette comes from the resolved spec, not from a caller.
5. **Behaviour-changing.** :func:`distribution_option` reindexes onto the three
   degradation classes where bar_plot.py:8 hard-selects them, so an AOI for which
   Earth Engine reported no "Improved" group draws a zero-length bar instead of
   raising ``KeyError: "['Improved'] not in index"``.
6. **Behaviour-changing.** A land cover row whose three classes sum to zero yields
   0.0. bar_plot.py:10's ``df.div(df.sum(axis=1))`` yielded NaN for it, which
   matplotlib drew as a gap in the stack.
7. **Behaviour-changing, scoped to the colour KEYS.** ``barh_plot(df, color, title)``
   was called with ``cp.legend`` (parameter/ui.py:49-53), whose keys are the
   TRANSLATED ``cm.legend.*`` strings, while the frame's columns are the untranslated
   names bar_plot.py:8 selects on. The two lined up only in English; in any other
   locale matplotlib silently fell back to its default colour cycle.
   :data:`_DEGRADATION_COLORS` keys on the untranslated names, so the same three hex
   values now land in every locale.
8. **No legacy counterpart.** The ``title`` argument ``barh_plot`` took (:20) is
   dropped -- display strings are the app layer's (spec §4). The two axis names are
   NOT dropped: bar_plot.py:17 and :19 hardcode them in English rather than routing
   them through the message catalogue, so they are transcriptions, not translations.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any

import pandas as pd

__all__ = ["distribution_option", "sankey_option"]

# transcribed from component/parameter/ui.py:49-53 (pm.legend). The keys are the
# untranslated class names bar_plot.py:8 selects on; ui.py keyed the same colours
# on translated strings, which only lined up in English.
_DEGRADATION_COLORS: Mapping[str, str] = MappingProxyType(
    {
        "Degraded": "#d7191c",
        "Stable": "#ffffbf",
        "Improved": "#2c7bb6",
    }
)
_DISTRIBUTION_CLASSES = ("Degraded", "Stable", "Improved")

# parameter/ui.py:59 (pm.legend_bar), the "no data" swatch
_UNKNOWN_CLASS_COLOR = "#9ea7ad"


def sankey_option(df: pd.DataFrame, r: Any) -> dict[str, Any]:
    """Land cover transitions -> an ECharts sankey option.

    Replaces the hand-rolled pySankey of scripts/sankey.py:15-235. Reads
    ``r.scheme.start_names``, ``r.scheme.end_names`` and ``r.lc_color_by_class``.

    ``df`` is what ``decode_transition_areas`` returns: the start year, the end
    year and "Area".
    """
    start_year = df.columns[0]
    end_year = df.columns[1]
    colors = dict(r.lc_color_by_class)

    grouped = df.groupby([start_year, end_year], as_index=False)["Area"].sum()

    left_present = list(dict.fromkeys(grouped[start_year]))
    right_present = list(dict.fromkeys(grouped[end_year]))

    def ordered(vocabulary: Sequence[str], present: list[str]) -> list[str]:
        # dict.fromkeys, not the raw vocabulary: two start classes may carry the same
        # name (scheme.py's _scrub deletes digits, so "Forest 1" and "Forest 2" both
        # become "Forest "), and ECharts forbids a repeated node name.
        known = [name for name in dict.fromkeys(vocabulary) if name in present]
        return known + [name for name in present if name not in set(vocabulary)]

    nodes: list[dict[str, Any]] = []
    # The year suffix is load-bearing: with bare class names ECharts merges the
    # start and end node of an unchanged class into a single self-looping node.
    for name in ordered(r.scheme.start_names, left_present):
        nodes.append(
            {
                "name": f"{name} {start_year}",
                "itemStyle": {"color": colors.get(name, _UNKNOWN_CLASS_COLOR)},
            }
        )
    for name in ordered(r.scheme.end_names, right_present):
        nodes.append(
            {
                "name": f"{name} {end_year}",
                "itemStyle": {"color": colors.get(name, _UNKNOWN_CLASS_COLOR)},
            }
        )

    links = [
        {
            "source": f"{row[start_year]} {start_year}",
            "target": f"{row[end_year]} {end_year}",
            "value": float(row["Area"]),
        }
        for _, row in grouped.iterrows()
    ]

    return {
        "tooltip": {"trigger": "item", "triggerOn": "mousemove"},
        "series": [
            {
                "type": "sankey",
                "data": nodes,
                "links": links,
                "emphasis": {"focus": "adjacency"},
                # sankey.py coloured each ribbon by its left class; "source" is the
                # ECharts spelling of that rule.
                "lineStyle": {"color": "source", "curveness": 0.5},
                "label": {"formatter": "{b}"},
            }
        ],
    }


def distribution_option(pivot: pd.DataFrame, r: Any) -> dict[str, Any]:
    """Land cover x class areas -> a 100% stacked horizontal bar option.

    Transcribed from scripts/bar_plot.py:8-24, with two fixes: the hard
    three-column select at :8 becomes a reindex, so an AOI with no "Improved"
    group no longer raises KeyError; and a row whose total is zero yields zeros
    rather than the NaN :10 would produce.
    """
    frame = pivot.reindex(columns=list(_DISTRIBUTION_CLASSES), fill_value=0)

    # dict.fromkeys for the same reason sankey_option's ordered() uses it: a scrubbed
    # custom scheme can name two start classes alike, and reindexing on a repeated label
    # duplicates that land cover's row into a second bar carrying the same numbers.
    vocabulary = list(dict.fromkeys(r.scheme.start_names))
    order = [name for name in vocabulary if name in frame.index]
    order += [name for name in frame.index if name not in set(vocabulary)]
    frame = frame.reindex(order)

    totals = frame.sum(axis=1)
    pct = frame.div(totals.where(totals != 0), axis=0).mul(100).round(2).fillna(0.0)

    return {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"data": list(_DISTRIBUTION_CLASSES)},
        "grid": {"containLabel": True},
        "xAxis": {"type": "value", "max": 100, "name": "Percentage of area"},
        "yAxis": {
            "type": "category",
            "name": "Land cover type",
            "data": [str(name) for name in pct.index],
        },
        "series": [
            {
                "name": klass,
                "type": "bar",
                "stack": "Total",
                "itemStyle": {"color": _DEGRADATION_COLORS[klass]},
                "data": [float(value) for value in pct[klass]],
            }
            for klass in _DISTRIBUTION_CLASSES
        ],
    }
