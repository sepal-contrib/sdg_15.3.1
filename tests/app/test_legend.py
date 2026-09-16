"""The floating legend: colours from ``layer_vis_params``, driven by the
shown set -- never a second, independent derivation of either.

``ee.Image.constant(1)`` builds a real client-side graph with no network call
(``tests/conftest.py`` initialises an offline ``ee``), so ``_build_maps``
below reads the domain's REAL ``ClassifiedLayer.labels`` for all seven
layers -- not a hand-typed stand-in for them -- the same technique
``tests/test_stats_requests.py``'s own ``_export_layers`` uses.
"""

from __future__ import annotations

import ee
import solara

from app.message import messages, msg
from app.panels.legend import MapLegend, layer_legend_entries
from app.panels.map_layers import layer_name, layer_vis_params
from sdg1531.engine.indicator import IndicatorMaps
from sdg1531.engine.land_cover import LandCoverMaps
from sdg1531.enums import IndicatorLayer
from sdg1531.resolve import resolve
from sdg1531.tables import DEGRADATION_COLORS
from tests.spec_factory import default_spec


def _build_maps() -> IndicatorMaps:
    image = ee.Image.constant(1)
    return IndicatorMaps(
        resolved=resolve(default_spec()),
        land_cover=LandCoverMaps(stack=image),
        soc=image,
        productivity=image,
        productivity_trend=image,
        productivity_state=image,
        productivity_performance=image,
        indicator=image,
    )


def _legend_widget(box: object) -> object:
    """``MapLegend`` renders exactly one child: the ``LegendComponent`` Vue
    widget. Same discovery pattern pysepal's own ``test_solara/test_legend.py``
    uses for the same widget."""
    children = getattr(box, "children", None) or []
    assert len(children) == 1
    return children[0]


# ---------------------------------------------------------------------------
# `layer_legend_entries` -- the colour/label derivation itself.
# ---------------------------------------------------------------------------


def test_the_performance_layer_pins_its_two_entries_from_the_vis_palette():
    """The rule this whole task turns on: colours come from
    ``layer_vis_params``'s palette, never ``DEGRADATION_COLORS`` keyed by the
    label string. ``PROD_PERFORMANCE_LABELS``' class-2 label, "Not degraded",
    is deliberately absent from ``DEGRADATION_COLORS`` (``sdg1531/tables.py``),
    so that route would ``KeyError`` on exactly this layer -- this is the
    layer that makes the two routes actually distinguishable.
    """
    layer = _build_maps().layers()[IndicatorLayer.PRODUCTIVITY_PERFORMANCE]

    entries = layer_legend_entries(IndicatorLayer.PRODUCTIVITY_PERFORMANCE, layer)

    assert [entry.color for entry in entries] == list(DEGRADATION_COLORS.values())[1:3]
    assert [entry.label for entry in entries] == [
        msg("legend.classes.productivity_performance.1"),
        msg("legend.classes.productivity_performance.2"),
    ]


def test_nodata_pixel_zero_never_appears_in_the_legend():
    """The vis window starts at 1 (``layer_vis_params``'s ``min``); pixel 0
    (NoData) is never drawn on the map and must never be legended either."""
    layer = _build_maps().layers()[IndicatorLayer.LAND_COVER]

    entries = layer_legend_entries(IndicatorLayer.LAND_COVER, layer)

    assert len(entries) == 3  # Degraded, Stable, Improved -- NOT four
    assert entries[0].label == msg("legend.classes.land_cover.1")
    assert entries[-1].label == msg("legend.classes.land_cover.3")


def test_every_layer_class_resolves_through_the_catalogue_in_every_locale(monkeypatch):
    """Walks the REAL seven layers' REAL ``labels`` -- not a hand-typed
    roster of five class names -- across every shipped locale, not only
    English. Mirrors Task 22's ``test_every_indicator_layer_resolves_...``:
    monkeypatches ``current_locale`` at its lookup site rather than the
    global ``pysepal.i18n.set_locale``, which would re-render every earlier
    test's still-mounted render tree with that test's own monkeypatches
    already undone.
    """
    import pysepal.i18n.binding as i18n_binding

    layers = _build_maps().layers()
    for code in messages.available_locales():
        monkeypatch.setattr(i18n_binding, "current_locale", lambda code=code: code)
        for layer_id, layer in layers.items():
            vis = layer_vis_params(layer_id)
            entries = layer_legend_entries(layer_id, layer)
            for pixel, entry in zip(range(vis["min"], vis["max"] + 1), entries, strict=True):
                assert entry.label == msg(f"legend.classes.{layer_id.value}.{pixel}")
                assert entry.label  # never empty / a missing-key marker


