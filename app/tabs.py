"""The right panel's workflow, as tabs.

The repo owner asked twice for the workflow to live in the right panel, and
separately for the ten steps to be tabs. ``spatial-risk-module`` /
``spatial-risk-main-branch``'s own ``WorkflowTabs`` (``gui/solara_app.py``)
does both at once: one titleless right-panel section whose content is a
single component, which owns the active-tab state and swaps content with
``rv.TabsItems``. This module is that component for this app.

Ten labelled ``rv.Tabs`` do not fit a 450px panel -- the reference solves
this by drawing no ``rv.Tabs`` strip at all (``grep -n "rv.Tabs\\b"`` returns
nothing in either checkout). Navigation is a separate custom widget instead:
a segment strip of thin bars, one per tab, coloured by state, with a ring on
the active one (``gui/widget/pipeline_header.py``). This module adapts that
shape rather than transcribing it -- no jump dropdown, since a strip this
short does not need one to be usable. It DOES now carry the reference's
prev/next arrows (below), which task 21 originally left out; the repo owner
asked for them directly after using the app ("can we add arrows to the tabs
component? so I can easily navigate back-and-forth?").

Task 27 also folded the five output tabs (Layers, Transitions, Results,
Zonal, Export) into ONE tab, ``app/panels/outputs.py``'s ``OutputsPanel`` --
the repo owner's own words: "all the computation buttons ... should be in
the same tab, like with multiple sections, similarly as se.plan does". Task
28 replaced that tab's own ``rv.ExpansionPanels`` accordion with flat, headed
sections (see that module's docstring); the panel is still ONE tab here,
just one whose own content changed shape.

**Task 30 did the same fold a second time, to the other four configuration
tabs.** The repo owner, after using the six-tab layout task 28 left behind:
*"I now think we could have just three tabs, AOI, PARAMS, Result"* ...
*"in params, we should have sections, as you just did in the results."*
Assessment period, Productivity, Land cover and SOC collapse into one PARAMS
tab, built the identical way task 28 built the outputs tab -- flat, headed
sections, no accordion -- see ``app/panels/params.py``'s own docstring. The
panel has THREE tabs now: AOI, PARAMS, and the merged outputs tab.
``_tab_state``'s LOCKED/INCOMPLETE/SATISFIED derivation is unchanged in
shape; it now reads across FOUR steps' worth of ``problems_for`` for the
PARAMS tab's own chip, the same way it always read across one merged output
tab's ``outcome.maps`` instead of five (see ``TabDescriptor.step`` and
``_tab_state`` below for how a tab now names either one step or several).

Segment state is derived from what ``app/state.py`` already knows
(``problems_for``) and from ``outcome.maps``, never from a second,
hand-typed notion of "done" per step -- see ``_tab_state``. ``nav_targets``
(ported from the reference's own ``pipeline_header.nav_targets``) walks that
same derived state to find the nearest non-locked tab on each side of the
active one, so "next" skips straight past a still-locked outputs tab instead
of landing on it.

**Tab order (design decision A6) changed again here, task 28, by the repo
owner's direct request, and task 30 preserves what task 28 chose.** A6's own
ORDER -- AOI, Productivity, Land cover, SOC, Run, then the merged outputs
tab -- had already survived one supersession (its PLACEMENT moved into the
right panel; the order itself did not change then). Task 28 changed it: the
step long called "Run" owns no input but the overall assessment period
(``periods.overall``) -- Task 20 deleted its Build button, and task 28
renamed it for what remains, "Assessment period" (``PER`` in the segment
strip until task 30 merged it away; the owner's own question started this:
"the 'RUN' is only date? should we change that 'RUN' by 'DAT'???") -- and
moved it to run FIRST among the configuration steps. That period is also
what task 28's own ``app/steps/period_override.py`` shows the SOC and Land
cover steps inheriting FROM -- a user sitting on either step needs the
period already chosen, or the "inherited window" text they show is empty or
misleading. The step everything else derives from has to come before them.
Task 30 folds Assessment period, Productivity, Land cover and SOC into one
PARAMS tab's sections WITHOUT reordering them -- ``app/panels/params.py``'s
own docstring repeats this reasoning at the section level, since it is the
module that now actually orders them. New tab order: AOI -> PARAMS (itself
ordered Assessment period -> Productivity -> Land cover -> SOC) -> the
merged outputs tab. Only the catalogue TITLE/DESCRIPTION and the tab's
position moved over these two tasks -- the Run step's own routing key
(``STEP_PREFIXES["run"]`` in ``app/state.py``) is unchanged throughout;
renaming the key itself would ripple into ``app/state.py`` and the domain's
own field names for no gain.
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

__all__ = ("TabDescriptor", "WorkflowTabs", "nav_targets", "workflow_tabs")


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
    outputs tab. Design decision A6's own order was unchanged by this
    module's move out of ``steps_data``, then out of ten separate
    ``right_panel_content`` sections, then -- task 27 -- by folding the last
    five of those ten into one tab (see ``app/panels/outputs.py``), then --
    task 28 -- by moving the step long called "Run" to run first among the
    configuration steps and renaming its catalogue title, and now -- task 30
    -- by folding the remaining four configuration tabs (Assessment period,
    Productivity, Land cover, SOC) into one PARAMS tab (see
    ``app/panels/params.py``), in that same relative order; see this
    module's own docstring for why each move happened.

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
    ``ExportsPanel.spec`` deep inside ``OutputsPanel``); measured by deleting
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
        TabDescriptor("aoi", msg("step.aoi"), "mdi-map-marker-check", aoi_content),
        # `step` names all four folded steps, in the order `param_sections()`
        # renders them -- `_tab_state` reads every one of them for this tab's
        # own chip (see that function). "mdi-cogs": a settings-gear icon for
        # a tab that is now itself a settings panel, not any one step's own.
        TabDescriptor(
            ("run", "productivity", "land_cover", "soc"),
            msg("params.title"),
            "mdi-cogs",
            params_content,
        ),
    ]
    # The outputs tab always comes straight after the two configuration
    # tabs -- its index is this list's own length, not a second, hand-typed
    # literal that could silently drift from the return list below.
    outputs_index = len(configuration_tabs)

    # `OutputsPanel.spec` is a bare `RunSpec` (its own `ExportsPanel` section
    # needs it), unlike every other argument here -- the one tab that still
    # needs this guard, for the same mypy-narrowing reason it always did.
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
        # `outputs.title`, not `results.title`: the merged tab holds five
        # sections and one of them IS the ResultsPanel, so reusing that key
        # named the tab after its own child. The section keeps `results.title`
        # (now "Distribution", what it actually charts -- class areas per land
        # cover type); the tab carries its own key.
        TabDescriptor(None, msg("outputs.title"), "mdi-chart-bar", outputs_content),
    ]


class _TabState(Enum):
    """Segment-strip visual state. Derived per render, never hand-assigned --
    see ``_tab_state``."""

    LOCKED = "locked"
    INCOMPLETE = "incomplete"
    SATISFIED = "satisfied"


def _tab_state(tab: TabDescriptor, spec: RunSpec, has_maps: bool) -> _TabState:
    """A configuration tab (``tab.step`` set) is INCOMPLETE while ANY step it
    names owns a fatal problem, and SATISFIED only once NONE of them do -- it
    is never LOCKED, since every configuration field is always editable. AOI
    names one step; PARAMS (task 30) names four (``("run", "productivity",
    "land_cover", "soc")``), and the combining rule is the same either way:
    "satisfied" means every step behind the chip is, because a single chip is
    the only signal a user watching the segment strip has for everything
    folded behind it -- reading it as satisfied while one of the four still
    has a fatal problem would be reporting a false all-clear. The merged
    outputs tab (``tab.step is None``) is LOCKED until ``outcome.maps``
    exists and SATISFIED after -- the same gate ``is_runnable``/
    ``build_outcome`` already apply before any of its five sections (Layers,
    Transitions, Results, Zonal, Export) can show anything.

    Reads ``problems_for`` and ``has_maps`` -- the same predicates the steps
    and panels themselves already render against -- rather than a second,
    hand-typed roster of step states. A single step and several are the same
    code path here (a 1-tuple would compute identically to the bare string
    case), so AOI is not special-cased.
    """
    if tab.step is None:
        return _TabState.SATISFIED if has_maps else _TabState.LOCKED
    steps = (tab.step,) if isinstance(tab.step, str) else tab.step
    fatal = any(problem.fatal for step in steps for problem in problems_for(step, spec))
    return _TabState.INCOMPLETE if fatal else _TabState.SATISFIED


def nav_targets(
    tabs: list[TabDescriptor], active: int, spec: RunSpec, has_maps: bool
) -> tuple[int | None, int | None]:
    """The nearest non-``LOCKED`` tab on each side of ``active`` -- ported
    from spatial-risk's own ``pipeline_header.nav_targets``, same "skip a
    whole locked run" reasoning: since task 27, the outputs tab is one LOCKED
    block until a build exists, so ``active_tab`` sitting on the last
    configuration tab (PARAMS, since task 30 folded the other four
    configuration tabs into it) must not let "next" land there, it must find
    nothing (``None``) past it instead. Reads ``_tab_state`` -- the same
    derivation the segment strip itself is coloured by -- rather than a
    second, hand-typed notion of which tabs are reachable.
    """
    states = [_tab_state(tab, spec, has_maps) for tab in tabs]
    prev_t = next((i for i in range(active - 1, -1, -1) if states[i] is not _TabState.LOCKED), None)
    next_t = next(
        (i for i in range(active + 1, len(states)) if states[i] is not _TabState.LOCKED), None
    )
    return prev_t, next_t


#: Incomplete / locked tones stay theme-neutral grey; the SATISFIED fill and
#: the active-tab ring derive from the live Vuetify "primary" colour at
#: render time (see ``_WorkflowSegments``) so the strip matches the app
#: accent in both light and dark mode.
_SEG_INCOMPLETE = "rgba(128, 128, 128, 0.28)"
_SEG_LOCKED = (
    "repeating-linear-gradient(90deg, rgba(128,128,128,0.30) 0 3px, rgba(128,128,128,0.10) 3px 6px)"
)

#: The repo owner asked for the segments to be "a little bigger" and to carry
#: a short label -- 28px is tall enough to hold the 3-character abbreviation
#: readably; the old bars were 7px, purely decorative, and held no text.
_CHIP_HEIGHT = 28


def _rgba(hex_color: str, alpha: float) -> str:
    """``#rrggbb`` -> ``rgba(r, g, b, alpha)`` (for the translucent active ring)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _seg_style(state: _TabState, primary: str, active: bool) -> str:
    """The chip's style: fill by state, ring when active, same as before --
    plus the sizing and typography its new abbreviation label needs.

    Text colour is never a fixed value: SATISFIED fills with the theme's own
    ``primary`` colour, dark enough in both light and dark mode that white
    text reads on it (the same assumption Vuetify's own ``v-chip
    color="primary"`` makes); INCOMPLETE/LOCKED fill with a translucent grey
    over the page background, so ``color: inherit`` -- the theme's own
    foreground colour -- already has the contrast it needs without a second
    hardcoded value to keep in sync with the theme.
    """
    if state is _TabState.LOCKED:
        bg = f"background: {_SEG_LOCKED};"
        color = "inherit"
    else:
        fill = primary if state is _TabState.SATISFIED else _SEG_INCOMPLETE
        bg = f"background: {fill};"
        color = "#fff" if state is _TabState.SATISFIED else "inherit"
    ring = f" box-shadow: 0 0 0 2px {_rgba(primary, 0.55)};" if active else ""
    return (
        f"width: 100%; height: {_CHIP_HEIGHT}px; border-radius: 6px; {bg}"
        f"display: flex; align-items: center; justify-content: center; "
        f"color: {color}; font-size: 11px; font-weight: 600; letter-spacing: 0.02em;"
        f"{ring}"
    )


