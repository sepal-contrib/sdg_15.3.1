"""Adding the computed layers to the map, one row per layer.

The seven layers come from ``IndicatorMaps.layers()``; this panel never decides
which layers exist, what they are called, or how they are coloured. Colours
come from the domain palette so the map and the exported assets agree. Names
come from :func:`layer_name` -- ``ClassifiedLayer.label`` is the layer's raw
snake id (frozen under decision D9; the domain's own docstring says the
translated display label is the app layer's job).

A table replaces the earlier single "show everything" button: each row adds or
removes its own layer. The shown set is never read back from
``map_.find_layer`` -- the map's live widget state changes without telling
Solara, so a row driven from it would not re-render when it did. It lives in
a ``solara.Reactive`` instead, threaded down from ``page.py`` (see
``MapLayersPanel``'s own ``shown`` docstring) so the same set drives the
floating legend (``app/panels/legend.py``) too, not a second, independent
notion of "on the map".

Adding a layer is GEE work (it fetches a map id), so it follows
``docs/guides/solara-gee-patterns.md``'s Async Button Convention: one
``use_task`` for the whole component, parameterised by which layer it is
currently drawing, with a row's spinner driven by comparing its id against the
in-flight one. NOT one task per row -- that would call ``use_task`` a number
of times that depends on ``maps.layers()``, a hook inside a loop. Removing is
synchronous and local, so it needs no task.

One task also means one layer can draw at a time: clicking a second row's
Add while the first is still in flight does not queue it, it REPLACES it
(the same ``task(...)`` call that started the first now starts the second).
The abandoned layer never lands on the map and no row ends up wrongly marked
shown, so this was never a correctness bug -- but the first row simply
reverted to "Add" with no toast, which read as the click having done
nothing. Every OTHER row's Add is disabled (``external_busy``, see
``_LayerRow``) while one is pending, so the interaction cannot be started
rather than being started and silently dropped -- weighed against seven
one-or-two-second adds becoming serial, which seemed the smaller cost.

Task 20 made ``maps`` a derivation of the run spec: change the spec, and
``maps`` is a new object describing a different run. Every tile this panel
already drew is then from the run BEFORE it -- the same silently-wrong-data
failure Task 20 exists to kill, reappearing on the map instead of in a panel.
The effect keyed on ``maps`` below clears them.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

import reacton.ipyvuetify as rv
import solara
from pysepal.solara.components.task_button import TaskButtonComponent
from pysepal.solara.notifications import use_notifications
from reacton.ipyvue import use_event

from app.message import msg
from sdg1531.engine.indicator import ClassifiedLayer, IndicatorMaps
from sdg1531.enums import IndicatorLayer
from sdg1531.tables import DEGRADATION_COLORS

__all__ = ("MapLayersPanel", "layer_name", "layer_vis_params")


def layer_vis_params(layer_id: IndicatorLayer) -> dict[str, Any]:
    """SEPAL-convention visualization for one layer.

    ``[1:]`` drops the NoData entry: the legacy viz is min=1..max=3 over the
    three classified colours, and index 0 is the unclassified background.
    """
    colours = list(DEGRADATION_COLORS.values())
    if layer_id is IndicatorLayer.PRODUCTIVITY_PERFORMANCE:
        return {"min": 1, "max": 2, "palette": colours[1:3]}
    return {"min": 1, "max": 3, "palette": colours[1:]}


def layer_name(layer_id: IndicatorLayer) -> str:
    """Translated display name for one layer.

    ``ClassifiedLayer.label`` is ``id.value`` -- a stable snake id, not a
    display string. The catalogue key is named after that same value, so
    every ``IndicatorLayer`` member resolves through it with no separate,
    hand-typed id-to-name mapping to keep in sync with the enum.
    """
    return str(msg(f"layers.names.{layer_id.value}"))


@dataclass(frozen=True, slots=True)
class _AddOutcome:
    """What ``_add_layer`` hands back -- the task never notifies itself."""

    layer_id: IndicatorLayer


async def _add_layer(map_: Any, layer_id: IndicatorLayer, layer: ClassifiedLayer) -> _AddOutcome:
    """Draw one layer onto the map.

    ``layer_id``/``layer`` are a snapshot taken at click time
    (``MapLayersPanel.start``), never a live read of ``maps`` -- the guide's
    rule against reading reactive inputs after a task has started.
    ``key=layer_id.value`` is what makes a second add of the same layer
    replace it instead of accumulating another copy.
    """
    # add_ee_layer_async, NOT asyncio.to_thread(add_ee_layer, ...). Drawing an
    # EE layer fetches a map id, so it is GEE work, and the rule for GEE work
    # is to await the library's own *_async method. A to_thread worker runs
    # outside the kernel context, which is how it loses the session-backed
    # interface this map was built with.
    await map_.add_ee_layer_async(
        layer.image.select(layer.band),
        layer_vis_params(layer_id),
        layer_name(layer_id),
        key=layer_id.value,
    )
    return _AddOutcome(layer_id=layer_id)


def _bind_add(
    start: Callable[[IndicatorLayer, ClassifiedLayer], None],
    layer_id: IndicatorLayer,
    layer: ClassifiedLayer,
) -> Callable[[], None]:
    """A stably-typed zero-arg closure over one row's layer -- see
    ``app/tabs.py``'s ``_bind`` for why this is a named function rather than a
    default-argument lambda."""

    def _start() -> None:
        start(layer_id, layer)

    return _start


def _bind_remove(
    remove: Callable[[IndicatorLayer], None], layer_id: IndicatorLayer
) -> Callable[[], None]:
    def _remove() -> None:
        remove(layer_id)

    return _remove


@solara.component
def _RemoveButton(on_remove: Callable[[], None]) -> None:
    """Its own component so ``use_event`` attaches unconditionally at ITS OWN
    top level -- called only from the ``is_shown`` branch of ``_LayerRow``,
    which is fine (mounting a whole child component conditionally is normal
    reconciliation); calling ``use_event`` itself directly inside that branch
    is not (rules of hooks: the caller's OWN hook count would then flip
    between 0 and 1 across a re-render of the SAME row instance, each time
    ``is_shown`` changes)."""
    remove_btn = rv.Btn(children=[msg("layers.remove")], small=True, block=True, outlined=True)

    def _handle_click(*_: object) -> None:
        on_remove()

    use_event(remove_btn, "click", _handle_click)


@solara.component
def _LayerRow(
    name: str,
    is_shown: bool,
    is_pending: bool,
    is_busy_elsewhere: bool,
    on_add: Callable[[], None],
    on_remove: Callable[[], None],
    on_cancel: Callable[[], None],
) -> None:
    """One table row: the layer's name, and its own add/remove action.

    Its own component, called once per layer inside ``MapLayersPanel``'s loop
    over ``maps.layers()`` -- a python list whose length is data-dependent,
    so no hook may be called directly at that outer loop's level (rules of
    hooks). ``_LayerRow`` itself calls none directly either: which of
    ``_RemoveButton``/``TaskButtonComponent`` it mounts is decided by
    ``is_shown``, but both are whole child components, each with its own
    stable hook count, so branching on which one to mount does not touch
    ``_LayerRow``'s.

    ``is_busy_elsewhere`` -- another row's add in flight, this one's not --
    reaches ``TaskButtonComponent`` as ``external_busy``: disabled Add, same
    as its own docstring's "child component loading" case. Without it, a
    click here would abandon the OTHER row's add task (one component-level
    ``use_task``, so starting this one cancels it) with no toast and no
    explanation on either row -- disabling is what turns a click that does
    nothing into a click that cannot be made.
    """
    with rv.Html(tag="tr"):
        rv.Html(tag="td", children=[name])
        with rv.Html(tag="td"):
            if is_shown:
                _RemoveButton(on_remove=on_remove)
            else:
                TaskButtonComponent(
                    label=msg("layers.add"),
                    running=is_pending,
                    external_busy=is_busy_elsewhere,
                    on_start=on_add,
                    on_cancel=on_cancel,
                    small=True,
                    block=True,
                )


@solara.component
def MapLayersPanel(
    maps: IndicatorMaps | None,
    map_: Any,
    gee_interface: Any,
    shown: solara.Reactive[frozenset[IndicatorLayer]] | frozenset[IndicatorLayer] = frozenset[
        IndicatorLayer
    ](),
) -> None:
    """``gee_interface`` is accepted for parity with the other right-panel
    sections (``page.py`` passes the same three objects to each one) but goes
    unused here: ``map_.add_ee_layer_async`` already carries the session-backed
    interface the map itself was constructed with.

    ``shown`` follows ``solara.use_reactive``'s own flexible-argument shape: a
    plain value (the default, and every test that does not care) makes this
    panel own its state exactly as it always has; a ``Reactive`` -- ``page.py``
    passes one, shared with ``MapLegend`` -- makes the set visible to that
    sibling component instead of staying this panel's private copy.

    The description this panel used to render itself now lives in its
    section's own header (``app/panels/outputs.py``).
    """
    notifications = use_notifications()

    # `shown_reactive.set` -- unlike `use_state`'s own setter, which this
    # replaced -- takes a plain value, not an updater callable, so every
    # update below reads `.value` fresh rather than closing over a snapshot.
    # `Reactive` is a stable, persistent object (the same one across this
    # component's renders, and across renders of the sibling `MapLegend` that
    # shares it), so a fresh `.value` read from inside a later callback is
    # never stale the way a captured render-time snapshot would be.
    shown_reactive = solara.use_reactive(shown)
    shown_ids = shown_reactive.value
    pending_id, set_pending_id = solara.use_state(cast("IndicatorLayer | None", None))

    task = solara.lab.use_task(
        _add_layer, dependencies=None, raise_error=False, prefer_threaded=False
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
            outcome = cast("_AddOutcome", task.value)
            shown_reactive.value = shown_reactive.value | {outcome.layer_id}
            notifications.success(msg("layers.added", name=layer_name(outcome.layer_id)))

    # Unconditional, ahead of the `maps is None` return below: the number of
    # hooks a component calls must stay the same on every render of it, and
    # that guard is exactly the kind of thing that would otherwise make it
    # differ between the "not built yet" and "built" renders of the same
    # panel instance.
    solara.use_effect(
        handle_task_state,
        [task.pending, task.finished, task.error, task.cancelled],
    )

    def cancel() -> None:
        if task.pending:
            with contextlib.suppress(RuntimeError):
                task.cancel()

    def clear_stale_layers() -> None:
        # `maps` just became a different run (or stopped being runnable at
        # all): cancel whatever this panel is still drawing from the
        # PREVIOUS one, and take every layer this panel put on the map back
        # off, rather than leaving old-run tiles shown next to -- or instead
        # of -- the new run's.
        cancel()
        for layer_id in shown_ids:
            map_.remove_layer(layer_id.value, none_ok=True)
        shown_reactive.value = frozenset()

    # Keyed on `maps` alone -- identity/equality of the whole `IndicatorMaps`,
    # never one of its fields, is what "a different run" means here (see
    # `page.py`'s `outcome` comment on why `==` is the right comparison for a
    # frozen dataclass built fresh per run). Fires on the first render too
    # (nothing to remove: `shown_ids` is still empty) and again when `maps`
    # becomes `None` (the spec is no longer runnable) -- both are required by
    # the task, not only the "changed to a different runnable spec" case.
    solara.use_effect(clear_stale_layers, [maps])

    def start(layer_id: IndicatorLayer, layer: ClassifiedLayer) -> None:
        # Snapshot both here, at click time -- not inside `_add_layer`, which
        # the guide's rule bans from reading live reactive inputs once it is
        # running as a background task.
        set_pending_id(layer_id)
        task(map_, layer_id, layer)

    def remove(layer_id: IndicatorLayer) -> None:
        map_.remove_layer(layer_id.value, none_ok=True)
        shown_reactive.value = shown_reactive.value - {layer_id}

    if maps is None:
        solara.Markdown(msg("layers.build_first"))
        return

    with rv.SimpleTable(dense=True):
        with rv.Html(tag="thead"), rv.Html(tag="tr"):
            rv.Html(tag="th", children=[msg("layers.columns.name")])
            rv.Html(tag="th", children=[msg("layers.columns.action")])
        with rv.Html(tag="tbody"):
            for layer_id, layer in maps.layers().items():
                _LayerRow(
                    name=layer_name(layer_id),
                    is_shown=layer_id in shown_ids,
                    is_pending=task.pending and pending_id == layer_id,
                    is_busy_elsewhere=task.pending and pending_id != layer_id,
                    on_add=_bind_add(start, layer_id, layer),
                    on_remove=_bind_remove(remove, layer_id),
                    on_cancel=cancel,
                )
