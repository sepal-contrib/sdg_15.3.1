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

import contextlib
from dataclasses import dataclass
from typing import Any, cast

import solara
from ipecharts import EChartsRawWidget
from pysepal.solara import use_theme_dark
from pysepal.solara.components.task_button import TaskButtonComponent, use_task_button
from pysepal.solara.notifications import use_notifications

from app.message import msg
from app.panels.chart_theme import themed_option
from app.panels.staleness import use_discard_on_new_run
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

    def discard_stale_chart() -> None:
        # `maps` is a different run: the chart on screen is a picture of the
        # PREVIOUS one, under a heading that now describes this one. Cancel
        # first -- a fetch started under the old run would otherwise finish
        # after this and write its stale option straight back into the
        # reactive just cleared.
        with contextlib.suppress(RuntimeError):
            if task.pending:
                task.cancel()
        option.value = None

    use_discard_on_new_run(maps, discard_stale_chart)

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

    # `use_memo`, not `if option.value is not None: EChartsRawWidget(...)`:
    # solara flags a `use_*` hook inside an `if`, so whether the widget exists
    # at all is decided INSIDE the factory. Keyed on `is_open` too because an
    # `EChartsRawWidget` measures its canvas once, at construction -- built
    # while hidden it bakes a 100x500 fallback that reopening never fixes.
    # Themed here rather than in the fetch: the option stored is the domain's,
    # and the theme can flip long after the fetch finished.
    dark = use_theme_dark()

    def _build_chart() -> EChartsRawWidget | None:
        if option.value is None or not is_open:
            return None
        return EChartsRawWidget(option=themed_option(option.value, dark))

    chart = solara.use_memo(_build_chart, [option.value, is_open, dark])

    if current_maps is None or current_ctx is None:
        solara.Markdown(msg("results.build_first"))
        return

    TaskButtonComponent(label=msg("results.compute"), **btn_props, small=True, block=True)

    # `solara.display`, not a declarative element: ipecharts gives no
    # `.element()` factory. Called in the render body, not an effect -- solara
    # only captures a `display()` into the reacton tree while a render context
    # is active, and from an effect it mounts nothing at all.
    if chart is not None:
        solara.display(chart)
