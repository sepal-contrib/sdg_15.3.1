"""Zonal statistics and the shapefile download.

Two ``use_task``-backed buttons, so most of these tests render the panel on a
live event loop -- the same harness ``test_panel_results.py`` and
``test_panel_map_layers.py`` use -- click the real rendered button, and wait
for its task to settle before asserting. The table itself is checked through
``DataTableWidget``, the real widget ``solara.DataFrame`` builds in the
reacton tree (unlike ``ResultsPanel``'s chart, this one needs no
``solara.display`` patch: ``DataTableWidget`` is a child element, not a
displayed one).
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Any

import ipyvuetify
import pandas as pd
import solara
from solara.components.datatable import DataTableWidget

from app.message import msg
from app.panels import zonal
from app.panels.zonal import ZonalPanel
from tests.app.render_helpers import find_widget, find_widgets, markdown_texts


class _FakeMaps:
    """Stands in for ``IndicatorMaps``: only ``.resolved`` is read by this panel."""

    def __init__(self, resolved: Any) -> None:
        self.resolved = resolved


class _FakeCtx:
    """Stands in for ``ExecutionContext``: only ``.feature_collection`` is read."""

    def __init__(self, feature_collection: Any) -> None:
        self.feature_collection = feature_collection


class _FakeResolvedScales:
    """A resolved-spec stand-in with DISTINCT analysis/zonal scales.

    ``FakeResolved`` (``tests/helpers_stats.py``) always sets both to 300, so
    it cannot tell a correct ``zonal_scale`` read apart from the
    ``analysis_scale`` regression Defect 1 warns about. This fixture can.
    """

    def __init__(self, *, analysis_scale: int, zonal_scale: int) -> None:
        self.analysis_scale = analysis_scale
        self.zonal_scale = zonal_scale


class _FakeFiles:
    """Stands in for ``UserFilesEndpoint``: records every ``write`` call."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, Any, bool]] = []

    def module_dir(self, module_name: str) -> PurePosixPath:
        return PurePosixPath("/home/sepal-user/module_results") / module_name

    def write(self, file_path: str, content: Any, *, overwrite: bool = False) -> None:
        self.writes.append((file_path, content, overwrite))


class _FakeSepalClient:
    def __init__(self) -> None:
        self.files = _FakeFiles()


class _FakeTracker:
    def __init__(self) -> None:
        self.steps: list[str] = []

    def step(self, message: str) -> None:
        self.steps.append(message)

    def __enter__(self) -> _FakeTracker:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False  # never suppress -- a real TaskTracker doesn't either


class _FakeNotifier:
    """A spy standing in for ``use_notifications()``'s real bus-backed notifier."""

    def __init__(self) -> None:
        self.successes: list[str] = []
        self.errors: list[str] = []
        self.tracked: list[tuple[str, int | None]] = []
        self.trackers: list[_FakeTracker] = []

    def track(self, title: str, total_steps: int | None = None) -> _FakeTracker:
        self.tracked.append((title, total_steps))
        tracker = _FakeTracker()
        self.trackers.append(tracker)
        return tracker

    def success(self, message: str) -> None:
        self.successes.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)


_FRAME = pd.DataFrame({"NoData": [0.0], "Improve": [1.5], "Stable": [2.5], "Degrade": [0.5]})


async def _wait_for(predicate: Callable[[], bool], timeout: float = 2.0) -> bool:
    """Give the scheduled ``use_task`` coroutines a chance to run on the live loop."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            return False
        await asyncio.sleep(0.01)
    return True


def _buttons(box: Any) -> dict[Any, ipyvuetify.Btn]:
    return {tuple(btn.children): btn for btn in find_widgets(box, ipyvuetify.Btn)}


def test_the_panel_renders_before_a_run(monkeypatch):
    """Shown before Build has run."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.zonal.use_notifications", lambda: fake)
    maps = solara.reactive(None)
    ctx = solara.reactive(None)
    box, rc = solara.render(
        ZonalPanel(maps=maps, ctx=ctx, gee_interface=None, sepal_client=None),
        handle_error=False,
    )
    assert rc is not None
    # Not `zonal.description` too: that copy lives once, in `page.py`'s
    # section dict, which `MapApp` renders under the section title -- the
    # panel itself must not render it a second time.
    assert markdown_texts(box) == [f"<p>{msg('zonal.build_first')}</p>"]
    assert find_widget(box, ipyvuetify.Btn) is None  # no dead button before Build
    assert fake.tracked == []  # nothing to show yet, so nothing was started


