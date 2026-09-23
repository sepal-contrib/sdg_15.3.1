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

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

import reacton.ipyvuetify as rv
import solara
from pysepal.mapping.sepal_map import SepalMap
from reacton.ipyvue import use_event

from app.message import msg
from app.panels.outputs import OutputsPanel
from app.panels.params import ParamsPanel
from app.state import problems_for
from app.steps.aoi import AoiStep
from app.steps.run import BuildOutcome
from sdg1531.enums import IndicatorLayer
from sdg1531.spec import RunSpec

__all__ = (
    "NAV_BAR_HEIGHT",
    "NavButton",
    "TabDescriptor",
    "WorkflowFooter",
    "WorkflowTabs",
    "tab_reachable",
    "workflow_tabs",
)


#: The footer bar's height in px. Taller than the 28px ``small`` gives a
#: button, because this one spans the whole panel: at button height a
#: full-width bar reads as a sliver of chrome rather than a place to click.
NAV_BAR_HEIGHT = 34

#: One half of the footer bar. Given the bar's own height even when it holds
#: no button, so an empty track still reserves its half rather than
#: collapsing and letting the other button slide across.
_TRACK_STYLE = f"flex: 1 1 0; min-height: {NAV_BAR_HEIGHT}px;"


def _go_to(active_tab: solara.Reactive[int], index: int) -> Callable[[], None]:
    """A zero-arg closure over one tab index -- a named function rather than a
    default-argument lambda, whose type ``mypy --strict`` cannot pin against
    the ``Callable[[], None]`` :func:`NavButton` declares (the same reason
    ``app/panels/map_layers.py`` has ``_bind_toggle``)."""

    def _go() -> None:
        active_tab.value = index

    return _go


@solara.component
def NavButton(
    label: str,
    tooltip: str,
    icon: str,
    enabled: bool,
    on_click: Callable[[], None],
    leading_icon: bool = False,
) -> None:
    """One step of the workflow navigation, in either direction.

    ``block`` + ``tile``: square corners and full width of whatever track it
    is given, so the bar fills the footer edge to edge. ``small`` with them,
    not ``large``, because pysepal's right-panel button-sizing convention
    applies here exactly as it does to every other button in this app --
    ``tests/app/test_button_sizing.py`` pins both halves. ``height`` overrides
    only the 28px ``small`` would otherwise impose: this is a bar spanning the
    panel, and at button height it read as a sliver rather than a footer. The
    compact type ``small`` also sets is kept.

    ``secondary``, not ``primary``: the bar should be findable at the bottom
    of a long panel, which plain grey was not, without taking the colour the
    app spends on the work itself (Build, Export, a drawn layer).
    ``depressed`` drops the shadow a raised button would cast onto the panel
    edge it sits flush against.

    ``disabled`` while the destination is locked, with the reason as its
    hover title, because a button that silently does nothing is worse than
    one that says why it cannot. A direction that does not EXIST is not drawn
    at all -- see :func:`WorkflowFooter`.

    A disabled button reacts to nothing -- no hover tint, no ripple -- which
    is Vuetify's own ``.v-btn--disabled { pointer-events: none }`` doing its
    job. That took a pysepal fix to get back: ``MapApp.vue``'s
    ``.v-navigation-drawer .v-btn`` rule is specificity 0,2,0 against
    Vuetify's 0,1,0 and was handing every disabled control in the panel its
    pointer events back, so a dead button still lit up under the cursor.

    ``rv.Btn`` + ``use_event``, not ``solara.Button``: the same missing
    return-type annotation in solara's own stubs that
    ``app/steps/period_override.py`` avoids ``solara.Checkbox`` over.
    """

    def _handle_click(*_: object) -> None:
        if enabled:
            on_click()

    glyph = rv.Icon(left=leading_icon, right=not leading_icon, small=True, children=[icon])
    btn = rv.Btn(
        block=True,
        tile=True,
        small=True,
        depressed=True,
        color="secondary",
        height=NAV_BAR_HEIGHT,
        disabled=not enabled,
        attributes={"title": tooltip, "aria-label": tooltip},
        children=[glyph, label] if leading_icon else [label, glyph],
    )
    use_event(btn, "click", _handle_click)


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

    Navigation is NOT here. It used to append a button to each configuration
    tab's own content, which put it at the end of whatever that tab happened
    to render; it now lives in :func:`WorkflowFooter`, outside the tabs
    entirely, so a tab's content is only ever the step it is for.
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


