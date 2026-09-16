"""The floating map legend for whichever layers are actually shown.

Not a right-panel tab -- ``page.py`` mounts :func:`MapLegend` as ``MapApp``'s
SIBLING, the same placement pysepal's own demo app uses
(``demo_apps/solara_map_app/app.py:137``): ``LegendComponent``'s own ``.vue``
positions it ``position: fixed`` bottom-centre, so where it sits in the DOM
tree does not matter, and keeping it out of ``right_panel_content`` keeps it
visible regardless of which workflow tab is active.

The obvious way to colour this -- join ``sdg1531.tables.DEGRADATION_COLORS``
to a layer's ``labels`` by the English label string -- breaks on the
performance layer: its class 2 label, ``"Not degraded"``, is deliberately
absent from ``DEGRADATION_COLORS`` (see ``sdg1531/tables.py``). Instead this
reads the SAME ``layer_vis_params()`` the map itself draws with
(``app/panels/map_layers.py``): pixel ``v`` gets ``palette[v - min]`` and
``layer.labels[v]``, so the legend agrees with the tiles by construction
rather than by two tables that happen to line up today. ``min`` starts at 1
(the legacy's NoData/unclassified value is 0, outside the vis window), so
pixel 0 is never drawn and never legended.

Driven by the SAME shown set ``MapLayersPanel`` toggles (``page.py`` threads
one shared ``solara.Reactive`` into both), never a second, independent
reading of which layers are "on the map" -- see that module's docstring for
why this can only be a ``Reactive``, not a live read of the map widget.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import solara
from pysepal.solara.components.legend import DiscreteEntry, LegendComponent, LegendData

from app.message import msg
from app.panels.map_layers import layer_name, layer_vis_params
from sdg1531.engine.indicator import ClassifiedLayer, IndicatorMaps
from sdg1531.enums import IndicatorLayer

__all__ = ("MapLegend", "layer_legend_entries")


def _class_label(layer_id: IndicatorLayer, pixel: int) -> str:
    """Translated legend text for one (layer, pixel) pair.

    Keyed on the layer id and the pixel value, never the domain's English
    string: matching on English text is a join that breaks the first time the
    domain rewords a label (the same reason ``layer_name`` keys on
    ``layer_id.value`` rather than on ``ClassifiedLayer.label``).
    """
    return str(msg(f"legend.classes.{layer_id.value}.{pixel}"))


def layer_legend_entries(layer_id: IndicatorLayer, layer: ClassifiedLayer) -> list[DiscreteEntry]:
    """Discrete chips for one layer, colour and pixel range both taken from
    ``layer_vis_params`` -- the map's own vis dict, not a second derivation.

    ``pixel not in layer.labels`` would mean the vis window and the domain's
    own class table disagree, which is a real bug in one of the two, not a
    translation gap -- raised loudly rather than silently skipped or shown
    unlabelled.
    """
    vis = layer_vis_params(layer_id)
    palette = vis["palette"]
    entries = []
    for pixel in range(vis["min"], vis["max"] + 1):
        if pixel not in layer.labels:
            raise KeyError(f"{layer_id.value} has no class label for pixel {pixel}")
        entries.append(
            DiscreteEntry(label=_class_label(layer_id, pixel), color=palette[pixel - vis["min"]])
        )
    return entries


@dataclass(frozen=True, slots=True)
class _LayerLegend:
    """One shown layer paired with the legend body floated for it."""

    layer_id: str
    label: str
    data: LegendData


@solara.component
def MapLegend(
    maps: IndicatorMaps | None,
    shown: solara.Reactive[frozenset[IndicatorLayer]],
) -> None:
    """Floats the legend of the selected shown layer bottom-centre over the map.

    The dropdown appears once two or more shown layers publish a legend; one
    (or none) renders with no selector at all -- ``LegendComponent``'s own
    rule, unchanged here.
    """
    selected_id, set_selected_id = solara.use_state("")

    legends: list[_LayerLegend] = []
    if maps is not None:
        # `maps.layers()`'s own canonical table order, not `shown.value`'s
        # arbitrary frozenset iteration order -- so the dropdown does not
        # reorder itself across renders that add or remove nothing.
        for layer_id, layer in maps.layers().items():
            if layer_id not in shown.value:
                continue
            legends.append(
                _LayerLegend(
                    layer_id=layer_id.value,
                    label=layer_name(layer_id),
                    data=LegendData(items=layer_legend_entries(layer_id, layer)),
                )
            )

    current = next((entry for entry in legends if entry.layer_id == selected_id), None)
    # Falling back to the first entry is not cosmetic: the legend only renders
    # while it has gradients or items, so an unmatched selection (the
    # previously-selected layer just got removed) would take the whole widget
    # down with it and leave no way back.
    current = current or (legends[0] if legends else None)

    LegendComponent(
        legend_data=asdict(current.data) if current else {},
        selector_options=[{"value": entry.layer_id, "text": entry.label} for entry in legends],
        selected=current.layer_id if current else "",
        event_set_selected=set_selected_id,
    )