@solara.component
def _SegmentCell(
    tip: str, label: str, seg_style: str, locked: bool, on_activate: Callable[[], None]
) -> None:
    """One cell of the segment strip.

    Its own component so the ``rv.use_event`` click hook is called exactly
    once at this component's top level, never inside the caller's loop over
    tabs (rules of hooks -- the same reason ``pipeline_header.py``'s
    ``_SegmentCell`` exists as its own component). A locked cell is inert
    twice over: ``pointer-events: none`` in its own style (there is no
    Vuetify ``disabled`` prop to inherit one from -- this is a plain
    ``rv.Html`` div, not a list item), *and* the handler below re-checks --
    because the hook must be attached on every render regardless of state,
    the no-op has to live inside the handler rather than around it.

    ``label`` is the tab's up-to-three-character abbreviation, rendered
    inside the chip; ``tip`` (the tab's own full title) stays the hover
    tooltip on the WRAPPER, same as before -- the abbreviation is an
    addition to that, never a replacement for it.

    The wrapper is a padded, transparent div that owns the tooltip and the
    click; the coloured chip inside is what carries the label, sizing and
    state -- the hit area is the whole wrapper, not just the chip.
    """

    def _handle_click(*_: object) -> None:
        if not locked:
            on_activate()

    lock_style = " pointer-events: none;" if locked else " cursor: pointer;"
    with rv.Html(
        tag="div",
        style_=f"flex: 1; padding: 4px 2px;{lock_style}",
        attributes={"title": tip},
    ) as cell:
        rv.Html(tag="div", style_=seg_style, children=[label])
    use_event(cell, "click", _handle_click)