def tab_reachable(tabs: list[TabDescriptor], index: int, spec: RunSpec, has_maps: bool) -> bool:
    """Whether tab ``index`` can be activated at all.

    The same question :func:`_tab_state` answers for ``rv.Tab(disabled=...)``,
    asked by :func:`WorkflowFooter` of the tab a button would land on. One
    rule, two readers: a footer button that enabled while the tab it targets
    was still disabled would look like a dead control, and an index outside
    the strip is simply not reachable.
    """
    if not 0 <= index < len(tabs):
        return False
    return _tab_state(tabs[index], spec, has_maps) is not _TabState.LOCKED


@solara.component
def WorkflowFooter(
    active_tab: solara.Reactive[int],
    spec: RunSpec,
    outcome: BuildOutcome,
) -> None:
    """Back and Next, pinned below the panel's scrolling content.

    The repo owner's report was that a tab's bottom was a dead end: *"if I'm
    in parameters, I finish, I scroll all the way down, I don't know what to
    do next, I have to go back to the top and find the results tab"*. Putting
    the buttons inside a tab only moved the problem -- they still sat at the
    end of a long scroll. This renders into ``MapApp``'s ``right_panel_footer``
    slot instead, which is outside the scroll area, so it is on screen
    wherever the content above it happens to be.

    **A direction that does not exist is not drawn**: no Back on the first
    tab, no Next on the last. The alternative -- drawing it disabled -- spends
    half the bar on a control that can never do anything, and "this is the
    first step" is already obvious from the tab strip. A direction that
    exists but is LOCKED is a different case and still renders, disabled,
    because there the user does have something to fix and the tooltip says
    what.

    **The bar is always two half-width tracks**, and a direction that does not
    exist leaves its own track EMPTY rather than letting the other one grow
    into it. So Back always occupies the left half and Next the right half,
    wherever in the workflow the reader is: the one button on the first tab
    sits exactly where it will sit on the second, instead of jumping from
    centre to right as soon as Back appears beside it. No gap between the
    tracks: they meet at the middle and run flush to both panel edges
    (pysepal's footer slot adds no padding of its own), so the row reads as
    one bar rather than a pair of floating controls.
    """
    tabs = workflow_tabs()
    current = active_tab.value
    has_maps = outcome.maps is not None

    with rv.Html(tag="div", class_="d-flex"):
        with rv.Html(tag="div", style_=_TRACK_STYLE):
            if current > 0:
                enabled = tab_reachable(tabs, current - 1, spec, has_maps)
                NavButton(
                    label=msg("nav.back"),
                    tooltip=msg("nav.back_to", target=tabs[current - 1].title),
                    icon="mdi-arrow-left",
                    leading_icon=True,
                    enabled=enabled,
                    on_click=_go_to(active_tab, current - 1),
                )
        with rv.Html(tag="div", style_=_TRACK_STYLE):
            if current < len(tabs) - 1:
                enabled = tab_reachable(tabs, current + 1, spec, has_maps)
                NavButton(
                    label=msg("nav.forward"),
                    tooltip=msg("nav.next", target=tabs[current + 1].title)
                    if enabled
                    # Two different reasons share one greyed-out button, and
                    # "nothing happens" is the answer that helps nobody.
                    else msg("nav.locked_params" if current == 0 else "nav.locked_results"),
                    icon="mdi-arrow-right",
                    enabled=enabled,
                    on_click=_go_to(active_tab, current + 1),
                )