def test_the_panel_waits_for_both_maps_and_context(monkeypatch):
    """``maps`` and ``ctx`` land via two separate assignments in
    ``RunStep.on_build``, so a render can observe one set with the other
    still ``None``. The panel must not show Compute until both have landed."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.zonal.use_notifications", lambda: fake)
    maps = solara.reactive(_FakeMaps(_FakeResolvedScales(analysis_scale=300, zonal_scale=300)))
    ctx = solara.reactive(None)
    box, rc = solara.render(
        ZonalPanel(maps=maps, ctx=ctx, gee_interface=None, sepal_client=None),
        handle_error=False,
    )
    assert rc is not None
    assert markdown_texts(box) == [f"<p>{msg('zonal.build_first')}</p>"]
    assert find_widget(box, ipyvuetify.Btn) is None


def test_the_panel_never_writes_to_disk():
    """D12: the domain returns bytes and the app hands them to SepalClient.
    A write here would land on container-local disk, which is invisible to
    the user and collides between users."""
    source = inspect.getsource(zonal)
    for forbidden in ("open(", "to_file(", "Path(", "mkdir", "NamedTemporaryFile"):
        assert forbidden not in source, forbidden


def test_clicking_compute_fetches_with_the_zonal_scale_not_the_analysis_scale(monkeypatch):
    """Defect 1: ``fetch_zonal_areas``'s only caller must pass
    ``resolved.zonal_scale``. ``analysis_scale`` and ``zonal_scale`` are
    given DELIBERATELY DIFFERENT values here -- with both equal (as
    ``FakeResolved`` ships), a regression that read the wrong one would
    still pass every assertion below."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.zonal.use_notifications", lambda: fake)
    zones = object()
    resolved = _FakeResolvedScales(analysis_scale=300, zonal_scale=100)
    maps_obj = _FakeMaps(resolved)

    calls: list[dict[str, Any]] = []

    async def fake_fetch(gee_interface, maps, zone_collection, *, scale):
        calls.append({"maps": maps, "zones": zone_collection, "scale": scale})
        return _FRAME

    monkeypatch.setattr("app.panels.zonal.fetch_zonal_areas", fake_fetch)

    async def main():
        maps = solara.reactive(maps_obj)
        ctx = solara.reactive(_FakeCtx(zones))
        box, rc = solara.render(
            ZonalPanel(maps=maps, ctx=ctx, gee_interface="the-interface", sepal_client=None),
            handle_error=False,
        )
        assert rc is not None
        button = _buttons(box)[(msg("zonal.compute"),)]
        button.click()
        assert await _wait_for(lambda: fake.successes or fake.errors)
        return box

    box = asyncio.run(main())

    assert calls == [{"maps": maps_obj, "zones": zones, "scale": 100}]
    table = find_widget(box, DataTableWidget)
    assert table is not None
    assert table.total_length == 1
    assert fake.tracked == [(msg("zonal.compute"), 1)]
    assert fake.trackers[0].steps == [msg("zonal.compute")]
    assert fake.successes == [msg("zonal.ready")]
    assert fake.errors == []
    # No download button until a table exists is covered separately; here,
    # once compute succeeds, it must appear.
    assert (msg("zonal.download"),) in _buttons(box)


def test_a_failed_compute_reports_the_error_and_shows_no_table(monkeypatch):
    """``raise_error=False`` keeps the render alive; the effect is what must
    still surface the failure -- silently swallowing it would look like
    success, and no table or download button should appear over stale or
    absent data."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.zonal.use_notifications", lambda: fake)

    async def failing_fetch(gee_interface, maps, zones, *, scale):
        raise RuntimeError("Earth Engine refused")

    monkeypatch.setattr("app.panels.zonal.fetch_zonal_areas", failing_fetch)

    async def main():
        maps = solara.reactive(_FakeMaps(_FakeResolvedScales(analysis_scale=300, zonal_scale=100)))
        ctx = solara.reactive(_FakeCtx(object()))
        box, rc = solara.render(
            ZonalPanel(maps=maps, ctx=ctx, gee_interface=None, sepal_client=None),
            handle_error=False,
        )
        assert rc is not None
        button = _buttons(box)[(msg("zonal.compute"),)]
        button.click()
        assert await _wait_for(lambda: fake.successes or fake.errors)
        return box

    box = asyncio.run(main())

    assert fake.successes == []
    assert fake.errors == ["Earth Engine refused"]
    assert find_widget(box, DataTableWidget) is None
    assert (msg("zonal.download"),) not in _buttons(box)


def test_the_compute_task_uses_the_snapshot_taken_at_click_time_not_a_live_read(monkeypatch):
    """A Build that lands WHILE Compute is still running must not change
    what that in-flight click fetches -- the guide's rule against reading a
    live reactive input from inside a task after it has started."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.zonal.use_notifications", lambda: fake)

    calls: list[Any] = []
    first_maps = _FakeMaps(_FakeResolvedScales(analysis_scale=300, zonal_scale=100))

    async def recording_fetch(gee_interface, maps, zones, *, scale):
        calls.append(maps)
        await asyncio.sleep(0)
        return _FRAME

    monkeypatch.setattr("app.panels.zonal.fetch_zonal_areas", recording_fetch)

    async def main():
        maps = solara.reactive(first_maps)
        ctx = solara.reactive(_FakeCtx(object()))
        box, rc = solara.render(
            ZonalPanel(maps=maps, ctx=ctx, gee_interface=None, sepal_client=None),
            handle_error=False,
        )
        assert rc is not None
        button = _buttons(box)[(msg("zonal.compute"),)]
        button.click()  # fully synchronous snapshot, before any await happens
        # Land a new build mid-flight -- must not change what this click reads.
        maps.value = _FakeMaps(_FakeResolvedScales(analysis_scale=300, zonal_scale=999))
        assert await _wait_for(lambda: fake.successes or fake.errors)

    asyncio.run(main())

    assert calls == [first_maps]
    assert fake.successes == [msg("zonal.ready")]


