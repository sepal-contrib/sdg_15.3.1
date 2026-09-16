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
shape rather than transcribing it -- no prev/next buttons or jump dropdown,
since the strip alone already fits and already covers every required state
transition; those two extra controls are additional surface the brief did
not ask this app to carry.

Segment state is derived from what ``app/state.py`` already knows
(``problems_for``) and from ``outcome.maps``, never from a second,
hand-typed notion of "done" per step -- see ``_tab_state``.
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
from app.panels.exports import ExportsPanel
from app.panels.map_layers import MapLayersPanel
from app.panels.results import ResultsPanel
from app.panels.transitions import TransitionsPanel
from app.panels.zonal import ZonalPanel
from app.state import problems_for
from app.steps.aoi import AoiStep
from app.steps.land_cover import LandCoverStep
from app.steps.productivity import ProductivityStep
from app.steps.run import BuildOutcome, RunStep
from app.steps.soc import SocStep
from sdg1531.spec import RunSpec

__all__ = ("TabDescriptor", "WorkflowTabs", "workflow_tabs")


@dataclass(frozen=True, slots=True)
class TabDescriptor:
    """One workflow tab, in DISPLAY order.

    ``step`` is the ``app.state.STEP_PREFIXES`` key a configuration tab owns,
    so its segment can read its state off ``problems_for`` -- ``None`` for
    the five output tabs, which are gated by ``outcome.maps`` instead (see
    ``_tab_state``). Order lives in list position alone, same reason
    ``build_workflow_sections`` gave: nothing here has an ``id`` for a stray
    sort to key on.
    """

    step: str | None
    title: str
    icon: str
    content: list[object]


def workflow_tabs(
    spec: solara.Reactive[RunSpec] | None = None,
    sepal_map: SepalMap | None = None,
    outcome: BuildOutcome | None = None,
    gee_interface: Any = None,
    sepal_client: Any = None,
) -> list[TabDescriptor]:
    """The ten workflow tabs, in DISPLAY order: AOI -> Productivity -> Land
    cover -> SOC -> Run -> Layers -> Transitions -> Results -> Zonal ->
    Export (design decision A6, unchanged by this module's move out of
    ``steps_data`` and then out of ten separate ``right_panel_content``
    sections).

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
    ``ExportsPanel.spec``); measured by deleting a guard, which leaves every
    test green and produces one ``mypy`` error per guard removed.
    """
    maps = outcome.maps if outcome is not None else None
    ctx = outcome.ctx if outcome is not None else None

    aoi_content: list[object] = (
        [AoiStep(spec=spec, map_=sepal_map)] if spec is not None and sepal_map is not None else []
    )
    productivity_content: list[object] = [ProductivityStep(spec=spec)] if spec is not None else []
    # No `gee_interface is not None` guard: `LandCoverStep`'s own parameter already
    # defaults to `None` (`AssetSelectComponent` falls back to the session
    # interface), so there is no bare `Reactive[...]` for mypy to narrow here.
    land_cover_content: list[object] = (
        [LandCoverStep(spec=spec, gee_interface=gee_interface)] if spec is not None else []
    )
    soc_content: list[object] = [SocStep(spec=spec)] if spec is not None else []
    run_content: list[object] = (
        [RunStep(spec=spec, outcome=outcome)] if spec is not None and outcome is not None else []
    )
    # `ExportsPanel.spec` is a bare `RunSpec`, unlike every other panel's `maps`/
    # `ctx` (both already `X | None`) -- the one output tab that needs a guard.
    exports_content: list[object] = (
        [ExportsPanel(maps=maps, ctx=ctx, spec=spec.value, gee_interface=gee_interface)]
        if spec is not None
        else []
    )
    return [
        TabDescriptor("aoi", msg("step.aoi"), "mdi-map-marker-check", aoi_content),
        TabDescriptor(
            "productivity", msg("step.productivity"), "mdi-sprout-outline", productivity_content
        ),
        TabDescriptor("land_cover", msg("step.land_cover"), "mdi-terrain", land_cover_content),
        TabDescriptor("soc", msg("step.soc"), "mdi-layers-outline", soc_content),
        TabDescriptor("run", msg("step.run"), "mdi-play-circle-outline", run_content),
        TabDescriptor(
            None,
            msg("layers.title"),
            "mdi-layers",
            [MapLayersPanel(maps=maps, map_=sepal_map, gee_interface=gee_interface)],
        ),
        TabDescriptor(
            None,
            msg("transitions.title"),
            "mdi-transit-transfer",
            [TransitionsPanel(maps=maps, ctx=ctx, gee_interface=gee_interface)],
        ),
        TabDescriptor(
            None,
            msg("results.title"),
            "mdi-chart-bar",
            [ResultsPanel(maps=maps, ctx=ctx, gee_interface=gee_interface)],
        ),
        TabDescriptor(
            None,
            msg("zonal.title"),
            "mdi-table",
            [
                ZonalPanel(
                    maps=maps, ctx=ctx, gee_interface=gee_interface, sepal_client=sepal_client
                )
            ],
        ),
        TabDescriptor(None, msg("exports.title"), "mdi-export-variant", exports_content),
    ]


