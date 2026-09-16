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

from dataclasses import dataclass
from typing import Any, cast

import solara
from ipecharts import EChartsRawWidget
from pysepal.solara.components.task_button import TaskButtonComponent, use_task_button
from pysepal.solara.notifications import use_notifications

from app.message import msg
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
) -> None:
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

    # `use_memo`, not a plain `if option.value is not None: EChartsRawWidget(...)`:
    # solara's hooks-order check flags a `use_*` hook called inside an `if` block
    # regardless of whether it precedes a return, so whether the widget exists at
    # all has to be decided INSIDE the memoised factory. Keyed on `option.value`
    # so a re-render with an unchanged option does not rebuild the widget.
    chart = solara.use_memo(
        lambda: None if option.value is None else EChartsRawWidget(option=option.value),
        [option.value],
    )

    # No `solara.Markdown(msg("transitions.description"))` here: `page.py`'s
    # section dict renders no `description` for this panel either, since the
    # panel would otherwise duplicate the sentence on screen -- see
    # `ResultsPanel`'s identical comment.
    if current_maps is None or current_ctx is None:
        solara.Markdown(msg("transitions.build_first"))
        return

    TaskButtonComponent(label=msg("transitions.compute"), **btn_props)

    # `solara.display`, called directly in the render body, not deferred into a
    # `use_effect` -- see `ResultsPanel`'s comment on this exact call for why:
    # `solara/server/shell.py`'s `display_in_reacton_hook` only reconciles a
    # `display()` call into the reacton tree while a render context is active,
    # and a version that deferred this into an effect once mounted NOTHING in a
    # real browser.
    if chart is not None:
        solara.display(chart)
