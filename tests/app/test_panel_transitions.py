"""Transitions: the domain builds the sankey option, the panel mounts it.

A near-copy of ``test_panel_results.py``: same rationale for patching
``solara.display`` (the only vantage point this bare-render harness has on a
displayed widget), same fixtures shape, same assertions -- see that module's
docstring for the underlying claim about ``solara.render``.
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
from app.panels.transitions import TransitionsPanel
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


# A frame in the shape `decode_transition_areas` produces: the start year and
# the end year as column names, class names as their values, and "Area" --
# see `app/panels/transitions.py`'s module docstring.
_FRAME = pd.DataFrame(
    {
        2001: ["Tree-covered areas", "Grassland"],
        2015: ["Grassland", "Grassland"],
        "Area": [1.0, 2.0],
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
    monkeypatch.setattr("app.panels.transitions.use_notifications", lambda: fake)
    box, rc = solara.render(
        TransitionsPanel(maps=None, ctx=None, gee_interface=None), handle_error=False
    )
    assert rc is not None
    # Not `transitions.description` too: that copy lives once, in `page.py`'s
    # section dict, which `MapApp` renders under the section title -- the
    # panel itself must not render it a second time.
    assert markdown_texts(box) == [f"<p>{msg('transitions.build_first')}</p>"]
    assert find_widget(box, ipyvuetify.Btn) is None  # no dead button before Build
    assert fake.tracked == []  # nothing to show yet, so nothing was started


def test_the_panel_waits_for_both_maps_and_context(monkeypatch):
    """``maps`` and ``ctx`` land together, from one ``build_outcome`` call --
    but they are still two separate fields on that ``BuildOutcome``, so
    nothing stops a caller handing in one without the other. The panel must
    not show Compute until both have landed."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.transitions.use_notifications", lambda: fake)
    box, rc = solara.render(
        TransitionsPanel(maps=_FakeMaps(FakeResolved()), ctx=None, gee_interface=None),
        handle_error=False,
    )
    assert rc is not None
    assert markdown_texts(box) == [f"<p>{msg('transitions.build_first')}</p>"]
    assert find_widget(box, ipyvuetify.Btn) is None


def test_the_chart_option_is_plain_json():
    """ipecharts serialises the option to the browser, so a numpy scalar
    anywhere in it breaks the chart at runtime. The domain guarantees plain
    types; this asserts the guarantee still holds through the panel."""
    from sdg1531.stats.plots import sankey_option

    option = sankey_option(_FRAME, FakeResolved())
    json.dumps(option)  # raises TypeError on a numpy scalar


def test_clicking_compute_fetches_and_mounts_the_real_chart_option(monkeypatch):
    """A real click on the rendered button -- not a captured spy -- proves the
    task is wired through the real domain fetch/option functions, and that the
    widget handed to ``solara.display`` carries the exact option those
    functions produced from the fetched frame."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.transitions.use_notifications", lambda: fake)

    async def fake_fetch(gee_interface, maps, ctx):
        return _FRAME

    monkeypatch.setattr("app.panels.transitions.fetch_transition_areas", fake_fetch)

    displayed: list[Any] = []
    monkeypatch.setattr(solara, "display", lambda obj: displayed.append(obj))

    from ipecharts import EChartsRawWidget

    from sdg1531.stats.plots import sankey_option

    resolved = FakeResolved()
    expected_option = sankey_option(_FRAME, resolved)

    async def main():
        box, rc = solara.render(
            TransitionsPanel(maps=_FakeMaps(resolved), ctx=object(), gee_interface=None),
            handle_error=False,
        )
        assert rc is not None
        button = find_widget(box, ipyvuetify.Btn)
        assert button is not None
        assert button.children == [msg("transitions.compute")]
        button.click()
        assert await _wait_for(lambda: fake.successes or fake.errors)
        return box

    box = asyncio.run(main())

    # Not `len(displayed) == 1`: see `test_panel_results.py`'s identical
    # comment -- `use_task`'s state settles over more than one render pass,
    # so the panel calls `solara.display(chart)` more than once here, which
    # the real solara SERVER's `display_in_reacton_hook` reconciles into one
    # `Output(...)` element (verified separately in a live browser; see
    # `app/panels/transitions.py`'s comment on the `solara.display` call).
    assert displayed
    chart = displayed[-1]
    assert isinstance(chart, EChartsRawWidget)
    assert chart.option == expected_option
    # No stray description or "build first" text now that a build exists.
    assert markdown_texts(box) == []
    assert fake.tracked == [(msg("transitions.compute"), 2)]
    assert fake.trackers[0].steps == [msg("transitions.compute"), msg("transitions.computed")]
    assert fake.successes == [msg("transitions.computed")]
    assert fake.errors == []


def test_a_fetch_that_fails_reports_the_error_and_never_mounts_a_chart(monkeypatch):
    """``raise_error=False`` keeps the render alive; the effect is what must
    still surface the failure -- silently swallowing it would look like
    success to the user, and no chart should appear over stale or absent data.
    """
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.transitions.use_notifications", lambda: fake)

    async def failing_fetch(gee_interface, maps, ctx):
        raise RuntimeError("Earth Engine refused")

    monkeypatch.setattr("app.panels.transitions.fetch_transition_areas", failing_fetch)

    displayed: list[Any] = []
    monkeypatch.setattr(solara, "display", lambda obj: displayed.append(obj))

    async def main():
        box, rc = solara.render(
            TransitionsPanel(maps=_FakeMaps(FakeResolved()), ctx=object(), gee_interface=None),
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
    ``_compute`` receives the SAME object ``TransitionsPanel`` was rendered
    with, snapshotted into ``start()`` at click time -- not, say, a value it
    re-reads from some other source at call time.
    """
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.transitions.use_notifications", lambda: fake)
    monkeypatch.setattr(solara, "display", lambda obj: None)

    calls: list[Any] = []
    the_maps = _FakeMaps(FakeResolved(start_year=2001))

    async def recording_fetch(gee_interface, maps, ctx):
        calls.append(maps)
        await asyncio.sleep(0)
        return _FRAME

    monkeypatch.setattr("app.panels.transitions.fetch_transition_areas", recording_fetch)

    async def main():
        box, rc = solara.render(
            TransitionsPanel(maps=the_maps, ctx=object(), gee_interface=None),
            handle_error=False,
        )
        assert rc is not None
        button = find_widget(box, ipyvuetify.Btn)
        assert button is not None
        button.click()
        assert await _wait_for(lambda: fake.successes or fake.errors)

    asyncio.run(main())

    assert calls == [the_maps]
    assert fake.successes == [msg("transitions.computed")]
