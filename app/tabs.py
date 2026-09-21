"""The right panel's workflow, as tabs: AOI -> PARAMS -> Results.

**Tab labels are short, and have their own ``tabs.*`` catalogue group.** The
strip has ~418px inside the 450px panel. Measured in a browser: the steps'
full titles come to 418px in English -- exactly at the limit -- and 429px in
Spanish, which tips Vuetify into drawing overflow chevrons. Hence "AOI",
"Parameters", "Results" here, while each step keeps its full ``step.*`` title
for the header it renders inside the PARAMS tab.

The assessment period is chosen in PARAMS before land cover and SOC because
both inherit it (``app/steps/period_override.py``); that is what fixes the
order within the tab.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import reacton.ipyvuetify as rv
import solara
from pysepal.mapping.sepal_map import SepalMap

from app.message import msg
from app.panels.outputs import OutputsPanel
from app.panels.params import ParamsPanel
from app.state import problems_for
from app.steps.aoi import AoiStep
from app.steps.run import BuildOutcome
from sdg1531.enums import IndicatorLayer
from sdg1531.spec import RunSpec

__all__ = ("TabDescriptor", "WorkflowTabs", "workflow_tabs")


@dataclass(frozen=True, slots=True)
class TabDescriptor:
    """One workflow tab, in DISPLAY order.

    ``step`` keys the tab's problems off ``app.state.problems_for``: one
    ``STEP_PREFIXES`` key, a tuple of them for a tab folding several, or
    ``None`` for the outputs tab, gated by ``outcome.maps`` instead. A tuple
    is never registered in ``STEP_PREFIXES``: that mapping requires every
    field be owned by exactly one step, and a combined entry would
    double-claim what its members already own.
    """

    step: str | tuple[str, ...] | None
    title: str
    icon: str
    content: list[object]


def workflow_tabs(
    spec: solara.Reactive[RunSpec] | None = None,
    sepal_map: SepalMap | None = None,
    outcome: BuildOutcome | None = None,
    gee_interface: Any = None,
    sepal_client: Any = None,
    shown_layers: solara.Reactive[frozenset[IndicatorLayer]] | None = None,
    active_tab: int | None = None,
) -> list[TabDescriptor]:
    """The three workflow tabs, in display order.

    Every argument defaults to ``None`` so this is callable with no render
    context, letting ``tests/app/test_tabs.py`` pin tab order without a spec,
    map or outcome. The ``is not None`` guards below buy nothing at runtime --
    an inert element descriptor is built either way -- and exist only so
    ``mypy --strict`` narrows each argument before it reaches a component
    declaring a bare type. Deleting one leaves every test green and adds one
    mypy error.

    ``active_tab`` is threaded down only so ``OutputsPanel`` can tell whether
    its own tab is active; see that module for why that gates more than
    visibility.
    """
    maps = outcome.maps if outcome is not None else None
    ctx = outcome.ctx if outcome is not None else None

    aoi_content: list[object] = (
        [AoiStep(spec=spec, map_=sepal_map)] if spec is not None and sepal_map is not None else []
    )
    params_content: list[object] = (
        [ParamsPanel(spec=spec, outcome=outcome, gee_interface=gee_interface)]
        if spec is not None and outcome is not None
        else []
    )

    configuration_tabs = [
        TabDescriptor("aoi", msg("tabs.aoi"), "mdi-map-marker-check", aoi_content),
        TabDescriptor(
            ("run", "productivity", "land_cover", "soc"),
            msg("tabs.params"),
            "mdi-cogs",
            params_content,
        ),
    ]
    # Its own length, so the index cannot drift from the list below.
    outputs_index = len(configuration_tabs)

    outputs_content: list[object] = (
        [
            OutputsPanel(
                maps=maps,
                ctx=ctx,
                spec=spec.value,
                map_=sepal_map,
                gee_interface=gee_interface,
                sepal_client=sepal_client,
                shown_layers=shown_layers
                if shown_layers is not None
                else frozenset[IndicatorLayer](),
                is_active=active_tab == outputs_index,
            )
        ]
        if spec is not None
        else []
    )
    return [
        *configuration_tabs,
        # `tabs.results`, not `results.title`: one of this tab's sections IS
        # the ResultsPanel, so reusing that key would name the tab after its
        # own child.
        TabDescriptor(None, msg("tabs.results"), "mdi-chart-bar", outputs_content),
    ]


class _TabState(Enum):
    """Whether a tab is reachable, and whether what it holds is complete.
    Derived per render, never hand-assigned -- see ``_tab_state``."""

    LOCKED = "locked"
    INCOMPLETE = "incomplete"
    SATISFIED = "satisfied"


def _aoi_ready(spec: RunSpec) -> bool:
    """Whether an area of interest has actually been chosen.

    Asked of ``problems_for("aoi", ...)`` rather than ``spec.aoi is not
    None``: the step's own rules decide whether a selection is usable, and a
    second notion of "set" here would be one more thing to keep in sync.
    """
    return not any(problem.fatal for problem in problems_for("aoi", spec))


def _tab_state(tab: TabDescriptor, spec: RunSpec, has_maps: bool) -> _TabState:
    """Whether a tab is reachable, and whether what it holds is complete.

    **Every configuration tab but AOI is LOCKED until an AOI exists.** Each
    parameter describes how to compute something over an area, so with no area
    there is nothing to check them against. That lock is also what lets the
    AOI step stop repeating "Select an area of interest" (``app/steps/aoi.py``).

    Past that gate a tab is INCOMPLETE while ANY step it names owns a fatal
    problem: a single tab is the only signal the user has for everything
    folded behind it, so reading it as satisfied while one of four still
    fails would be a false all-clear. The outputs tab (``step is None``) is
    LOCKED until ``outcome.maps`` exists.

    Only LOCKED is drawn (as ``rv.Tab(disabled=...)``); the other two are kept
    apart because this is what would have to change if they were drawn again.
    """
    if tab.step is None:
        return _TabState.SATISFIED if has_maps else _TabState.LOCKED
    steps = (tab.step,) if isinstance(tab.step, str) else tab.step
    if "aoi" not in steps and not _aoi_ready(spec):
        return _TabState.LOCKED
    fatal = any(problem.fatal for step in steps for problem in problems_for(step, spec))
    return _TabState.INCOMPLETE if fatal else _TabState.SATISFIED


@solara.component
def WorkflowTabs(
    spec: solara.Reactive[RunSpec],
    sepal_map: SepalMap,
    outcome: BuildOutcome,
    shown_layers: solara.Reactive[frozenset[IndicatorLayer]],
    gee_interface: Any = None,
    sepal_client: Any = None,
) -> None:
    """The whole right-panel workflow: an ``rv.Tabs`` strip and its three tabs.

    ``rv.TabsItems`` hides inactive tabs client-side WITHOUT unmounting them,
    so ``AoiStep``'s draw control never runs its unmount cleanup on a tab
    switch and would stay on the map after the user leaves the AOI tab. The
    ``use_ref``-guarded effect below mirrors the active tab onto the map
    instead.
    """
    active_tab, set_active_tab = solara.use_state(0)

    tabs = workflow_tabs(
        spec=spec,
        sepal_map=sepal_map,
        outcome=outcome,
        gee_interface=gee_interface,
        sepal_client=sepal_client,
        shown_layers=shown_layers,
        active_tab=active_tab,
    )
    has_maps = outcome.maps is not None
    aoi_index = next(i for i, tab in enumerate(tabs) if tab.step == "aoi")

    dc_hidden = solara.use_ref(False)

    def _sync_draw_control_effect() -> None:
        dc_hidden.current = _sync_draw_control(
            sepal_map, active_tab == aoi_index, dc_hidden.current
        )

    solara.use_effect(_sync_draw_control_effect, [active_tab])

    # `grow` spreads three tabs across the panel's full 450px instead of
    # leaving them bunched at the left; `centered` is what keeps them centred
    # if a translation makes them narrow enough not to fill it. No
    # `show-arrows`: three tabs fit, and the overflow chevrons it adds are the
    # very thing the repo owner asked to be rid of.
    with rv.Tabs(v_model=active_tab, on_v_model=set_active_tab, grow=True, centered=True):
        for tab in tabs:
            # Vuetify draws a disabled tab (dimmed, not clickable) and refuses
            # to activate it, which is the whole of what the old hand-built
            # strip needed a `pointer-events: none` wrapper plus a re-check
            # inside its own click handler to achieve.
            rv.Tab(
                disabled=_tab_state(tab, spec.value, has_maps) is _TabState.LOCKED,
                children=[tab.title],
            )

    with rv.TabsItems(v_model=active_tab):
        for tab in tabs:
            rv.TabItem(children=list(tab.content))


def _sync_draw_control(map_: Any, aoi_active: bool, was_hidden: bool) -> bool:
    """Keep the AOI draw control on the map only while the AOI tab is active.

    Goes through ``add_control``/``remove_control`` directly, never
    ``dc.show()``/``dc.hide()`` -- those also wipe ``dc.data``, which would
    lose the drawn shape (same reasoning as the spatial-risk reference's own
    ``sync_draw_control_visibility``).

    ``was_hidden`` is what tells "removed by this function on the last tab
    switch" apart from "never added, because no DRAW method is selected yet"
    -- without it, returning to the AOI tab would unconditionally add the
    control even when the user never chose DRAW at all.

    The reference this mirrors also keys its own version on a project-load
    signal and a loading flag, because loading a saved project there can
    restore an AOI asynchronously and re-seed the control while another tab
    is active. This app has no project-load feature, and ``AoiStep`` passes
    no ``spec=`` into ``AoiView``, so ``AoiView``'s own restore-from-spec
    effect (the other source of a surprise re-add there) never fires here --
    the control can only move in response to the user picking a method on
    the AOI tab while it is actually visible. ``active_tab`` is therefore the
    only trigger this needs; keying on more would track state this app does
    not have.

    Returns:
        The new ``was_hidden`` for the caller to carry to the next call.
    """
    dc = getattr(map_, "dc", None)
    if map_ is None or dc is None:
        return was_hidden
    if aoi_active:
        if was_hidden and dc not in map_.controls:
            map_.add_control(dc)
        return False
    if dc in map_.controls:
        map_.remove_control(dc)
        return True
    return was_hidden
