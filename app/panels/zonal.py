"""Zonal statistics and the shapefile download.

``fetch_zonal_areas`` reduces over the AOI's own features -- the same zones
``compute_zonal_analysis`` used in the legacy (see ``app/steps/run.py``'s
``build()`` docstring) -- and ``zonal_shapefile_zip`` turns the resulting
GeoDataFrame into bytes. Nothing here touches the filesystem: the bytes go
straight to the SEPAL workspace through ``sepal_client.files``, because
container-local disk is invisible to the user and collides between
concurrent users.

Follows ``docs/guides/solara-gee-patterns.md``'s Async Button Convention
twice over, once per task: each snapshots its inputs at click time rather
than reading them live from inside the task, returns an outcome instead of
mutating reactive state from inside itself, and a ``solara.use_effect`` with
the full dependency list mirrors that outcome into state and a toast.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, cast

import solara
from pysepal.solara.components.task_button import TaskButtonComponent, use_task_button
from pysepal.solara.notifications import use_notifications

from app.message import msg
from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.indicator import IndicatorMaps
from sdg1531.export import zonal_shapefile_zip
from sdg1531.stats.api import fetch_zonal_areas

__all__ = ("ZonalPanel",)

_MODULE_NAME = "sdg_15_3_1"
_ZONAL_FILENAME = "sdg_15_3_1_zonal.zip"


@dataclass(frozen=True, slots=True)
class _ZonalRequest:
    """An immutable snapshot of ``maps``/``ctx``, taken at click time."""

    maps: IndicatorMaps
    ctx: ExecutionContext


@dataclass(frozen=True, slots=True)
class _ZonalOutcome:
    """What ``_compute`` hands back -- the task never mutates reactive state.

    ``frame`` is ``Any`` (a ``gpd.GeoDataFrame`` at runtime): the app layer
    reaches it through a duck-typed object rather than importing geopandas,
    matching ``sdg1531.export.zonal_shapefile_zip``'s own ``gdf: Any``.
    """

    frame: Any


async def _compute(gee_interface: Any, notifications: Any, request: _ZonalRequest) -> _ZonalOutcome:
    """Fetch one snapshot of zonal statistics.

    ``request`` is a snapshot taken at click time (``ZonalPanel.start_compute``),
    never a live read of ``maps``/``ctx`` -- the guide's rule against
    reading reactive inputs after a task has started.
    """
    with notifications.track(msg("zonal.compute"), total_steps=1) as task:
        task.step(msg("zonal.compute"))
        frame = await fetch_zonal_areas(
            gee_interface,
            request.maps,
            request.ctx.feature_collection,
            # zonal_scale, NOT analysis_scale. The legacy used a dedicated
            # `100 if "Sentinel 2" in sensors else 300` for the zonal reduction
            # (run_15_3_1.py:324); resolve() carries it as `zonal_scale`
            # (resolve.py:285) and this call is its only consumer. For a
            # Sentinel 2 run the two genuinely differ.
            scale=request.maps.resolved.zonal_scale,
        )
    return _ZonalOutcome(frame=frame)


def _write_zip(sepal_client: Any, gdf: Any) -> None:
    """Blocking HTTP, plus a ``module_dir()`` round trip of its own. Never
    call ``msg()`` in here: a pool thread has no kernel context and would
    silently fall back to English."""
    target = sepal_client.files.module_dir(_MODULE_NAME) / _ZONAL_FILENAME
    sepal_client.files.write(str(target), zonal_shapefile_zip(gdf), overwrite=True)


@dataclass(frozen=True, slots=True)
class _DownloadOutcome:
    """Sentinel outcome -- the upload has nothing to report but success."""


async def _download(sepal_client: Any, frame: Any) -> _DownloadOutcome:
    # to_thread, not a GEE await: this is plain blocking IO against SEPAL's
    # file API, not Earth Engine -- the opposite of the GEE rule, which keeps
    # GEE coroutines on Solara's own event loop instead of a worker thread.
    # Running it on the click handler itself would freeze the UI for the
    # whole upload.
    await asyncio.to_thread(_write_zip, sepal_client, frame)
    return _DownloadOutcome()


@solara.component
def ZonalPanel(
    maps: IndicatorMaps | None,
    ctx: ExecutionContext | None,
    gee_interface: Any,
    sepal_client: Any,
) -> None:
    solara.Markdown(msg("zonal.description"))

    notifications = use_notifications()
    current_maps = maps
    current_ctx = ctx
    frame: solara.Reactive[Any] = solara.use_reactive(None)

    compute_task = solara.lab.use_task(
        _compute, dependencies=None, raise_error=False, prefer_threaded=False
    )

    def handle_compute_state() -> None:
        if compute_task.pending or compute_task.cancelled:
            return
        if compute_task.error:
            notifications.error(str(compute_task.exception))
            return
        if compute_task.finished and compute_task.value is not None:
            # See ResultsPanel's identical comment: solara's `use_task` overloads
            # bind `R` straight to the task function's return type with no
            # special case for `async def`, so for an async task function
            # `Task[P, R].value` is typed as the `Coroutine` itself rather than
            # what it resolves to -- a stub gap, not a real ambiguity: at
            # runtime `use_task` awaits the coroutine and stores its result,
            # never the coroutine object.
            outcome = cast("_ZonalOutcome", compute_task.value)
            frame.value = outcome.frame
            notifications.success(msg("zonal.ready"))

    # Unconditional, ahead of the `current_maps is None or current_ctx is None`
    # guard below: the number of hooks a component calls must not depend on
    # which branch a render takes.
    solara.use_effect(
        handle_compute_state,
        [
            compute_task.pending,
            compute_task.finished,
            compute_task.error,
            compute_task.cancelled,
        ],
    )

    def start_compute() -> None:
        # Snapshot both here, at click time -- not inside `_compute`, which the
        # guide's rule bans from reading live reactive inputs once it is running
        # as a background task. `maps` and `ctx` come from the same `BuildOutcome`
        # (`build_outcome` sets both together, never one without the other), so
        # this can't observe one set with the other still `None` in practice;
        # guarded again so this closure stays total rather than assuming its
        # caller's care.
        if current_maps is not None and current_ctx is not None:
            compute_task(
                gee_interface,
                notifications,
                _ZonalRequest(maps=current_maps, ctx=current_ctx),
            )

    # `use_task_button` is a hook by convention (its name), so it stays above
    # every conditional too.
    compute_btn_props = use_task_button(compute_task, on_start=start_compute)

    current_frame = frame.value

    download_task = solara.lab.use_task(
        _download, dependencies=None, raise_error=False, prefer_threaded=False
    )

    def handle_download_state() -> None:
        if download_task.pending or download_task.cancelled:
            return
        if download_task.error:
            notifications.error(str(download_task.exception))
            return
        if download_task.finished and download_task.value is not None:
            notifications.success(msg("zonal.download"))

    solara.use_effect(
        handle_download_state,
        [
            download_task.pending,
            download_task.finished,
            download_task.error,
            download_task.cancelled,
        ],
    )

    def start_download() -> None:
        # Snapshot `frame.value` here too, for the same reason: the download
        # task must upload exactly the table that was on screen when the user
        # clicked, not whatever `frame.value` happens to hold once the worker
        # thread actually runs.
        if current_frame is not None:
            download_task(sepal_client, current_frame)

    download_btn_props = use_task_button(download_task, on_start=start_download)

    if current_maps is None or current_ctx is None:
        solara.Markdown(msg("zonal.build_first"))
        return

    TaskButtonComponent(label=msg("zonal.compute"), **compute_btn_props)

    if current_frame is not None:
        # `is not None`, not bare truthiness: an empty DataFrame is falsey,
        # which would hide a real (if empty) result.
        solara.DataFrame(current_frame)
        TaskButtonComponent(label=msg("zonal.download"), **download_btn_props)
