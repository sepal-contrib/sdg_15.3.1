"""Class areas and the distribution chart.

The panel fetches, the domain decodes and builds the chart option, ipecharts
renders it. No statistics arithmetic lives here.

Follows ``docs/guides/solara-gee-patterns.md``'s Async Button Convention: the
task snapshots ``maps``/``ctx`` at click time instead of reading them live,
returns an outcome instead of mutating reactive state from inside itself, and
a ``solara.use_effect`` with the full dependency list mirrors that outcome
into the chart option and a toast.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import solara
from ipecharts import EChartsRawWidget
from pysepal.solara.components.task_button import TaskButtonComponent, use_task_button
from pysepal.solara.notifications import use_notifications

from app.message import msg
from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.indicator import IndicatorMaps
from sdg1531.enums import IndicatorLayer
from sdg1531.stats.api import fetch_areas_by_land_cover
from sdg1531.stats.decode import pivot_areas_by_land_cover
from sdg1531.stats.plots import distribution_option

__all__ = ("RESULTS_LAYER", "ResultsPanel")

#: The layer whose class areas this panel reports. Both calls below must use the
#: SAME value: `decode_areas_by_land_cover` names its class column `layer.value`
#: and `pivot_areas_by_land_cover` pivots on that name, so two different layers
#: here raise a KeyError inside pandas rather than showing the wrong chart.
#: 15.3.1 is the module's headline output, which is what the panel leads with.
RESULTS_LAYER = IndicatorLayer.INDICATOR_15_3_1


@dataclass(frozen=True, slots=True)
class _ResultsRequest:
    """An immutable snapshot of ``maps``/``ctx``, taken at click time."""

    maps: IndicatorMaps
    ctx: ExecutionContext


@dataclass(frozen=True, slots=True)
class _ResultsOutcome:
    """What ``_compute`` hands back -- the task never mutates reactive state."""

    option: dict[str, Any]


async def _compute(
    gee_interface: Any, notifications: Any, request: _ResultsRequest
) -> _ResultsOutcome:
    """Fetch one snapshot of class areas and build the chart option from it.

    ``request`` is a snapshot taken at click time (``ResultsPanel.start``),
    never a live read of ``maps``/``ctx`` -- the guide's rule
    against reading reactive inputs after a task has started.
    """
    with notifications.track(msg("results.compute"), total_steps=2) as task:
        task.step(msg("results.compute"))
        frame = await fetch_areas_by_land_cover(
            gee_interface, request.maps, request.ctx, layer=RESULTS_LAYER
        )
        task.step(msg("results.computed"))
        pivot = pivot_areas_by_land_cover(frame, RESULTS_LAYER)
        option = distribution_option(pivot, request.maps.resolved)
    return _ResultsOutcome(option=option)


@solara.component
def ResultsPanel(
    maps: IndicatorMaps | None,
    ctx: ExecutionContext | None,
    gee_interface: Any,
    is_open: bool = True,
) -> None:
    """``is_open`` used to say whether THIS panel's own accordion section (an
    ``rv.ExpansionPanel`` since task 27) was the one currently expanded; task
    28's move to flat sections removed the accordion, so it now says whether
    the merged outputs TAB itself (``app/tabs.py``'s ``WorkflowTabs``) is the
    one currently active -- see ``app/panels/outputs.py``'s module docstring
    for why that still gates more than visibility. The description this
    panel used to render itself (``solara.Markdown(msg("results.description"))``)
    now lives in its section's own header there too."""
    notifications = use_notifications()
    option: solara.Reactive[dict[str, Any] | None] = solara.use_reactive(None)
    current_maps = maps
    current_ctx = ctx

    task = solara.lab.use_task(
        _compute, dependencies=None, raise_error=False, prefer_threaded=False
    )

    def handle_task_state() -> None:
        if task.pending or task.cancelled:
            return
        if task.error:
            notifications.error(str(task.exception))
            return
        if task.finished and task.value is not None:
            # See MapLayersPanel's identical comment: solara's own `use_task`
            # overloads bind `R` straight to the task function's return type with
            # no special case for `async def`, so for an async task function
            # `Task[P, R].value` is typed as the `Coroutine` itself rather than
            # what it resolves to -- a stub gap, not a real ambiguity: at runtime
            # `use_task` awaits the coroutine and stores its result, never the
            # coroutine object.
            outcome = cast("_ResultsOutcome", task.value)
            option.value = outcome.option
            notifications.success(msg("results.computed"))

    # Unconditional, ahead of the `current_maps is None` guard below -- same
    # reason `use_memo` further down stays up here too: the number of hooks a
    # component calls must not depend on which branch a render takes.
    solara.use_effect(
        handle_task_state,
        [task.pending, task.finished, task.error, task.cancelled],
    )

    def start() -> None:
        # Snapshot both here, at click time -- not inside `_compute`, which the
        # guide's rule bans from reading live reactive inputs once it is running
        # as a background task. `maps` and `ctx` come from the same `BuildOutcome`
        # (`build_outcome` sets both together, never one without the other), so
        # this can't observe one set with the other still `None` in practice --
        # `start` is only ever wired to a button rendered when both are already
        # not-`None` below, but the guard is repeated so the closure stays total
        # rather than assuming its caller's care.
        if current_maps is not None and current_ctx is not None:
            task(
                gee_interface,
                notifications,
                _ResultsRequest(maps=current_maps, ctx=current_ctx),
            )

    # `use_task_button` is a hook by convention (its name), not just by what it
    # does, so it stays above the guard below along with everything else.
    btn_props = use_task_button(task, on_start=start)

    # `use_memo`, not a plain `if option.value is not None: EChartsRawWidget(...)`:
    # solara's hooks-order check flags a `use_*` hook called inside an `if` block
    # regardless of whether it precedes a return, so whether the widget exists at
    # all has to be decided INSIDE the memoised factory. Keyed on `option.value`
    # AND `is_open`, and gated on both: an `EChartsRawWidget` sizes its canvas
    # from its container's live dimensions at construction time and never
    # revisits that later, so building it while this section is collapsed (a
    # real case -- the async fetch above can finish after the user has already
    # expanded a DIFFERENT section) bakes in a zero-width canvas that reopening
    # this one does not fix. Verified in a real browser with a throwaway probe
    # (an `EChartsRawWidget` mounted via `solara.display()` inside an
    # `rv.ExpansionPanel`, driven by `pysepal/scripts/browser_probe.mjs`): built
    # while open, the canvas measured its real pixel size and kept it across a
    # collapse/reopen cycle; built while collapsed, it measured 100x500 (an
    # ECharts fallback, not the container's real width) and STAYED that size
    # after reopening. Gating on `is_open` too means the widget is always first
    # built during a render where its section is already the open one -- the
    # reopen itself is what re-runs this memo once `option.value` is already
    # sitting there waiting.
    def _build_chart() -> EChartsRawWidget | None:
        if option.value is None or not is_open:
            return None
        return EChartsRawWidget(option=option.value)

    chart = solara.use_memo(_build_chart, [option.value, is_open])

    if current_maps is None or current_ctx is None:
        solara.Markdown(msg("results.build_first"))
        return

    TaskButtonComponent(label=msg("results.compute"), **btn_props, small=True, block=True)

    # `solara.display`, not a declarative `EChartsRawWidget.element(...)`: ipecharts
    # 1.4.0 gives neither chart class an `.element()` factory. Called directly in
    # the render body here (not deferred into a `use_effect`) because
    # `solara/server/shell.py`'s `display_in_reacton_hook` only captures a
    # `display()` call into the reacton tree -- as a reconciled `Output(...)`
    # element, updated in place rather than duplicated -- while a render context is
    # active and not reconsolidating; an effect runs after that window closes, and
    # a version that called `solara.display` from one mounted NOTHING in a real
    # browser (verified: no `<canvas>` at all). Verified the reverse too: called
    # here, a real ECharts `<canvas>` painted with non-zero dimensions, and forcing
    # further re-renders left exactly one `<canvas>` in the DOM, not a second copy.
    if chart is not None:
        solara.display(chart)
