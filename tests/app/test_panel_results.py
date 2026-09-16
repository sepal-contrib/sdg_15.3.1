"""Results: the domain builds the chart option, the panel mounts it.

``solara.display`` does not attach a widget to the reacton tree that
``solara.render`` builds -- there is no kernel context for IPython's display
hook to route through outside the real Solara server (proven empirically: a
component that does nothing but ``solara.display(SomeWidget())`` renders a
tree with no trace of that widget under ``.children``). ``find_widget`` can
therefore prove the button and the description text, but not the chart's
presence -- the tests below patch ``solara.display`` itself to capture what
the panel handed it, which is the only vantage point this harness has on a
displayed (rather than child-embedded) widget.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import ipyvuetify
import pandas as pd
import solara

from app.message import msg
from app.panels.results import RESULTS_LAYER, ResultsPanel
from tests.app.render_helpers import find_widget, markdown_texts
from tests.helpers_stats import FakeResolved


class _FakeMaps:
    """Stands in for ``IndicatorMaps``: only ``.resolved`` is read by this panel."""

    def __init__(self, resolved: Any) -> None:
        self.resolved = resolved


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


# A long frame in the shape `decode_areas_by_land_cover` produces: one row per
# (land cover, class), with the class column named for `RESULTS_LAYER.value` --
# see `app/panels/results.py`'s module docstring for why the two must agree.
_FRAME = pd.DataFrame(
    {
        "landcover": ["Forest", "Forest", "Cropland"],
        RESULTS_LAYER.value: ["Degraded", "Improved", "Stable"],
        "Area": [1.0, 2.0, 3.0],
    }
)


async def _wait_for(predicate: Callable[[], bool], timeout: float = 2.0) -> bool:
    """Give the scheduled ``use_task`` coroutine a chance to run on the live loop."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            return False
        await asyncio.sleep(0.01)
    return True


def test_the_panel_renders_before_a_run(monkeypatch):
    """Shown before Build has run."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.results.use_notifications", lambda: fake)
    box, rc = solara.render(
        ResultsPanel(maps=None, ctx=None, gee_interface=None), handle_error=False
    )
    assert rc is not None
    # Not `results.description` too: that copy lives once, in `page.py`'s
    # section dict, which `MapApp` renders under the section title -- the
    # panel itself must not render it a second time.
    assert markdown_texts(box) == [f"<p>{msg('results.build_first')}</p>"]
    assert find_widget(box, ipyvuetify.Btn) is None  # no dead button before Build
    assert fake.tracked == []  # nothing to show yet, so nothing was started


def test_the_panel_waits_for_both_maps_and_context(monkeypatch):
    """``maps`` and ``ctx`` land together, from one ``build_outcome`` call --
    but they are still two separate fields on that ``BuildOutcome``, so
    nothing stops a caller handing in one without the other. The panel must
    not show Compute until both have landed."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.results.use_notifications", lambda: fake)
    box, rc = solara.render(
        ResultsPanel(maps=_FakeMaps(FakeResolved()), ctx=None, gee_interface=None),
        handle_error=False,
    )
    assert rc is not None
    assert markdown_texts(box) == [f"<p>{msg('results.build_first')}</p>"]
    assert find_widget(box, ipyvuetify.Btn) is None


def test_the_chart_option_is_plain_json():
    """ipecharts serialises the option to the browser, so a numpy scalar
    anywhere in it breaks the chart at runtime. The domain guarantees plain
    types; this asserts the guarantee still holds through the panel."""
    from sdg1531.stats.plots import distribution_option

    pivot = pd.DataFrame(
        {"Degraded": [1.0], "Stable": [2.0], "Improved": [3.0]},
        index=["Forest"],
    )
    option = distribution_option(pivot, FakeResolved())
    json.dumps(option)  # raises TypeError on a numpy scalar