class _TabState(Enum):
    """Segment-strip visual state. Derived per render, never hand-assigned --
    see ``_tab_state``."""

    LOCKED = "locked"
    INCOMPLETE = "incomplete"
    SATISFIED = "satisfied"


def _tab_state(tab: TabDescriptor, spec: RunSpec, has_maps: bool) -> _TabState:
    """A configuration tab (``tab.step`` set) is INCOMPLETE while it owns a
    fatal problem and SATISFIED once it does not -- it is never LOCKED, since
    every configuration field is always editable. An output tab
    (``tab.step is None``) is LOCKED until ``outcome.maps`` exists and
    SATISFIED after -- the same gate ``is_runnable``/``build_outcome``
    already apply before Layers, Transitions, Results, Zonal or Export can
    show anything.

    Reads ``problems_for`` and ``has_maps`` -- the same predicates the steps
    and panels themselves already render against -- rather than a second,
    hand-typed roster of ten step states.
    """
    if tab.step is None:
        return _TabState.SATISFIED if has_maps else _TabState.LOCKED
    fatal = any(problem.fatal for problem in problems_for(tab.step, spec))
    return _TabState.INCOMPLETE if fatal else _TabState.SATISFIED


#: Incomplete / locked tones stay theme-neutral grey; the SATISFIED fill and
#: the active-tab ring derive from the live Vuetify "primary" colour at
#: render time (see ``_WorkflowSegments``) so the strip matches the app
#: accent in both light and dark mode.
_SEG_INCOMPLETE = "rgba(128, 128, 128, 0.28)"
_SEG_LOCKED = (
    "repeating-linear-gradient(90deg, rgba(128,128,128,0.30) 0 3px, rgba(128,128,128,0.10) 3px 6px)"
)


def _rgba(hex_color: str, alpha: float) -> str:
    """``#rrggbb`` -> ``rgba(r, g, b, alpha)`` (for the translucent active ring)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _seg_style(state: _TabState, primary: str, active: bool) -> str:
    """The 7px inner bar's style: fill by state, ring when active."""
    if state is _TabState.LOCKED:
        bg = f"background: {_SEG_LOCKED};"
    else:
        fill = primary if state is _TabState.SATISFIED else _SEG_INCOMPLETE
        bg = f"background: {fill};"
    ring = f" box-shadow: 0 0 0 2px {_rgba(primary, 0.55)};" if active else ""
    return f"width: 100%; height: 7px; border-radius: 3.5px; {bg}{ring}"


@solara.component
def _SegmentCell(tip: str, seg_style: str, locked: bool, on_activate: Callable[[], None]) -> None:
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

    The wrapper is a padded, transparent div (~21px tall) that owns the
    tooltip and the click; the 7px bar inside is purely visual, so the hit
    area stays usable.
    """

    def _handle_click(*_: object) -> None:
        if not locked:
            on_activate()

    lock_style = " pointer-events: none;" if locked else " cursor: pointer;"
    with rv.Html(
        tag="div",
        style_=f"flex: 1; padding: 7px 0;{lock_style}",
        attributes={"title": tip},
    ) as cell:
        rv.Html(tag="div", style_=seg_style)
    use_event(cell, "click", _handle_click)


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
                seg_style=_seg_style(state, primary, active=i == active_tab),
                locked=locked,
                on_activate=_bind(on_navigate, i),
            )


@solara.component
def WorkflowTabs(
    spec: solara.Reactive[RunSpec],
    sepal_map: SepalMap,
    outcome: BuildOutcome,
    gee_interface: Any = None,
    sepal_client: Any = None,
) -> None:
    """The whole right-panel workflow: the segment strip over the ten tabs.

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

    The same non-unmounting behaviour is a help for the two chart tabs
    (Results, Transitions): both call ``solara.display()`` directly in their
    render body (see ``app/panels/results.py``'s load-bearing comment on
    why), and a tab that stays mounted does not re-run that path on every
    switch -- verified in the browser, not merely assumed: mounting a chart,
    switching away and back leaves the same live ``<canvas>`` in place.
    """
    active_tab, set_active_tab = solara.use_state(0)

    tabs = workflow_tabs(
        spec=spec,
        sepal_map=sepal_map,
        outcome=outcome,
        gee_interface=gee_interface,
        sepal_client=sepal_client,
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