@solara.component
def WorkflowTabs(
    spec: solara.Reactive[RunSpec],
    sepal_map: SepalMap,
    outcome: BuildOutcome,
    shown_layers: solara.Reactive[frozenset[IndicatorLayer]],
    active_tab: solara.Reactive[int],
    gee_interface: Any = None,
    sepal_client: Any = None,
    inline_footer: bool = False,
) -> None:
    """The whole right-panel workflow: an ``rv.Tabs`` strip and its three tabs.

    ``rv.TabsItems`` hides inactive tabs client-side WITHOUT unmounting them,
    so ``AoiStep``'s draw control never runs its unmount cleanup on a tab
    switch and would stay on the map after the user leaves the AOI tab. The
    ``use_ref``-guarded effect below mirrors the active tab onto the map
    instead.

    ``active_tab`` is owned by ``app/page.py``, not by a ``use_state`` here,
    because :func:`WorkflowFooter` reads and writes the same index from the
    other side of the panel -- it renders into ``MapApp``'s footer slot, a
    separate subtree from this one. Same reason ``shown_layers`` is threaded
    down rather than owned here.

    ``inline_footer`` renders the footer at the bottom of this subtree instead
    of the panel's, for a pysepal without the slot (see ``app/page.py``). It
    scrolls with the content there, which is exactly the problem the slot was
    added to fix -- it exists so the app still navigates on the published
    pysepal, and comes out when the floor is raised.
    """
    tabs = workflow_tabs(
        spec=spec,
        sepal_map=sepal_map,
        outcome=outcome,
        gee_interface=gee_interface,
        sepal_client=sepal_client,
        shown_layers=shown_layers,
        active_tab=active_tab.value,
    )
    has_maps = outcome.maps is not None
    aoi_index = next(i for i, tab in enumerate(tabs) if tab.step == "aoi")

    dc_hidden = solara.use_ref(False)

    def _sync_draw_control_effect() -> None:
        dc_hidden.current = _sync_draw_control(
            sepal_map, active_tab.value == aoi_index, dc_hidden.current
        )

    solara.use_effect(_sync_draw_control_effect, [active_tab.value])

    # `grow` spreads three tabs across the panel's full 450px instead of
    # leaving them bunched at the left; `centered` is what keeps them centred
    # if a translation makes them narrow enough not to fill it. No
    # `show-arrows`: three tabs fit, and the overflow chevrons it adds are the
    # very control this strip exists to avoid.
    # `background_color="transparent"`, and the same on `TabsItems` below.
    # Vuetify paints both the strip (`.v-tabs-bar`) and the content
    # (`.v-tabs-items`) with the theme's SURFACE colour, which is not the
    # navigation drawer's: measured in the browser, rgb(30,30,30) over the
    # panel's rgb(26,26,26). That lighter rectangle read as a card sitting
    # behind the AOI controls -- pysepal's own `demo_apps/solara_map_app` has
    # no tabs, so its panel content sits straight on the drawer and showed the
    # difference.
    with rv.Tabs(
        v_model=active_tab.value,
        on_v_model=active_tab.set,
        grow=True,
        centered=True,
        background_color="transparent",
    ):
        for tab in tabs:
            # Vuetify draws a disabled tab (dimmed, not clickable) and refuses
            # to activate it, which is the whole of what the old hand-built
            # strip needed a `pointer-events: none` wrapper plus a re-check
            # inside its own click handler to achieve.
            rv.Tab(
                disabled=_tab_state(tab, spec.value, has_maps) is _TabState.LOCKED,
                children=[tab.title],
            )

    with rv.TabsItems(v_model=active_tab.value, style_="background-color: transparent;"):
        for tab in tabs:
            rv.TabItem(children=list(tab.content))

    if inline_footer:
        WorkflowFooter(active_tab=active_tab, spec=spec.value, outcome=outcome)


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