def test_clicking_download_writes_the_zip_bytes_with_overwrite_and_the_right_target(monkeypatch):
    """Defect 2: ``sepal_client.files.write`` (never ``write_bytes``, which
    does not exist), with ``overwrite=True`` -- otherwise a second download
    of the same run fails outright."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.zonal.use_notifications", lambda: fake)

    async def fake_fetch(gee_interface, maps, zones, *, scale):
        return _FRAME

    monkeypatch.setattr("app.panels.zonal.fetch_zonal_areas", fake_fetch)

    zip_calls: list[Any] = []

    def fake_zip(gdf: Any) -> bytes:
        zip_calls.append(gdf)
        return b"the-zip-bytes"

    monkeypatch.setattr("app.panels.zonal.zonal_shapefile_zip", fake_zip)

    sepal_client = _FakeSepalClient()

    async def main():
        maps = solara.reactive(_FakeMaps(_FakeResolvedScales(analysis_scale=300, zonal_scale=100)))
        ctx = solara.reactive(_FakeCtx(object()))
        box, rc = solara.render(
            ZonalPanel(maps=maps, ctx=ctx, gee_interface=None, sepal_client=sepal_client),
            handle_error=False,
        )
        assert rc is not None
        compute_button = _buttons(box)[(msg("zonal.compute"),)]
        compute_button.click()
        assert await _wait_for(lambda: fake.successes or fake.errors)
        fake.successes.clear()

        download_button = _buttons(box)[(msg("zonal.download"),)]
        download_button.click()
        assert await _wait_for(lambda: fake.successes or fake.errors)

    asyncio.run(main())

    # `is`, not `==`: the exact frame `_compute` fetched must be what gets
    # zipped, not a coincidentally-equal copy.
    assert len(zip_calls) == 1
    assert zip_calls[0] is _FRAME
    assert sepal_client.files.writes == [
        ("/home/sepal-user/module_results/sdg_15_3_1/sdg_15_3_1_zonal.zip", b"the-zip-bytes", True)
    ]
    assert fake.successes == [msg("zonal.download")]
    assert fake.errors == []


def test_a_failed_download_reports_the_error_and_does_not_pretend_to_succeed(monkeypatch):
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.zonal.use_notifications", lambda: fake)

    async def fake_fetch(gee_interface, maps, zones, *, scale):
        return _FRAME

    monkeypatch.setattr("app.panels.zonal.fetch_zonal_areas", fake_fetch)

    def failing_zip(gdf: Any) -> bytes:
        raise RuntimeError("could not write the shapefile")

    monkeypatch.setattr("app.panels.zonal.zonal_shapefile_zip", failing_zip)

    sepal_client = _FakeSepalClient()

    async def main():
        maps = solara.reactive(_FakeMaps(_FakeResolvedScales(analysis_scale=300, zonal_scale=100)))
        ctx = solara.reactive(_FakeCtx(object()))
        box, rc = solara.render(
            ZonalPanel(maps=maps, ctx=ctx, gee_interface=None, sepal_client=sepal_client),
            handle_error=False,
        )
        assert rc is not None
        compute_button = _buttons(box)[(msg("zonal.compute"),)]
        compute_button.click()
        assert await _wait_for(lambda: fake.successes or fake.errors)
        fake.successes.clear()

        download_button = _buttons(box)[(msg("zonal.download"),)]
        download_button.click()
        assert await _wait_for(lambda: fake.successes or fake.errors)

    asyncio.run(main())

    assert fake.successes == []
    assert fake.errors == ["could not write the shapefile"]
    assert sepal_client.files.writes == []