# ---------------------------------------------------------------------------
# `MapLegend` -- driven by the shown set, never all seven.
# ---------------------------------------------------------------------------


def test_no_maps_renders_nothing():
    box, rc = solara.render(
        MapLegend(maps=None, shown=solara.reactive(frozenset())), handle_error=False
    )
    assert rc is not None
    widget = _legend_widget(box)
    assert widget.legend_data == {}


def test_an_empty_shown_set_renders_nothing_even_with_a_real_build():
    box, rc = solara.render(
        MapLegend(maps=_build_maps(), shown=solara.reactive(frozenset())), handle_error=False
    )
    assert rc is not None
    widget = _legend_widget(box)
    assert widget.legend_data == {}
    assert widget.selector_options == []
    assert widget.selected == ""


def test_the_legend_only_shows_layers_actually_in_the_shown_set():
    """Task 24's central wiring rule: adding ONE layer to the shown set must
    legend exactly that one, not all seven ``maps.layers()`` carries."""
    maps = _build_maps()
    shown = solara.reactive(frozenset({IndicatorLayer.SOC}))

    box, rc = solara.render(MapLegend(maps=maps, shown=shown), handle_error=False)
    assert rc is not None

    widget = _legend_widget(box)
    # `showSelector` (Legend.vue) only draws the dropdown for 2+ options; the
    # PYTHON side still carries the one option that exists, so this asserts
    # the Python-visible contract, not the template's own visibility rule.
    assert widget.selector_options == [{"value": "soc", "text": layer_name(IndicatorLayer.SOC)}]
    assert widget.selected == IndicatorLayer.SOC.value
    assert [item["label"] for item in widget.legend_data["items"]] == [
        entry.label
        for entry in layer_legend_entries(IndicatorLayer.SOC, maps.layers()[IndicatorLayer.SOC])
    ]


def test_the_dropdown_appears_once_a_second_layer_is_shown_in_canonical_order():
    maps = _build_maps()
    shown = solara.reactive(frozenset({IndicatorLayer.SOC}))

    box, rc = solara.render(MapLegend(maps=maps, shown=shown), handle_error=False)
    assert rc is not None
    rc.force_update()

    # SOC alone: one option -- the template draws no dropdown for it, but
    # the Python-visible trait already carries it.
    widget = _legend_widget(box)
    assert len(widget.selector_options) == 1

    shown.value = shown.value | {IndicatorLayer.LAND_COVER}
    rc.force_update()

    widget = _legend_widget(box)
    # `maps.layers()`'s own canonical table order (LAND_COVER precedes SOC),
    # not the frozenset's arbitrary iteration order.
    assert [opt["value"] for opt in widget.selector_options] == [
        IndicatorLayer.LAND_COVER.value,
        IndicatorLayer.SOC.value,
    ]
    assert [opt["text"] for opt in widget.selector_options] == [
        layer_name(IndicatorLayer.LAND_COVER),
        layer_name(IndicatorLayer.SOC),
    ]


def test_removing_down_to_zero_shown_layers_clears_the_legend():
    maps = _build_maps()
    shown = solara.reactive(frozenset({IndicatorLayer.SOC}))

    box, rc = solara.render(MapLegend(maps=maps, shown=shown), handle_error=False)
    assert rc is not None

    shown.value = frozenset()
    rc.force_update()

    widget = _legend_widget(box)
    assert widget.legend_data == {}
    assert widget.selector_options == []


def test_an_unmatched_selection_falls_back_to_the_first_shown_layer():
    """The load-bearing trap pysepal's own demo documents: the legend only
    renders while it has gradients or items, so if the previously-selected
    layer is removed, the fallback to the first remaining entry is what
    keeps the widget from disappearing with no way back."""
    maps = _build_maps()
    shown = solara.reactive(frozenset({IndicatorLayer.SOC, IndicatorLayer.LAND_COVER}))

    box, rc = solara.render(MapLegend(maps=maps, shown=shown), handle_error=False)
    assert rc is not None

    widget = _legend_widget(box)
    # Select SOC explicitly (the second option), simulating the user's pick.
    widget._handle_custom_msg({"event": "set_selected", "data": IndicatorLayer.SOC.value}, [])
    rc.force_update()
    assert _legend_widget(box).selected == IndicatorLayer.SOC.value

    shown.value = frozenset({IndicatorLayer.LAND_COVER})  # SOC removed
    rc.force_update()

    widget = _legend_widget(box)
    assert widget.selected == IndicatorLayer.LAND_COVER.value
    assert widget.legend_data != {}
