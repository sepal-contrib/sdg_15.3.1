"""The five output panels, as one tab's collapsible sections.

The repo owner asked for this after using the app: *"all the computation
buttons ... should be in the same tab, like with multiple sections, similarly
as se.plan does ... like all the computations in one single place."* This
module is that tab's content -- ``se.plan``'s own
``component/widget/dashboard_layer_panels.py`` builds the same shape with
``sw.ExpansionPanels``/``ExpansionPanel``/``ExpansionPanelHeader``/
``ExpansionPanelContent``; this uses the reacton equivalents (``rv.*``, never
``v.*`` inside an ``rv.*`` container).

**Section order is the old tab order and must not change**: Layers ->
Transitions -> Results -> Zonal -> Export (``app/tabs.py``'s own docstring
already names this as the tabs' DISPLAY order; task 27 folds five tabs into
five sections without reordering them). Each section keeps its panel's own
``msg("<panel>.description")`` (rendered inside the panel component itself,
same as before) and its header carries that panel's existing
``msg("<panel>.title")`` and icon -- no new copy invented for any of the five.

Layers opens by default (``_DEFAULT_OPEN = 0``): it needs no button click to
be useful (it is a read-only table of what layers a run produced), unlike the
other four, which show nothing until the user presses Compute -- opening one
of those by default would still look empty. All five collapsed was rejected
outright: the brief that asked for this is explicit that the tab must not
open looking empty.

**The chart-mount trap.** Two sections mount an ``EChartsRawWidget`` via
``solara.display()`` (``ResultsPanel``, ``TransitionsPanel``) called directly
in the render body. ``rv.TabsItems`` (this app's OTHER container, in
``app/tabs.py``) hides an inactive tab without unmounting it, and a chart
mounted there was verified in a real browser to survive a tab switch with its
canvas intact. ``rv.ExpansionPanel`` is a different container, and that
verification does not transfer: probed the same way (a throwaway app mounting
an ``EChartsRawWidget`` inside ``rv.ExpansionPanel``, driven by
``pysepal/scripts/browser_probe.mjs``), collapsing a section does NOT unmount
its content (the canvas keeps its pixel dimensions, just hidden via
``display: none``) -- so a chart already built while open survives a
collapse/reopen cycle same as in a tab. But a chart built for the FIRST time
while its section is collapsed -- which happens whenever the async fetch
behind it resolves after the user has already opened a DIFFERENT section --
measured a fixed, wrong canvas size (ECharts' own fallback, not the
container's real width) that reopening the section never corrected. Both
``ResultsPanel`` and ``TransitionsPanel`` now take an ``is_open`` flag for
exactly this: their own chart-widget memo is gated on it, not just on the
fetched data being ready, so the widget is always first constructed during a
render where its section is already the open one. Threaded here from this
component's own ``open_index`` state -- the only place that knows which
section that is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import reacton.ipyvuetify as rv
import solara

from app.message import msg
from app.panels.exports import ExportsPanel
from app.panels.map_layers import MapLayersPanel
from app.panels.results import ResultsPanel
from app.panels.transitions import TransitionsPanel
from app.panels.zonal import ZonalPanel
from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.indicator import IndicatorMaps
from sdg1531.enums import IndicatorLayer
from sdg1531.spec import RunSpec

__all__ = ("OutputsPanel", "SectionDescriptor", "output_sections")

#: Layers -- see the module docstring for why.
_DEFAULT_OPEN = 0
_TRANSITIONS_INDEX = 1
_RESULTS_INDEX = 2


@dataclass(frozen=True, slots=True)
class SectionDescriptor:
    """One section of the merged outputs tab, in DISPLAY order. Mirrors
    ``app/tabs.py``'s ``TabDescriptor``: order lives in list position alone,
    since nothing here has an ``id`` for a stray sort to key on."""

    title: str
    icon: str
    content: list[object]


def output_sections(
    maps: IndicatorMaps | None = None,
    ctx: ExecutionContext | None = None,
    spec: RunSpec | None = None,
    map_: Any = None,
    gee_interface: Any = None,
    sepal_client: Any = None,
    shown_layers: solara.Reactive[frozenset[IndicatorLayer]]
    | frozenset[IndicatorLayer]
    | None = None,
    open_index: int = _DEFAULT_OPEN,
) -> list[SectionDescriptor]:
    """The five sections, in DISPLAY order. Bare-callable with every argument
    defaulting to ``None`` (or ``_DEFAULT_OPEN`` for ``open_index``), same
    reason ``app.tabs.workflow_tabs`` is bare-callable -- see that function's
    docstring; the reasoning carries over unchanged. ``export_content`` is the
    one guarded build (``ExportsPanel.spec`` is a bare ``RunSpec``, unlike
    every other panel's already-``X | None`` ``maps``/``ctx``), for the exact
    same mypy-narrowing reason ``workflow_tabs`` guards it.
    """
    export_content: list[object] = (
        [ExportsPanel(maps=maps, ctx=ctx, spec=spec, gee_interface=gee_interface)]
        if spec is not None
        else []
    )
    return [
        SectionDescriptor(
            msg("layers.title"),
            "mdi-layers",
            [
                MapLayersPanel(
                    maps=maps,
                    map_=map_,
                    gee_interface=gee_interface,
                    shown=shown_layers if shown_layers is not None else frozenset[IndicatorLayer](),
                )
            ],
        ),
        SectionDescriptor(
            msg("transitions.title"),
            "mdi-transit-transfer",
            [
                TransitionsPanel(
                    maps=maps,
                    ctx=ctx,
                    gee_interface=gee_interface,
                    is_open=open_index == _TRANSITIONS_INDEX,
                )
            ],
        ),
        SectionDescriptor(
            msg("results.title"),
            "mdi-chart-bar",
            [
                ResultsPanel(
                    maps=maps,
                    ctx=ctx,
                    gee_interface=gee_interface,
                    is_open=open_index == _RESULTS_INDEX,
                )
            ],
        ),
        SectionDescriptor(
            msg("zonal.title"),
            "mdi-table",
            [
                ZonalPanel(
                    maps=maps, ctx=ctx, gee_interface=gee_interface, sepal_client=sepal_client
                )
            ],
        ),
        SectionDescriptor(msg("exports.title"), "mdi-export-variant", export_content),
    ]


@solara.component
def OutputsPanel(
    maps: IndicatorMaps | None,
    ctx: ExecutionContext | None,
    spec: RunSpec,
    map_: Any,
    gee_interface: Any,
    sepal_client: Any,
    shown_layers: solara.Reactive[frozenset[IndicatorLayer]]
    | frozenset[IndicatorLayer] = frozenset[IndicatorLayer](),
) -> None:
    """The merged outputs tab's whole content: an accordion over
    ``output_sections()``, single-select (opening one closes whichever else
    was open) so ``open_index`` is unambiguous for the ``is_open`` wiring
    above.
    """
    open_index, set_open_index = solara.use_state(_DEFAULT_OPEN)

    sections = output_sections(
        maps=maps,
        ctx=ctx,
        spec=spec,
        map_=map_,
        gee_interface=gee_interface,
        sepal_client=sepal_client,
        shown_layers=shown_layers,
        open_index=open_index,
    )

    with rv.ExpansionPanels(v_model=open_index, on_v_model=set_open_index):
        for section in sections:
            rv.ExpansionPanel(
                children=[
                    rv.ExpansionPanelHeader(
                        children=[
                            rv.Icon(children=[section.icon], style_="margin-right: 8px;"),
                            section.title,
                        ]
                    ),
                    rv.ExpansionPanelContent(children=section.content),
                ]
            )
