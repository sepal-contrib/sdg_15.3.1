"""Land cover transitions and the sankey chart.

The panel fetches, the domain builds the chart option, ipecharts renders it.
No statistics arithmetic lives here.

A near-copy of ``results.py`` -- same shape, same click-time snapshot, same
outcome-returning task, same ``use_effect``/``cast`` pattern, same chart
mount. See that module's docstring and inline comments for why each piece is
built the way it is; this one differs only in which fetch/option pair it
calls and in taking no ``layer=`` argument, because a transition is a
property of the land-cover pair rather than of one indicator layer.
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
from sdg1531.stats.api import fetch_transition_areas
from sdg1531.stats.plots import sankey_option

__all__ = ("TransitionsPanel",)


@dataclass(frozen=True, slots=True)
class _TransitionsRequest:
    """An immutable snapshot of ``maps``/``ctx``, taken at click time."""

    maps: IndicatorMaps
    ctx: ExecutionContext


@dataclass(frozen=True, slots=True)
class _TransitionsOutcome:
    """What ``_compute`` hands back -- the task never mutates reactive state."""

    option: dict[str, Any]


async def _compute(
    gee_interface: Any, notifications: Any, request: _TransitionsRequest
) -> _TransitionsOutcome:
    """Fetch one snapshot of transition areas and build the chart option from it.

    ``request`` is a snapshot taken at click time (``TransitionsPanel.start``),
    never a live read of ``maps``/``ctx`` -- the guide's rule against
    reading reactive inputs after a task has started.
    """
    with notifications.track(msg("transitions.compute"), total_steps=2) as task:
        task.step(msg("transitions.compute"))
        frame = await fetch_transition_areas(gee_interface, request.maps, request.ctx)
        task.step(msg("transitions.computed"))
        option = sankey_option(frame, request.maps.resolved)
    return _TransitionsOutcome(option=option)


@solara.component
def TransitionsPanel(
    maps: IndicatorMaps | None,
    ctx: ExecutionContext | None,
    gee_interface: Any,
    is_open: bool = True,
) -> None:
    """``is_open``: see ``ResultsPanel``'s identical parameter -- same
    chart-mount trap, same fix, now keyed on the merged outputs tab's own
    active state rather than an accordion section. The description this
    panel used to render itself now lives in its section's own header
    (``app/panels/outputs.py``)."""
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
            # See ResultsPanel's identical comment: solara's own `use_task`
            # overloads bind `R` straight to the task function's return type with
            # no special case for `async def`, so for an async task function
            # `Task[P, R].value` is typed as the `Coroutine` itself rather than
            # what it resolves to -- a stub gap, not a real ambiguity: at runtime
            # `use_task` awaits the coroutine and stores its result, never the
            # coroutine object.
            outcome = cast("_TransitionsOutcome", task.value)
            option.value = outcome.option
            notifications.success(msg("transitions.computed"))

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
                _TransitionsRequest(maps=current_maps, ctx=current_ctx),
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
        solara.Markdown(msg("transitions.build_first"))
        return

    TaskButtonComponent(label=msg("transitions.compute"), **btn_props, small=True, block=True)

    # `solara.display`, not a declarative element: ipecharts gives no
    # `.element()` factory. Called in the render body, not an effect -- solara
    # only captures a `display()` into the reacton tree while a render context
    # is active, and from an effect it mounts nothing at all.
    if chart is not None:
        solara.display(chart)
