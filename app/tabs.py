"""The right panel's workflow, as tabs.

The repo owner asked twice for the workflow to live in the right panel, and
separately for the steps to be tabs. ``page.py`` mounts this module's
``WorkflowTabs`` as ONE titleless right-panel section whose whole content is
that single component, the way ``spatial-risk-module``'s own ``WorkflowTabs``
(``gui/solara_app.py``) does.

**Tab labels are short, and live in their own ``tabs.*`` catalogue group.**
The strip has ~418px inside a 450px panel, and a tab is at least 90px wide.
Measured in a real browser, the three steps' own full titles come to 418px in
English -- exactly at the limit -- and 429px in Spanish, which tips Vuetify
into drawing its own overflow chevrons: the very control the repo owner asked
to be rid of. So the strip carries "AOI", "Parameters", "Results" rather than
"Area of interest" and friends. These keys belong to the tab strip alone;
each configuration step keeps its own full ``step.*`` title for the section
header it renders inside the PARAMS tab (``app/panels/params.py``).

**Navigation is plain ``rv.Tabs``.** It was not always: tasks 21-30 carried a
hand-built segment strip -- one coloured bar per tab, a ring on the active
one, three-character labels inside, prev/next chevrons beside it -- ported
from ``spatial-risk``'s ``gui/widget/pipeline_header.py``. That shape exists
there to fit TEN tabs into a 450px panel. This app no longer has ten: task 27
folded five output tabs into one, task 30 folded four configuration tabs into
another, and three tabs fit a standard tab strip with room to spare. The repo
owner, after using it: *"I didn't like the navigation buttons... let's just
use standard vuetify tabs.... remove the arrows as well"*. So the strip, its
theme-aware fills, its abbreviation catalogue (``tabs.abbrev.*``) and the
arrows (``tabs.previous``/``tabs.next``, and ``nav_targets``, which existed
only to feed them) are all gone, replaced by ``rv.Tabs`` + ``rv.Tab``.

``_tab_state`` survives that deletion because it was never about the strip's
styling: it is the derivation that says whether a tab is reachable at all, and
``rv.Tab(disabled=...)`` is how a standard tab strip expresses the same thing.
The Results tab stays unreachable until a build exists, exactly as before --
the difference is that Vuetify now draws "unreachable", instead of a
hand-written ``repeating-linear-gradient`` and a ``pointer-events: none``
wrapper that had to re-check itself in its own click handler.

**Tab order (design decision A6, twice superseded).** A6's ORDER -- AOI,
Productivity, Land cover, SOC, Run, then the outputs tab -- kept its shape
through the move into the right panel, then through two folds. Task 28 moved
the step long called "Run" to run FIRST among the configuration steps and
renamed it for what it actually owns, the overall assessment period
(``periods.overall``); ``app/steps/period_override.py`` shows the SOC and Land
cover steps inheriting that period, so it has to be chosen before them. Task
30 folded Assessment period, Productivity, Land cover and SOC into one PARAMS
tab in that same relative order (see ``app/panels/params.py``). Current order:
AOI -> PARAMS -> the merged outputs tab. Only catalogue titles and positions
moved; the Run step's own routing key (``STEP_PREFIXES["run"]`` in
``app/state.py``) is unchanged throughout.
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

    ``step`` is what ``_tab_state`` reads a tab's problems by, off
    ``app.state.problems_for``: a single ``STEP_PREFIXES`` key for a tab that
    owns one step (AOI), a tuple of them for a tab that folds several
    (PARAMS, task 30 -- ``("run", "productivity", "land_cover", "soc")``), or
    ``None`` for the merged outputs tab, which is gated by ``outcome.maps``
    instead (see ``_tab_state``). A tuple is never registered in
    ``STEP_PREFIXES`` itself -- that mapping's own coverage test
    (``tests/app/test_state.py``) requires every field be owned by EXACTLY one
    step, and a combined PARAMS entry would double-claim every field its four
    real steps already own. Order lives in list position alone, same reason
    ``build_workflow_sections`` gave: nothing here has an ``id`` for a stray
    sort to key on.
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
    """The three workflow tabs, in DISPLAY order: AOI -> PARAMS -> the merged
    outputs tab. See this module's docstring for how that order was reached.

    Every argument defaults to ``None`` so this is reachable with no render
    context at all -- calling a ``@solara.component`` function outside a
    render pass builds an inert element descriptor, never executes the
    component body, so ``tests/app/test_tabs.py`` can call
    ``workflow_tabs()`` bare to pin tab order (title, icon) without a real
    spec, map or outcome to hand it. Each tab's own content is built only
    once its required arguments are actually present, guarded with plain
    ``is not None`` checks -- calling a step or panel with ``None`` would not
    actually raise (an inert element descriptor is built either way, per the
    paragraph above), so this buys nothing at runtime. It exists solely so
    ``mypy --strict`` narrows each ``X | None`` argument away from ``None``
    before it reaches a component that declares a bare ``X`` parameter
    (``Reactive[RunSpec]`` for ``spec``, plain ``RunSpec`` for
    ``OutputsPanel.spec``); measured by deleting
    a guard, which leaves every test green and produces one ``mypy`` error per
    guard removed.

    ``active_tab`` is ``WorkflowTabs``'s own active-index state, threaded down
    only so ``OutputsPanel`` can tell whether ITS tab is the active one --
    see that module's docstring for the chart-mount trap this feeds. ``None``
    (the bare-callable default) means "no tab is active", which is also the
    right answer for the merged outputs tab specifically: with no render
    context there is no real active tab to speak of, and its two chart
    sections must not eagerly build against a container that may not exist.
    """
    maps = outcome.maps if outcome is not None else None
    ctx = outcome.ctx if outcome is not None else None

    aoi_content: list[object] = (
        [AoiStep(spec=spec, map_=sepal_map)] if spec is not None and sepal_map is not None else []
    )
    # `ParamsPanel.outcome` is a bare `BuildOutcome` (its own `RunStep`
    # section needs it), unlike `spec` -- the same mypy-narrowing reason
    # `OutputsPanel.spec` below needs its own guard.
    params_content: list[object] = (
        [ParamsPanel(spec=spec, outcome=outcome, gee_interface=gee_interface)]
        if spec is not None and outcome is not None
        else []
    )

    configuration_tabs = [
        TabDescriptor("aoi", msg("tabs.aoi"), "mdi-map-marker-check", aoi_content),
        # `step` names all four folded steps, in the order `param_sections()`
        # renders them -- `_tab_state` reads every one of them for this tab's
        # own state (see that function). "mdi-cogs": a settings-gear icon for
        # a tab that is now itself a settings panel, not any one step's own.
        TabDescriptor(
            ("run", "productivity", "land_cover", "soc"),
            msg("tabs.params"),
            "mdi-cogs",
            params_content,
        ),
    ]
    # The outputs tab always comes straight after the two configuration
    # tabs -- its index is this list's own length, not a second, hand-typed
    # literal that could silently drift from the return list below.
    outputs_index = len(configuration_tabs)

    # `OutputsPanel.spec` is a bare `RunSpec`, unlike every other argument
    # here -- the one tab that still needs this guard, for the same
    # mypy-narrowing reason it always did.
    outputs_content: list[object] = (
        [
            OutputsPanel(
                maps=maps,
                ctx=ctx,
                spec=spec.value,
                map_=sepal_map,
                gee_interface=gee_interface,
                sepal_client=sepal_client,
                # `OutputsPanel.shown_layers` already defaults to an
                # internally-owned frozenset when no `Reactive` is given (the
                # bare `workflow_tabs()` call this docstring describes), so
                # `None` here means exactly that -- not a narrowing guard like
                # the one above.
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
        # `tabs.results`, not `results.title`: the merged tab holds several
        # sections and one of them IS the ResultsPanel, so reusing that key
        # would name the tab after its own child. The section keeps
        # `results.title` (now "Distribution", what it actually charts --
        # class areas per land cover type); the tab carries its own key.
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

    Asked of ``problems_for("aoi", ...)`` rather than of ``spec.aoi is not
    None``: the AOI step's own rules are what decide whether a selection is
    usable, and a second, hand-written notion of "set" here would be one more
    thing to keep in sync with them.
    """
    return not any(problem.fatal for problem in problems_for("aoi", spec))


