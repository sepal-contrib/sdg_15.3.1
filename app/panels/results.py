"""Class areas and the distribution chart.

The panel fetches, the domain decodes and builds the chart option, ipecharts
renders it. No statistics arithmetic lives here.

Follows ``docs/guides/solara-gee-patterns.md``'s Async Button Convention: the
task snapshots ``maps.value``/``ctx.value`` at click time instead of reading
them live, returns an outcome instead of mutating reactive state from inside
itself, and a ``solara.use_effect`` with the full dependency list mirrors that
outcome into the chart option and a toast.
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
    never a live read of ``maps.value``/``ctx.value`` -- the guide's rule
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
    maps: solara.Reactive[IndicatorMaps | None],
    ctx: solara.Reactive[ExecutionContext | None],
    gee_interface: Any,
) -> None:
    notifications = use_notifications()
    option: solara.Reactive[dict[str, Any] | None] = solara.use_reactive(None)
    current_maps = maps.value
    current_ctx = ctx.value

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
        # Snapshot both reactives here, at click time -- not inside `_compute`,
        # which the guide's rule bans from reading live reactive inputs once it
        # is running as a background task. `maps` and `ctx` are set by two
        # separate assignments in `RunStep.on_build`, so a render can observe
        # one set with the other still `None`; `start` is only ever wired to a
        # button rendered when both are already not-`None` below, but the guard
        # is repeated so the closure stays total rather than assuming its
        # caller's care.
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
    # so a re-render with an unchanged option does not rebuild the widget.
    chart = solara.use_memo(
        lambda: None if option.value is None else EChartsRawWidget(option=option.value),
        [option.value],
    )

    # No `solara.Markdown(msg("results.description"))` here: `page.py`'s section
    # dict already carries that same string as the right-panel section's own
    # `description`, which `MapApp` renders under the section title. Rendering
    # it a second time here duplicated the sentence on screen for the Layers
    # panel (Task 10); this panel drops it up front instead.
    if current_maps is None or current_ctx is None:
        solara.Markdown(msg("results.build_first"))
        return

    TaskButtonComponent(label=msg("results.compute"), **btn_props)

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
