"""Adding the computed layers to the map.

The seven layers come from ``IndicatorMaps.layers()``; this panel never decides
which layers exist, what they are called, or how they are coloured. Colours come
from the domain palette so the map and the exported assets agree.

Follows ``docs/guides/solara-gee-patterns.md``'s Async Button Convention: the
task snapshots ``maps.value`` at click time instead of reading it live, returns
an outcome instead of notifying from inside itself, and a ``solara.use_effect``
with the full dependency list mirrors that outcome into a toast.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

import solara
from pysepal.solara.components.task_button import TaskButtonComponent, use_task_button
from pysepal.solara.notifications import use_notifications

from app.message import msg
from sdg1531.engine.indicator import ClassifiedLayer, IndicatorMaps
from sdg1531.enums import IndicatorLayer
from sdg1531.tables import DEGRADATION_COLORS

__all__ = ("MapLayersPanel", "layer_vis_params")


def layer_vis_params(layer_id: IndicatorLayer) -> dict[str, Any]:
    """SEPAL-convention visualization for one layer.

    ``[1:]`` drops the NoData entry: the legacy viz is min=1..max=3 over the
    three classified colours, and index 0 is the unclassified background.
    """
    colours = list(DEGRADATION_COLORS.values())
    if layer_id is IndicatorLayer.PRODUCTIVITY_PERFORMANCE:
        return {"min": 1, "max": 2, "palette": colours[1:3]}
    return {"min": 1, "max": 3, "palette": colours[1:]}


@dataclass(frozen=True, slots=True)
class _LayersOutcome:
    """What ``_add_layers`` hands back -- the task never notifies itself."""

    count: int


async def _add_layers(
    map_: Any,
    notifications: Any,
    layers: Mapping[IndicatorLayer, ClassifiedLayer],
) -> _LayersOutcome:
    """Draw one snapshot of layers onto the map.

    ``layers`` is a snapshot taken at click time (``MapLayersPanel.start``),
    never a live read of ``maps.value`` -- the guide's rule against reading
    reactive inputs after a task has started. ``key=layer_id.value`` is what
    makes a second click replace each layer instead of accumulating another
    copy of it: a stable, locale-invariant identity, independent of
    ``layer.label`` (used below only as the display name and the progress-step
    text), which idempotency should not hinge on.
    """
    with notifications.track(msg("layers.show"), total_steps=len(layers)) as task:
        for layer_id, layer in layers.items():
            task.step(layer.label)
            # add_ee_layer_async, NOT asyncio.to_thread(add_ee_layer, ...).
            # Drawing an EE layer fetches a map id, so it is GEE work, and the
            # rule for GEE work is to await the library's own *_async method.
            # A to_thread worker runs outside the kernel context, which is how
            # it loses the session-backed interface this map was built with.
            await map_.add_ee_layer_async(
                layer.image.select(layer.band),
                layer_vis_params(layer_id),
                layer.label,
                key=layer_id.value,
            )
    return _LayersOutcome(count=len(layers))


@solara.component
def MapLayersPanel(
    maps: solara.Reactive[IndicatorMaps | None],
    map_: Any,
    gee_interface: Any,
) -> None:
    """``gee_interface`` is accepted for parity with the other right-panel
    sections (``page.py`` passes the same three objects to each one) but goes
    unused here: ``map_.add_ee_layer_async`` already carries the session-backed
    interface the map itself was constructed with.
    """
    notifications = use_notifications()
    current_maps = maps.value

    task = solara.lab.use_task(
        _add_layers, dependencies=None, raise_error=False, prefer_threaded=False
    )

    def handle_task_state() -> None:
        if task.pending or task.cancelled:
            return
        if task.error:
            notifications.error(str(task.exception))
            return
        if task.finished and task.value is not None:
            # solara's own `use_task` overloads (tasks.py) bind `R` straight to the
            # task function's return type with no special case for `async def`, so
            # for an async task function `Task[P, R].value` is typed as the
            # `Coroutine` itself rather than what it resolves to -- a stub gap, not
            # a real ambiguity: at runtime `use_task` awaits the coroutine and
            # stores its result, never the coroutine object.
            outcome = cast("_LayersOutcome", task.value)
            notifications.success(msg("layers.shown", count=outcome.count))

    # Unconditional, ahead of the `current_maps is None` return below: the
    # number of hooks a component calls must stay the same on every render of
    # it, and that guard is exactly the kind of thing that would otherwise
    # make it differ between the "not built yet" and "built" renders of the
    # same panel instance.
    solara.use_effect(
        handle_task_state,
        [task.pending, task.finished, task.error, task.cancelled],
    )

    def start() -> None:
        # Snapshot `maps.value` here, at click time -- not inside `_add_layers`,
        # which the guide's rule bans from reading live reactive inputs once it
        # is running as a background task. Guarded again (`start` is only ever
        # wired to a button rendered when `current_maps` is not None below) so
        # the closure stays total rather than assuming its caller's care.
        if current_maps is not None:
            task(map_, notifications, current_maps.layers())

    # `use_task_button` is a hook by convention (its name), not just by what it
    # does -- solara's rules-of-hooks check flags it the same as `use_task`
    # above if it moves below the conditional return, so it stays up here too.
    btn_props = use_task_button(task, on_start=start)

    solara.Markdown(msg("layers.description"))

    if current_maps is None:
        solara.Markdown(msg("layers.build_first"))
        return

    TaskButtonComponent(label=msg("layers.show"), **btn_props)
