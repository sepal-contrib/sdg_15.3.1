"""The computed layers: one row per layer, each with its own show and export.

The seven layers come from ``IndicatorMaps.layers()``; this panel never decides
which layers exist, what they are called, or how they are coloured. A row
carries an eye toggle and an export icon, and the export dialog is pysepal's
(``use_export_dialog`` + ``ExportDialog``), opened preselected on that row's
own layer.

**Every layer is clipped to the AOI and self-masked before it is drawn**
(``app/panels/layer_style.py``). Without both, an unclipped classified layer
covers the globe in the palette's first colour. The legacy did the same in
``display_maps`` (``component/scripts/run_15_3_1.py:113-144``). This is DISPLAY
only -- the domain graphs are untouched (decision D9) and the export path keeps
its own ``.clip(ctx.feature_collection)``, so nothing here reaches the parity
harness. One deliberate difference: the legacy clipped a non-ADMIN AOI to
``geom.bounds()``, painting its whole bounding rectangle; this clips to
``ctx.geometry`` for every arm.

The shown set is never read back from ``map_.find_layer``: the map's widget
state changes without telling Solara, so a row driven from it would not
re-render. It lives in a ``solara.Reactive`` threaded down from ``page.py``, so
the same set drives the floating legend (``app/panels/legend.py``).

Adding a layer is GEE work, so it follows one ``use_task`` for the whole
component, parameterised by which layer is drawing -- NOT one task per row,
which would be a hook inside a data-dependent loop. One task also means one
layer draws at a time: every other row's eye is disabled while one is pending,
so a second click cannot silently replace the first.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

import ee
import reacton.ipyvuetify as rv
import solara
from pysepal.solara.components.export import ExportSource
from pysepal.solara.components.export_dialog import ExportDialog
from pysepal.solara.components.export_hook import ExportDialogController, use_export_dialog
from pysepal.solara.notifications import use_notifications
from reacton.ipyvue import use_event

from app.message import msg
from app.panels.exports import export_sources
from app.panels.layer_style import display_image, layer_name, layer_vis_params
from app.panels.staleness import use_discard_on_new_run
from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.indicator import ClassifiedLayer, IndicatorMaps
from sdg1531.enums import IndicatorLayer

__all__ = ("MapLayersPanel",)


@dataclass(frozen=True, slots=True)
class _ExportRequest:
    """One press of a row's export icon.

    ``nonce`` is what makes a second press of the SAME row a new request: the
    dialog opens from an effect keyed on this value, so a bare layer id would
    compare equal and re-opening a dialog the user had closed would do nothing.
    """

    nonce: int
    layer_id: str


@solara.component
def _ExportDialogHost(
    sources: tuple[ExportSource, ...],
    request: _ExportRequest,
    gee_interface: Any,
    sepal_client: Any,
) -> None:
    """Owns the export dialog and opens it on the layer a row asked for.

    Its own component, mounted only once a build exists: ``use_export_dialog``
    is a hook, so it cannot sit behind ``MapLayersPanel``'s ``maps is None``
    guard, and one of the tasks it mounts schedules real async work at first
    render -- which needs a running event loop that a bare ``solara.render()``
    harness has none of.

    ``request`` arrives as a plain value rather than the controller being
    handed upward, so the row icons stay ignorant of pysepal's export API.
    """
    controller: ExportDialogController = use_export_dialog(
        sources, gee_interface=gee_interface, sepal_client=sepal_client
    )

    def open_requested() -> None:
        if not request.layer_id:
            return
        # AFTER open_dialog(), never before: opening RESETS the form,
        # `selected_source_id.set("")` included (pysepal export_hook.py:803).
        # Both are synchronous writes in one handler, so this survives.
        controller.open_dialog()
        controller.selected_source_id.value = request.layer_id

    solara.use_effect(open_requested, [request])

    ExportDialog(controller=controller, title=msg("exports.title"))


@dataclass(frozen=True, slots=True)
class _AddOutcome:
    """What ``_add_layer`` hands back -- the task never notifies itself."""

    layer_id: IndicatorLayer


async def _add_layer(
    map_: Any, layer_id: IndicatorLayer, layer: ClassifiedLayer, region: ee.Geometry
) -> _AddOutcome:
    """Draw one layer onto the map.

    ``layer_id``/``layer``/``region`` are a snapshot taken at click time
    (``MapLayersPanel.start``), never a live read of ``maps``/``ctx`` -- the
    guide's rule against reading reactive inputs after a task has started.
    ``key=layer_id.value`` is what makes a second add of the same layer
    replace it instead of accumulating another copy, and is the key
    ``clear_stale_layers`` removes by.
    """
    # add_ee_layer_async, NOT asyncio.to_thread(add_ee_layer, ...). Drawing an
    # EE layer fetches a map id, so it is GEE work, and the rule for GEE work
    # is to await the library's own *_async method. A to_thread worker runs
    # outside the kernel context, which is how it loses the session-backed
    # interface this map was built with.
    await map_.add_ee_layer_async(
        display_image(layer, region),
        layer_vis_params(layer_id),
        layer_name(layer_id),
        key=layer_id.value,
    )
    return _AddOutcome(layer_id=layer_id)


def _bind_toggle(
    toggle: Callable[[IndicatorLayer, ClassifiedLayer], None],
    layer_id: IndicatorLayer,
    layer: ClassifiedLayer,
) -> Callable[[], None]:
    """A stably-typed zero-arg closure over one row's layer -- a named function
    rather than a default-argument lambda, whose type ``mypy --strict`` cannot
    pin against the ``Callable[[], None]`` the icon buttons expect."""

    def _toggle() -> None:
        toggle(layer_id, layer)

    return _toggle


def _bind_export(
    export: Callable[[IndicatorLayer], None], layer_id: IndicatorLayer
) -> Callable[[], None]:
    def _export() -> None:
        export(layer_id)

    return _export


@solara.component
def _IconAction(
    icon_name: str,
    tooltip: str,
    on_click: Callable[[], None],
    disabled: bool = False,
    color: str | None = None,
    busy: bool = False,
) -> None:
    """One icon-only row action.

    Its own component so the ``use_event`` click hook attaches unconditionally
    at ITS OWN top level, never inside the caller's loop over layers (rules of
    hooks) -- the same reason ``app/tabs.py`` used to need a ``_SegmentCell``.

    ``tooltip`` is the only affordance an icon-only control has, so it is set
    as BOTH ``title`` (hover) and ``aria-label`` (screen reader); an icon with
    neither is unreadable and unexplained.

    **This is not ``TaskButtonComponent``, and the difference is chrome only.**
    That component is the house convention for a button that starts async work,
    and the substance of the convention is kept here: the same single
    ``use_task``, a visible running state, a click that cancels while running,
    and a disabled start while another row is busy (see ``_LayerToggle``). What
    it cannot do is be an icon -- it always renders a filled, coloured
    ``v-btn`` with a label -- and seven of those stacked in a table is exactly
    what this panel exists to avoid.
    """

    def _handle_click(*_: object) -> None:
        if not disabled:
            on_click()

    btn = rv.Btn(
        icon=True,
        small=True,
        disabled=disabled,
        color=color,
        attributes={"title": tooltip, "aria-label": tooltip},
        children=[
            rv.ProgressCircular(size=16, width=2, indeterminate=True, color=color or "primary")
            if busy
            else rv.Icon(small=True, children=[icon_name])
        ],
    )
    use_event(btn, "click", _handle_click)


@solara.component
def _LayerToggle(
    is_shown: bool,
    is_pending: bool,
    is_busy_elsewhere: bool,
    name: str,
    on_toggle: Callable[[], None],
) -> None:
    """The eye: show, hide, or cancel an in-flight add.

    Three states, one control -- the same collapse ``TaskButtonComponent``
    makes between "start" and "cancel", extended by the shown/hidden pair this
    row already had as two separate buttons. Cancel is never disabled;
    ``is_busy_elsewhere`` only blocks starting, which is that component's rule
    verbatim.
    """
    if is_pending:
        _IconAction(
            icon_name="mdi-close",
            tooltip=msg("layers.cancel", name=name),
            on_click=on_toggle,
            color="error",
            busy=True,
        )
        return
    _IconAction(
        icon_name="mdi-eye" if is_shown else "mdi-eye-off-outline",
        tooltip=msg("layers.hide" if is_shown else "layers.show", name=name),
        on_click=on_toggle,
        disabled=is_busy_elsewhere,
        color="primary" if is_shown else None,
    )


@solara.component
def _LayerRow(
    name: str,
    is_shown: bool,
    is_pending: bool,
    is_busy_elsewhere: bool,
    can_export: bool,
    on_toggle: Callable[[], None],
    on_export: Callable[[], None],
) -> None:
    """One table row: the layer's name, its eye, and its export.

    Called once per layer inside a data-dependent loop, so neither it nor its
    caller may call a hook directly at that level; every control it mounts is
    a whole child component with its own stable hook count.
    """
    with rv.Html(tag="tr"):
        rv.Html(tag="td", children=[name])
        with rv.Html(tag="td", style_="text-align: right; white-space: nowrap;"):
            _LayerToggle(
                is_shown=is_shown,
                is_pending=is_pending,
                is_busy_elsewhere=is_busy_elsewhere,
                name=name,
                on_toggle=on_toggle,
            )
            _IconAction(
                icon_name="mdi-export-variant",
                tooltip=msg("layers.export", name=name),
                on_click=on_export,
                disabled=not can_export,
            )


@solara.component
def MapLayersPanel(
    maps: IndicatorMaps | None,
    ctx: ExecutionContext | None,
    map_: Any,
    gee_interface: Any,
    sepal_client: Any = None,
    shown: solara.Reactive[frozenset[IndicatorLayer]] | frozenset[IndicatorLayer] = frozenset[
        IndicatorLayer
    ](),
) -> None:
    """``ctx`` is what every layer is clipped to before it is drawn (see the
    module docstring); without it -- a spec that does not resolve -- there is
    no ``maps`` either, so the two are always present or absent together.

    ``gee_interface`` is threaded into the export dialog rather than left for
    its own internal ``get_current_gee_interface()`` fallback: ``MapApp``'s
    ``right_panel_content`` is a separate render root from the
    ``@with_sepal_sessions`` page that establishes the session, so a nested
    panel resolving it itself can raise ``SepalSessionError`` even though the
    page-level lookup succeeded (the same reason ``app/panels/exports.py``
    already gave). It is NOT needed for drawing: ``map_.add_ee_layer_async``
    already carries the interface the map itself was constructed with.

    ``shown`` follows ``solara.use_reactive``'s own flexible-argument shape: a
    plain value (the default, and every test that does not care) makes this
    panel own its state exactly as it always has; a ``Reactive`` -- ``page.py``
    passes one, shared with ``MapLegend`` -- makes the set visible to that
    sibling component instead of staying this panel's private copy.

    The description this panel used to render itself now lives in its
    section's own header (``app/panels/outputs.py``).
    """
    notifications = use_notifications()

    shown_reactive = solara.use_reactive(shown)
    shown_ids = shown_reactive.value
    pending_id, set_pending_id = solara.use_state(cast("IndicatorLayer | None", None))

    task = solara.lab.use_task(
        _add_layer, dependencies=None, raise_error=False, prefer_threaded=False
    )

    # Every hook is called here, unconditionally, ahead of the `maps is None`
    # return below: the number of hooks a component calls must stay the same
    # on every render of it, and that guard is exactly the kind of thing that
    # would otherwise make it differ between the "not built yet" and "built"
    # renders of the same panel instance.
    export_request, set_export_request = solara.use_state(_ExportRequest(0, ""))

    def handle_task_state() -> None:
        if task.pending or task.cancelled:
            return
        if task.error:
            # Name the layer. Earth Engine reports a failed graph in its own
            # terms ("Image.remap: Parameter 'image' ... may not be null"),
            # which says nothing about which of the seven the user clicked --
            # and with one task serving every row, the raw message is the only
            # thing that would otherwise reach them.
            failed = pending_id
            if failed is None:
                notifications.error(str(task.exception))
            else:
                notifications.error(
                    msg(
                        "layers.add_failed",
                        name=layer_name(failed),
                        reason=str(task.exception),
                    )
                )
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

    solara.use_effect(
        handle_task_state,
        [task.pending, task.finished, task.error, task.cancelled],
    )

    def cancel() -> None:
        if task.pending:
            with contextlib.suppress(RuntimeError):
                task.cancel()

    def clear_stale_layers() -> None:
        # Sweeps the whole enum, not `shown_ids`. That snapshot is read in the
        # render body, before `handle_task_state`'s effect runs, so a layer
        # whose add finished in THIS commit is on the map but not in it --
        # removing by the snapshot leaves a tile nothing tracks: invisible to
        # this panel and to the legend, and unremovable from the UI.
        cancel()
        if map_ is not None:
            for layer_id in IndicatorLayer:
                map_.remove_layer(layer_id.value, none_ok=True)
        shown_reactive.value = frozenset()

    use_discard_on_new_run(maps, clear_stale_layers)

    def toggle(layer_id: IndicatorLayer, layer: ClassifiedLayer) -> None:
        if task.pending and pending_id == layer_id:
            cancel()
            return
        if layer_id in shown_reactive.value:
            map_.remove_layer(layer_id.value, none_ok=True)
            shown_reactive.value = shown_reactive.value - {layer_id}
            return
        if ctx is None:
            return
        # Snapshot all three here, at click time -- not inside `_add_layer`,
        # which the guide's rule bans from reading live reactive inputs once it
        # is running as a background task.
        set_pending_id(layer_id)
        task(map_, layer_id, layer, ctx.geometry)

    def export(layer_id: IndicatorLayer) -> None:
        set_export_request(_ExportRequest(export_request.nonce + 1, layer_id.value))

    if maps is None:
        solara.Markdown(msg("layers.build_first"))
        return

    with rv.SimpleTable(dense=True):
        with rv.Html(tag="thead"), rv.Html(tag="tr"):
            rv.Html(tag="th", children=[msg("layers.columns.name")])
            rv.Html(
                tag="th",
                style_="text-align: right;",
                children=[msg("layers.columns.action")],
            )
        with rv.Html(tag="tbody"):
            for layer_id, layer in maps.layers().items():
                _LayerRow(
                    name=layer_name(layer_id),
                    is_shown=layer_id in shown_ids,
                    is_pending=task.pending and pending_id == layer_id,
                    is_busy_elsewhere=task.pending and pending_id != layer_id,
                    can_export=ctx is not None,
                    on_toggle=_bind_toggle(toggle, layer_id, layer),
                    on_export=_bind_export(export, layer_id),
                )

    if ctx is not None:
        _ExportDialogHost(
            sources=export_sources(maps, ctx),
            request=export_request,
            gee_interface=gee_interface,
            sepal_client=sepal_client,
        )