@solara.component
def _NavArrow(
    icon_name: str,
    label: str,
    disabled: bool,
    on_activate: Callable[[], None],
    color: str | None = None,
) -> None:
    """One prev/next arrow. Its own component so the ``use_event`` click hook
    attaches at a stable top level -- same convention as ``_SegmentCell``
    above and ``map_layers.py``'s ``_RemoveButton``. ``solara.Button`` would
    build this in one call, but (like ``solara.Row``/``Column``) it has no
    return-type annotation in solara's own stubs, so ``mypy --strict``
    refuses to call it; a plain ``rv.Btn`` is fully typed.
    """
    # `label` is the only affordance this control has: an icon-only button
    # carries no text, so without it the arrow is unreadable to a screen
    # reader and unexplained on hover. `_SegmentCell` above solves the same
    # problem the same way.
    btn = rv.Btn(
        icon=True,
        small=True,
        disabled=disabled,
        color=color,
        attributes={"title": label, "aria-label": label},
        children=[rv.Icon(children=[icon_name])],
    )

    def _handle_click(*_: object) -> None:
        on_activate()

    use_event(btn, "click", _handle_click)


def _tab_abbrev(tab: TabDescriptor) -> str:
    """The tab's up-to-three-character segment-chip label -- an ADDITION to
    the full-title tooltip ``_SegmentCell`` already carries, never a
    replacement for it (the owner's own words: "show inside them a
    max-three-char reference").

    Keyed off ``tab.step``: a single ``STEP_PREFIXES`` name for a
    single-step tab (AOI) is also its own catalogue key, ``"outputs"`` stands
    in for the merged tab's own ``None``, and ``"params"`` stands in for a
    tuple (task 30's combined PARAMS tab) -- a tuple has no ``STEP_PREFIXES``
    name of its own to reuse (see ``TabDescriptor``'s own docstring for why
    one is never registered), so this is the one case that does not fall
    straight out of ``tab.step``. A real ``msg()`` lookup either way, not a
    hand-typed dict: these are user-facing strings, and a translator may
    legitimately need to change a three-letter English contraction that
    reads wrong in Spanish or French.
    """
    if tab.step is None:
        key = "outputs"
    elif isinstance(tab.step, str):
        key = tab.step
    else:
        key = "params"
    return str(msg(f"tabs.abbrev.{key}"))