def _tab_state(tab: TabDescriptor, spec: RunSpec, has_maps: bool) -> _TabState:
    """**A configuration tab other than AOI is LOCKED until an AOI exists.**
    The repo owner asked for this after using the app: *"if the AOI is not
    set, PARAMS should be deactivated"*. It is not merely cosmetic -- every
    parameter in PARAMS describes how to compute something over an area, and
    with no area there is nothing any of them can be checked against, so the
    tab would present four sections of settings that cannot produce a run.
    Making it unreachable is also what lets the AOI step stop repeating
    "Select an area of interest" as an error (see ``app/steps/aoi.py``): the
    locked tab says the same thing, at the moment it matters.

    Past that gate, a configuration tab is INCOMPLETE while ANY step it names
    owns a fatal problem, and SATISFIED only once NONE of them do. AOI names
    one step; PARAMS (task 30) names four (``("run", "productivity",
    "land_cover", "soc")``), and the combining rule is the same either way:
    "satisfied" means every step behind it is, because a single tab is the
    only signal a user has for everything folded behind it -- reading it as
    satisfied while one of the four still has a fatal problem would be
    reporting a false all-clear. The merged outputs tab (``tab.step is None``)
    is LOCKED until ``outcome.maps`` exists and SATISFIED after -- the same
    gate ``is_runnable``/``build_outcome`` already apply before any of its
    sections can show anything.

    The AOI tab itself is never LOCKED, and the asymmetry is the point: it is
    the one tab that is always reachable, because it is where the thing every
    other tab waits for gets chosen.

    Reads ``problems_for`` and ``has_maps`` -- the same predicates the steps
    and panels themselves already render against -- rather than a second,
    hand-typed roster of step states. A single step and several are the same
    code path here (a 1-tuple would compute identically to the bare string
    case), so AOI is not special-cased.

    LOCKED is the state ``WorkflowTabs`` disables a tab for. INCOMPLETE and
    SATISFIED are not distinguished visually any more (the segment strip that
    drew them differently is gone -- see the module docstring); the
    distinction survives here because ``_tab_state`` is also what would have
    to change if it were ever drawn again, and collapsing it into a bare
    ``is_locked`` predicate would throw away a derivation the panels' own
    ``ProblemsAlert`` already agrees with.
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
    """The whole right-panel workflow: a standard ``rv.Tabs`` strip and the
    three tabs it navigates.

    ``rv.TabsItems`` hides inactive tabs client-side WITHOUT unmounting them.
    That is a problem for ``app/steps/aoi.py``'s ``AoiStep``, which mounts
    ``AoiView`` against the shared ``sepal_map``: its draw control (toolbar +
    editable drawn shape) never gets a chance to run its own unmount cleanup
    on a tab switch, so it would stay on the map after the user moves away
    from the AOI tab -- the exact bug the spatial-risk reference's own
    ``WorkflowTabs`` documents and works around. The ``use_ref``-guarded
    effect below mirrors the active tab onto the map the same way; see
    ``_sync_draw_control`` for why it needs no dependency beyond
    ``active_tab`` in THIS app.

    The same non-unmounting behaviour is a help for the merged outputs tab's
    two chart sections (Results, Transitions): both call ``solara.display()``
    directly in their render body (see ``app/panels/results.py``'s
    load-bearing comment on why), and a tab that stays mounted does not
    re-run that path on every switch -- verified in the browser, not merely
    assumed: mounting a chart, switching away and back leaves the same live
    ``<canvas>`` in place.
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
