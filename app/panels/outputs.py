"""The output panels, as one tab's flat, headed sections.

The repo owner asked for this after using the app: *"all the computation
buttons ... should be in the same tab, like with multiple sections, similarly
as se.plan does ... like all the computations in one single place."* Task 27
first built this as an ``rv.ExpansionPanels`` accordion; the repo owner then
asked for that to go -- *"I didn't like the expansion panels you added, what
about using like subtitles?"* -- so this module now renders them as flat,
always-visible sections, each introduced by
``app/panels/section_header.py``'s ``SectionHeader`` (title, icon and the
panel's own description as one styled unit) instead of an
``ExpansionPanelHeader``/``ExpansionPanelContent`` pair.

**Section order is the old tab order and must not change**: Layers ->
Transitions -> Results -> Zonal. Task 27 folded the output tabs into sections
without reordering them, and neither the move to flat sections nor the loss of
the fifth reorders the rest.

**There were five sections; Export is now the fourth's worth of icons
instead.** The repo owner asked for it -- *"what if the export can someway
included in the layer section?"* -- so ``app/panels/map_layers.py`` hosts the
export dialog and each of its table rows opens it preselected on that row's
own layer. ``app/panels/exports.py`` still owns the sources; it just no longer
owns a section. One fewer heading, and export now sits next to the thing being
exported.

Each section's header carries that panel's ``msg("<panel>.title")``, icon and
``msg("<panel>.description")``. The description used to be rendered a second
time, inside the panel component itself, as a plain ``solara.Markdown`` line
below its own title-less content; it was removed from every panel component
once the header started showing it, so title and description read as one unit
rather than a heading followed by a stray sentence. The descriptions
themselves got longer in the same round the Export section went away -- the
owner's *"the transitions, distribution, zonal stats that should show some
info like 3 lines explanation text"*. They are the one place a user is told
what a computation actually produces, so they now say that rather than naming
the section a second time.

Every section is always visible -- there is no "default open index" left to
choose. What survives from that concept is only which section's OWN chart, if
any, needs special mount timing; see the chart-mount trap below.

**The chart-mount trap. This is now the THIRD container these charts have
lived in**, and behaviour has changed with every one so far:

* ``rv.TabItem`` (``app/tabs.py``, this app's OWN OTHER container) -- verified
  fine for a chart that STAYS mounted after being built while visible, then
  survives a tab switch away and back with its canvas intact.
* ``rv.ExpansionPanel`` (task 27) -- broke: a chart built for the FIRST time
  while its section was collapsed measured a fixed 100x500 canvas (ECharts'
  own fallback, not the container's real width) that reopening never
  corrected. Task 27's fix: an ``is_open`` flag gating each chart's
  ``use_memo`` on "is MY section the one currently expanded", so the widget
  is always first built during a render where its section is already open.
* Flat sections (this task) -- the accordion (and its per-section open/closed
  state) is gone, so naively deleting ``is_open`` and always building the
  chart looked right: every section renders unconditionally now, all the
  time. **Measured instead of assumed, with a throwaway probe mirroring task
  27's own technique** (an ``EChartsRawWidget`` behind an ``rv.TabsItems``
  pair, driven by ``pysepal/scripts/browser_probe.mjs --resize 1400x900``):
  the accordion is gone, but the outer container is NOT -- this whole panel
  still lives inside ``rv.TabItem`` (the merged outputs TAB, one of
  ``app/tabs.py``'s three), which ``WorkflowTabs``'s own docstring already
  documents as mounting a tab's content once, on first visit, and never
  unmounting it afterwards. That is exactly ``rv.ExpansionPanel``'s own
  eager-DOM, CSS-toggled behaviour, not a lazier one: switching to a
  DIFFERENT workflow tab while a chart's async fetch is still in flight, then
  letting it resolve while the outputs tab is hidden, reproduced the
  IDENTICAL 100x500 fallback canvas task 27 found -- confirmed with the exact
  same probe technique, gate removed, chart built while ``display: none``.
  So the trap survives the move to flat sections unchanged; only its
  ADDRESS moves, from "which accordion section is open" (a concept flat
  sections no longer have) to "is the merged outputs TAB itself the one
  currently active" (a concept ``app/tabs.py``'s ``WorkflowTabs`` owns, since
  it is the only place that knows). ``is_open`` therefore becomes
  ``is_active`` here: threaded from ``WorkflowTabs``'s own ``active_tab``
  state, through ``workflow_tabs()``, into ``OutputsPanel``, and down into
  ``ResultsPanel``/``TransitionsPanel`` exactly as before -- re-probed with
  the gate restored (now keyed on the OUTER tab instead of an accordion
  section): the widget builds ``None`` while the outputs tab is inactive, and
  on switching to it, builds fresh at the real container width.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import reacton.ipyvuetify as rv
import solara

from app.message import msg
from app.panels.map_layers import MapLayersPanel
from app.panels.results import ResultsPanel
from app.panels.section_header import SectionHeader
from app.panels.transitions import TransitionsPanel
from app.panels.zonal import ZonalPanel
from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.indicator import IndicatorMaps
from sdg1531.enums import IndicatorLayer
from sdg1531.spec import RunSpec

__all__ = ("OutputsPanel", "SectionDescriptor", "output_sections")


@dataclass(frozen=True, slots=True)
class SectionDescriptor:
    """One section of the merged outputs tab, in DISPLAY order. Mirrors
    ``app/tabs.py``'s ``TabDescriptor``: order lives in list position alone,
    since nothing here has an ``id`` for a stray sort to key on."""

    title: str
    icon: str
    description: str
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
    is_active: bool = True,
) -> list[SectionDescriptor]:
    """The four sections, in DISPLAY order. Bare-callable with every argument
    defaulting to ``None`` (or ``True`` for ``is_active``) -- same reason
    ``app.tabs.workflow_tabs`` is bare-callable; see that function's
    docstring.

    ``spec`` is accepted and unused. It reached the deleted Export section and
    nothing else; the parameter stays because ``OutputsPanel`` takes a bare
    ``RunSpec`` from ``app/tabs.py``, which is what forces that call site's own
    mypy-narrowing guard, and dropping it here would only move the churn.
    """
    return [
        SectionDescriptor(
            msg("layers.title"),
            "mdi-layers",
            msg("layers.description"),
            [
                MapLayersPanel(
                    maps=maps,
                    ctx=ctx,
                    map_=map_,
                    gee_interface=gee_interface,
                    sepal_client=sepal_client,
                    shown=shown_layers if shown_layers is not None else frozenset[IndicatorLayer](),
                )
            ],
        ),
        SectionDescriptor(
            msg("transitions.title"),
            "mdi-transit-transfer",
            msg("transitions.description"),
            [
                TransitionsPanel(
                    maps=maps,
                    ctx=ctx,
                    gee_interface=gee_interface,
                    is_open=is_active,
                )
            ],
        ),
        SectionDescriptor(
            msg("results.title"),
            "mdi-chart-bar",
            msg("results.description"),
            [
                ResultsPanel(
                    maps=maps,
                    ctx=ctx,
                    gee_interface=gee_interface,
                    is_open=is_active,
                )
            ],
        ),
        SectionDescriptor(
            msg("zonal.title"),
            "mdi-table",
            msg("zonal.description"),
            [
                ZonalPanel(
                    maps=maps, ctx=ctx, gee_interface=gee_interface, sepal_client=sepal_client
                )
            ],
        ),
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
    is_active: bool = True,
) -> None:
    """The merged outputs tab's whole content: four flat, headed sections
    over ``output_sections()``, stacked and always visible.

    ``is_active`` says whether the merged outputs TAB (``app/tabs.py``'s
    ``WorkflowTabs``, one of three ``rv.TabItem``s) is the one currently
    active -- see the module docstring's chart-mount trap for why this
    replaced the old per-accordion-section ``open_index``. Defaults to
    ``True`` so a bare, standalone render of this panel (as most of
    ``tests/app/test_panel_outputs.py`` does) behaves as it always has.
    """
    sections = output_sections(
        maps=maps,
        ctx=ctx,
        spec=spec,
        map_=map_,
        gee_interface=gee_interface,
        sepal_client=sepal_client,
        shown_layers=shown_layers,
        is_active=is_active,
    )

    for section in sections:
        SectionHeader(title=section.title, icon=section.icon, description=section.description)
        # A plain, unstyled `rv.Html` div: its only job is to be a live widget
        # for `section.content`'s already-built (inert, since `output_sections`
        # is a plain function, not a `@solara.component`) elements to attach to
        # -- see `app/tabs.py`'s `workflow_tabs` docstring for the same
        # "inert element descriptor" mechanism. It introduces no CSS visibility
        # toggle of its own, so it cannot reintroduce the accordion's own
        # collapsed/hidden state.
        rv.Html(tag="div", style_="margin-bottom: 16px;", children=section.content)