def _bind(on_navigate: Callable[[int], None], index: int) -> Callable[[], None]:
    """A zero-arg closure over ``index`` -- a plain default-argument lambda
    (``lambda i=i: ...``) is how the reference does this, but its type is
    awkward for ``mypy --strict`` to pin down against the ``Callable[[],
    None]`` ``_SegmentCell.on_activate`` expects, so this names the closure
    explicitly instead.
    """

    def _activate() -> None:
        on_navigate(index)

    return _activate


@solara.component
def _WorkflowSegments(
    tabs: list[TabDescriptor],
    active_tab: int,
    spec: RunSpec,
    has_maps: bool,
    on_navigate: Callable[[int], None],
) -> None:
    """The segment strip: one cell per tab, coloured by ``_tab_state``."""
    # Filled segments and the active-tab ring use the app's theme "primary"
    # accent, so the strip matches every other `color="primary"` control.
    themes = solara.lab.theme.themes
    primary = themes.dark.primary if solara.lab.use_dark_effective() else themes.light.primary

    # A flex `rv.Html` div, not `solara.Row`: the latter is untyped in solara's
    # own stubs (no return annotation), which `mypy --strict` refuses to call.
    with rv.Html(
        tag="div", style_="display: flex; gap: 4px; align-items: center; padding: 6px 8px 2px;"
    ):
        for i, tab in enumerate(tabs):
            state = _tab_state(tab, spec, has_maps)
            locked = state is _TabState.LOCKED
            _SegmentCell(
                tip=tab.title,
                label=_tab_abbrev(tab),
                seg_style=_seg_style(state, primary, active=i == active_tab),
                locked=locked,
                on_activate=_bind(on_navigate, i),
            )


