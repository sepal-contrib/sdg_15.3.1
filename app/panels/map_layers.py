"""The computed layers: one row per layer, each with its own show and export.

The seven layers come from ``IndicatorMaps.layers()``; this panel never decides
which layers exist, what they are called, or how they are coloured. Colours
come from the domain palette so the map and the exported assets agree. Names
come from :func:`layer_name` -- ``ClassifiedLayer.label`` is the layer's raw
snake id (frozen under decision D9; the domain's own docstring says the
translated display label is the app layer's job).

**Two icons per row, not two text buttons and a separate Export section.** The
table replaced a single "show everything" button; the repo owner then used it
and objected to its weight -- *"in the layers list, I'd like to remove the
button, IDK, or maybe replace it with an eye? for me the problem is that all 7
buttons are too much they're together"* -- and, in the same message, asked
where export belongs: *"what if the export can someway included in the layer
section?"*. So a row now carries an eye toggle and an export icon, and
``app/panels/outputs.py`` no longer renders an Export section of its own. The
export dialog is still pysepal's (``use_export_dialog`` + ``ExportDialog``,
the documented route for a custom trigger layout); the row icon only opens it
and preselects its own layer -- in that order, because opening resets the form
(see ``_ExportDialogHost.open_requested``).

The export glyph is ``mdi-export-variant``, which is also what pysepal's own
``ExportLauncher`` defaults to. It is not a free choice: this stack serves MDI
**4.9.95** (solara's ``plain.html`` pins it; the ``jupyter-vuetify``
labextension bundles the same generation), and Vuetify renders a name the font
lacks as an empty box with no error -- which is how the first attempt at this
icon shipped invisible. ``tests/app/test_icons.py`` checks every name in this
package against the font actually on disk.

**Every layer is clipped to the AOI and self-masked before it is drawn.**
Without it the whole world renders in the palette's FIRST colour: these are
classified images whose unclassified background is 0, the vis window starts at
1, and Earth Engine paints everything at or below ``min`` with the min colour
-- so an unclipped indicator layer covers the globe in "Degraded" red. That is
what the repo owner saw ("make sure all the layers that are being added to the
map show only the AOI area, I see some of them not masked out and I see a
large red tiles"). The legacy did this too, in ``display_maps``
(``component/scripts/run_15_3_1.py:113-144``): every classified raster is
``.clip(geom).selfMask()``. This is DISPLAY only -- the domain graphs are
untouched (decision D9), and the export path keeps its own
``.clip(ctx.feature_collection)`` (``app/panels/exports.py``), so nothing here
reaches the parity harness.

One deliberate difference from the legacy: it clipped a non-ADMIN AOI to
``geom.bounds()`` rather than to the geometry, so a drawn or uploaded AOI
still painted its whole bounding rectangle. The owner asked for "only the AOI
area", so this clips to ``ctx.geometry`` for every AOI arm.

The shown set is never read back from ``map_.find_layer``: the map's live
widget state changes without telling Solara, so a row driven from it would not
re-render when it did. It lives in a ``solara.Reactive`` instead, threaded down
from ``page.py`` (see ``MapLayersPanel``'s own ``shown`` docstring) so the same
set drives the floating legend (``app/panels/legend.py``) too, not a second,
independent notion of "on the map".

Adding a layer is GEE work (it fetches a map id), so it follows
``docs/guides/solara-gee-patterns.md``'s Async Button Convention: one
``use_task`` for the whole component, parameterised by which layer it is
currently drawing, with a row's spinner driven by comparing its id against the
in-flight one. NOT one task per row -- that would call ``use_task`` a number
of times that depends on ``maps.layers()``, a hook inside a loop. Removing is
synchronous and local, so it needs no task.

One task also means one layer can draw at a time: clicking a second row's eye
while the first is still in flight does not queue it, it REPLACES it (the same
``task(...)`` call that started the first now starts the second). The abandoned
layer never lands on the map and no row ends up wrongly marked shown, so this
was never a correctness bug -- but the first row simply reverted to hidden with
no toast, which read as the click having done nothing. Every OTHER row's eye is
disabled (``is_busy_elsewhere``, see ``_LayerToggle``) while one is pending, so
the interaction cannot be started rather than being started and silently
dropped -- weighed against seven one-or-two-second adds becoming serial, which
seemed the smaller cost.

Task 20 made ``maps`` a derivation of the run spec: change the spec, and
``maps`` is a new object describing a different run. Every tile this panel
already drew is then from the run BEFORE it -- the same silently-wrong-data
failure Task 20 exists to kill, reappearing on the map instead of in a panel.
The effect keyed on ``maps`` below clears them; see ``clear_stale_layers`` for
why it sweeps every layer id rather than only the ones it believes are shown.
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
    dialog is opened by an effect keyed on this value, and a bare layer id
    would compare equal to the previous request, so re-opening a dialog the
    user had closed would silently do nothing.
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

    **Its own component, mounted only once a build exists**, for two reasons
    that point the same way. ``use_export_dialog`` is a hook, so it cannot be
    called behind ``MapLayersPanel``'s own ``maps is None`` guard; and one of
    the tasks it mounts has ``dependencies=[]``, which schedules real async
    work through ``asyncio.create_task`` the moment it first renders. In a
    bare ``solara.render()`` harness with no running loop that raises
    ``RuntimeError: no running event loop``, so a panel that mounted this
    unconditionally would make every render test of the whole app need an
    event loop just to reach a dialog it never opens. Mounting a whole child
    component conditionally is ordinary reconciliation; calling its hooks
    conditionally would not be.

    ``request`` arrives as a plain value rather than the controller being
    handed upward, so the row icons stay ignorant of pysepal's export API --
    they set a request, and this decides what that means.
    """
    controller: ExportDialogController = use_export_dialog(
        sources, gee_interface=gee_interface, sepal_client=sepal_client
    )

    def open_requested() -> None:
        if not request.layer_id:
            return
        # AFTER open_dialog(), never before: opening RESETS the whole form,
        # `selected_source_id.set("")` included (pysepal
        # `export_hook.py:803-805`). Preselecting first therefore opens the
        # dialog on nothing at all, which is what the repo owner hit -- *"if I
        # select any of them, the export should populate that selection I
        # believe no?"*. Both calls are plain synchronous writes in one event
        # handler, so the reset lands first and this selection survives it.
        # The id is the layer's own `layer_id.value`, which is exactly how
        # `export_sources(...)` keys its sources (`app/panels/exports.py`), so
        # the hook's `_reconcile_selected_source` finds it and keeps it.
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
    what the repo owner asked to be rid of.
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

    Its own component, called once per layer inside ``MapLayersPanel``'s loop
    over ``maps.layers()`` -- a python list whose length is data-dependent,
    so no hook may be called directly at that outer loop's level (rules of
    hooks). ``_LayerRow`` itself calls none directly either: every control it
    mounts is a whole child component with its own stable hook count.
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
        # `maps` just became a different run (or stopped being runnable at
        # all): cancel whatever this panel is still drawing from the
        # PREVIOUS one, and take every layer this panel could have put on the
        # map back off, rather than leaving old-run tiles shown next to -- or
        # instead of -- the new run's.
        #
        # It sweeps the whole `IndicatorLayer` enum rather than
        # `shown_ids`, with `remove_layer(..., none_ok=True)` making each
        # removal a no-op when that layer is not on the map. `shown_ids` is a
        # RENDER-TIME snapshot and there is a real window in which it is
        # already out of date: a layer whose add finished during THIS render
        # commit is put on the map by `handle_task_state`, whose effect runs
        # before this one and writes the reactive -- but `shown_ids` was read
        # from the render body, before either effect, so it does not name that
        # layer. Removing by the snapshot alone would leave its tile on the
        # map with nothing tracking it: invisible to this panel, invisible to
        # `MapLegend`, and impossible to remove from the UI afterwards. The
        # enum is the complete set of keys `_add_layer` can ever have used, so
        # sweeping it cannot miss one.
        cancel()
        if map_ is not None:
            for layer_id in IndicatorLayer:
                map_.remove_layer(layer_id.value, none_ok=True)
        shown_reactive.value = frozenset()

    # Keyed on the whole `IndicatorMaps`, never one of its fields -- that is
    # what "a different run" means, here and in the three panels below this
    # one, which is why it is one shared hook. `app/panels/staleness.py`
    # carries the mount rule and the measured reason the dependency must stay
    # this object.
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