def test_clicking_compute_fetches_pivots_and_mounts_the_real_chart_option(monkeypatch):
    """A real click on the rendered button -- not a captured spy -- proves the
    task is wired through the real domain pivot/plot functions, and that the
    widget handed to ``solara.display`` carries the exact option those
    functions produced from the fetched frame."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.results.use_notifications", lambda: fake)

    async def fake_fetch(gee_interface, maps, ctx, *, layer):
        assert layer is RESULTS_LAYER
        return _FRAME

    monkeypatch.setattr("app.panels.results.fetch_areas_by_land_cover", fake_fetch)

    displayed: list[Any] = []
    monkeypatch.setattr(solara, "display", lambda obj: displayed.append(obj))

    from ipecharts import EChartsRawWidget

    from sdg1531.stats.decode import pivot_areas_by_land_cover
    from sdg1531.stats.plots import distribution_option

    resolved = FakeResolved()
    expected_option = distribution_option(
        pivot_areas_by_land_cover(_FRAME, RESULTS_LAYER), resolved
    )

    async def main():
        box, rc = solara.render(
            ResultsPanel(maps=_FakeMaps(resolved), ctx=object(), gee_interface=None),
            handle_error=False,
        )
        assert rc is not None
        button = find_widget(box, ipyvuetify.Btn)
        assert button is not None
        assert button.children == [msg("results.compute")]
        button.click()
        assert await _wait_for(lambda: fake.successes or fake.errors)
        return box

    box = asyncio.run(main())

    # Not `len(displayed) == 1`: `use_task`'s state settles over more than one
    # render pass, so the panel calls `solara.display(chart)` more than once
    # here -- correct and required, since it is the real solara SERVER's
    # `display_in_reacton_hook` (this bare `solara.render()` harness has none)
    # that reconciles repeated calls into ONE `Output(...)` element updated in
    # place rather than duplicated, verified separately in a live browser (see
    # `app/panels/results.py`'s comment on the `solara.display` call).
    assert displayed
    chart = displayed[-1]
    assert isinstance(chart, EChartsRawWidget)
    assert chart.option == expected_option
    # No stray description or "build first" text now that a build exists.
    assert markdown_texts(box) == []
    assert fake.tracked == [(msg("results.compute"), 2)]
    assert fake.trackers[0].steps == [msg("results.compute"), msg("results.computed")]
    assert fake.successes == [msg("results.computed")]
    assert fake.errors == []


def test_a_fetch_that_fails_reports_the_error_and_never_mounts_a_chart(monkeypatch):
    """``raise_error=False`` keeps the render alive; the effect is what must
    still surface the failure -- silently swallowing it would look like
    success to the user, and no chart should appear over stale or absent data.
    """
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.results.use_notifications", lambda: fake)

    async def failing_fetch(gee_interface, maps, ctx, *, layer):
        raise RuntimeError("Earth Engine refused")

    monkeypatch.setattr("app.panels.results.fetch_areas_by_land_cover", failing_fetch)

    displayed: list[Any] = []
    monkeypatch.setattr(solara, "display", lambda obj: displayed.append(obj))

    async def main():
        box, rc = solara.render(
            ResultsPanel(maps=_FakeMaps(FakeResolved()), ctx=object(), gee_interface=None),
            handle_error=False,
        )
        assert rc is not None
        button = find_widget(box, ipyvuetify.Btn)
        assert button is not None
        button.click()
        assert await _wait_for(lambda: fake.successes or fake.errors)

    asyncio.run(main())

    assert fake.successes == []
    assert fake.errors == ["Earth Engine refused"]
    assert displayed == []


def test_the_click_snapshot_is_what_the_fetch_receives_not_a_later_read(monkeypatch):
    """``maps`` is a plain value now, not a reactive a later build could
    mutate out from under a running task -- Task 20 removed the reactive
    that made a live-read even possible (the staleness the panel used to be
    vulnerable to lived one level up, in ``page.py``; see
    ``tests/app/test_page.py``'s staleness regression test for where that
    guarantee now lives). What is still worth pinning here is that
    ``_compute`` receives the SAME object ``ResultsPanel`` was rendered
    with, snapshotted into ``start()`` at click time -- not, say, a value it
    re-reads from some other source at call time.
    """
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.results.use_notifications", lambda: fake)
    monkeypatch.setattr(solara, "display", lambda obj: None)

    calls: list[Any] = []
    the_maps = _FakeMaps(FakeResolved(start_year=2001))

    async def recording_fetch(gee_interface, maps, ctx, *, layer):
        calls.append(maps)
        await asyncio.sleep(0)
        return _FRAME

    monkeypatch.setattr("app.panels.results.fetch_areas_by_land_cover", recording_fetch)

    async def main():
        box, rc = solara.render(
            ResultsPanel(maps=the_maps, ctx=object(), gee_interface=None),
            handle_error=False,
        )
        assert rc is not None
        button = find_widget(box, ipyvuetify.Btn)
        assert button is not None
        button.click()
        assert await _wait_for(lambda: fake.successes or fake.errors)

    asyncio.run(main())

    assert calls == [the_maps]
    assert fake.successes == [msg("results.computed")]