@solara.component
def WorkflowTabs(
    spec: solara.Reactive[RunSpec],
    sepal_map: SepalMap,
    outcome: BuildOutcome,
    shown_layers: solara.Reactive[frozenset[IndicatorLayer]],
    gee_interface: Any = None,
    sepal_client: Any = None,
) -> None:
    """The whole right-panel workflow: the segment strip, the prev/next
    arrows, and the three tabs they navigate.

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

    _WorkflowSegments(
        tabs=tabs,
        active_tab=active_tab,
        spec=spec.value,
        has_maps=has_maps,
        on_navigate=set_active_tab,
    )

    prev_t, next_t = nav_targets(tabs, active_tab, spec.value, has_maps)

    def _activate_prev() -> None:
        if prev_t is not None:
            set_active_tab(prev_t)

    def _activate_next() -> None:
        if next_t is not None:
            set_active_tab(next_t)

    # A flex `rv.Html` div, not `solara.Row`: see `_WorkflowSegments`'s identical
    # comment -- `solara.Row` has no return annotation in solara's own stubs,
    # which `mypy --strict` refuses to call.
    nav_style = "display: flex; justify-content: space-between; padding: 0 4px 4px;"
    with rv.Html(tag="div", style_=nav_style):
        # Disabled, never hidden, with no target: a disabled control tells the
        # user where they are (first/last reachable tab); a vanishing one would
        # make the strip jump. `disabled=` alone would already stop a real
        # browser click, but `_activate_prev`/`_activate_next`'s own `is not
        # None` recheck is what actually stops a raw `fire_event` too -- the
        # same double-guard `_SegmentCell.on_activate` uses for a locked
        # segment, for the same reason (the click handler is what a test
        # drives directly).
        _NavArrow(
            icon_name="mdi-chevron-left",
            label=msg("tabs.previous"),
            disabled=prev_t is None,
            on_activate=_activate_prev,
        )
        _NavArrow(
            icon_name="mdi-chevron-right",
            label=msg("tabs.next"),
            disabled=next_t is None,
            on_activate=_activate_next,
            color="primary",
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
