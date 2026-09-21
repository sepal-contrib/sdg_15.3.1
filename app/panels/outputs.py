"""The output panels, as one tab's flat, headed sections.

**Section order is the sub-indicator order and must not change**: Layers ->
Transitions -> Distribution -> Zonal statistics. Export is not a section: each
Layers row carries its own export icon (``app/panels/map_layers.py``), while
``app/panels/exports.py`` still owns the sources.

Each section's header carries that panel's ``msg("<panel>.title")``, icon and
``msg("<panel>.description")``, rendered once by ``SectionHeader`` rather than
a second time inside the panel itself. The descriptions are the one place a
user is told what a computation actually produces, so they say that rather
than naming the section again.

**``is_active`` gates chart CONSTRUCTION, not just visibility.** An
``EChartsRawWidget`` measures its canvas once, at construction, so one built
while its container is hidden bakes in a 100x500 fallback that becoming
visible never corrects. The flag says whether the merged outputs TAB is the
active one, so a chart is always first built while its container is really on
screen. Verified in a browser; see ``docs/guides/solara-app-gotchas.md`` in
the pysepal checkout for the measurement.
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
