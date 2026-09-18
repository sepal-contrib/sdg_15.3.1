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
from app.panels.chart_theme import themed_option
from app.panels.results import RESULTS_LAYER, ResultsPanel
from sdg1531.enums import IndicatorLayer
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


def test_results_layer_is_pinned_to_the_indicator_not_a_free_parameter():
    """``RESULTS_LAYER`` used to be provable only against itself: ``_FRAME``
    above names its class column ``RESULTS_LAYER.value``, and
    ``test_clicking_compute_fetches_pivots_and_mounts_the_real_chart_option``
    below asserts the code used ``RESULTS_LAYER`` -- so flipping the constant
    to ``IndicatorLayer.SOC`` moves both sides together and every test in this
    file (this one excepted) stays green.

    Which layer belongs here is not a free parameter: it is the SDG 15.3.1
    indicator's own class breakdown, the module's headline output, not one of
    the six intermediate layers. The legacy result tile's own bar chart
    (``ResultTile.bar_plot``, ``input_tile.py:349-364``, frozen under D9)
    pivoted on exactly this -- ``compute_stats_by_lc``'s ``indicator_name``
    parameter defaults to the literal string ``"Indicator 15.3.1"``
    (``run_15_3_1.py:254``), and ``sdg1531/stats/decode.py``'s own
    ``_STATS_LABELS`` table cites that same legacy line range (``:446-448``,
    ``indicator_n_category_label``) against ``IndicatorLayer.INDICATOR_15_3_1``.
    That fact is cited rather than imported: ``tests/parity/test_parity.py``'s
    ``test_stage_b_never_imports_the_legacy_tree`` asserts, over the whole
    session's ``sys.modules``, that nothing outside Stage A ever imports the
    frozen ``component`` tree -- importing it here to read the default live
    would fail that guard the moment both suites run in one session, which
    every verification command for this branch does.
    """
    assert RESULTS_LAYER is IndicatorLayer.INDICATOR_15_3_1


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
        assert button.small is True  # pysepal's right-panel button convention
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
    # `themed_option(..., dark=False)`, not the bare builder's output: the
    # domain owns the chart's CONTENT and the app layer merges light/dark
    # presentation on top (`app/panels/chart_theme.py`). Anchoring on the real
    # builder run through the real themer keeps this a test of the panel's
    # wiring rather than a hand-typed option -- and it still fails if the panel
    # mounts an option the domain did not build.
    assert chart.option == themed_option(expected_option, dark=False)
    # No stray "build first" text now that a build exists -- the description
    # itself no longer renders here at all; it moved to the section header
    # (`app/panels/outputs.py`).
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


def test_a_chart_ready_while_its_section_is_collapsed_does_not_mount_until_reopened(monkeypatch):
    """``is_open`` gates the chart widget's CONSTRUCTION, not just whether it
    shows: an ``EChartsRawWidget`` built while its ``rv.ExpansionPanel`` is
    collapsed measures a fixed, wrong canvas size that reopening never fixes
    (verified with a browser probe; see ``app/panels/outputs.py``'s module
    docstring). Proven here without a browser: the fetch resolves while
    ``is_open=False``, and ``solara.display`` must not be called until a
    later render flips it to ``True``.
    """
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.results.use_notifications", lambda: fake)

    async def fake_fetch(gee_interface, maps, ctx, *, layer):
        return _FRAME

    monkeypatch.setattr("app.panels.results.fetch_areas_by_land_cover", fake_fetch)

    displayed: list[Any] = []
    monkeypatch.setattr(solara, "display", lambda obj: displayed.append(obj))

    the_maps = _FakeMaps(FakeResolved())

    async def main():
        box, rc = solara.render(
            ResultsPanel(maps=the_maps, ctx=object(), gee_interface=None, is_open=False),
            handle_error=False,
        )
        assert rc is not None
        button = find_widget(box, ipyvuetify.Btn)
        assert button is not None
        button.click()
        assert await _wait_for(lambda: fake.successes or fake.errors)
        assert displayed == []  # data arrived, but the section is collapsed

        rc.render(ResultsPanel(maps=the_maps, ctx=object(), gee_interface=None, is_open=True))

    asyncio.run(main())

    assert displayed  # reopening builds the widget now that data is ready


def test_a_new_run_discards_the_chart_the_previous_one_produced(monkeypatch):
    """The repo owner's request: *"if I change params, the map should gone and
    the graphs and calculations should also gone, right? the same if I change
    the AOI"*.

    ``maps`` is a derivation of the run spec (task 20), so a new ``maps``
    object IS a new run. A chart left over from the previous one is a picture
    of a run the user has moved on from, sitting under a heading that now
    describes a different one -- the silently-wrong-data failure the whole
    ``BuildOutcome`` design exists to prevent, reappearing one layer up.
    ``MapLayersPanel`` already discarded on this signal; this panel did not.

    The ``is_open`` toggle is the probe, not decoration. ``solara.display`` is
    this harness's only vantage point on a displayed widget, and it is called
    from the render body -- which reacton skips entirely when nothing about
    the element changed, so neither ``force_update`` nor a re-render with
    equal props says anything about what is on screen. Closing and reopening
    the section re-runs the body AND re-runs the chart memo (``is_open`` is
    one of its dependencies), so what it displays afterwards is exactly "does
    this panel still hold an option".
    """
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.results.use_notifications", lambda: fake)

    async def fake_fetch(gee_interface, maps, ctx, *, layer):
        return _FRAME

    monkeypatch.setattr("app.panels.results.fetch_areas_by_land_cover", fake_fetch)

    displayed: list[Any] = []
    monkeypatch.setattr(solara, "display", lambda obj: displayed.append(obj))

    resolved = FakeResolved()
    first_run, second_run = _FakeMaps(resolved), _FakeMaps(resolved)
    ctx = object()

    def show(maps: Any, *, is_open: bool) -> Any:
        return ResultsPanel(maps=maps, ctx=ctx, gee_interface=None, is_open=is_open)

    async def main():
        box, rc = solara.render(show(first_run, is_open=True), handle_error=False)
        assert rc is not None
        find_widget(box, ipyvuetify.Btn).click()
        assert await _wait_for(lambda: fake.successes or fake.errors)

        # The floor: the SAME run survives a close/reopen with its chart, so
        # the assertion below cannot pass merely because this probe stopped
        # displaying anything at all.
        rc.render(show(first_run, is_open=False))
        displayed.clear()
        rc.render(show(first_run, is_open=True))
        assert displayed, "the chart vanished without any run change"

        rc.render(show(second_run, is_open=True))
        rc.render(show(second_run, is_open=False))
        displayed.clear()
        rc.render(show(second_run, is_open=True))

    asyncio.run(main())

    assert displayed == []


def test_a_fetch_still_in_flight_when_the_run_changes_cannot_land_afterwards(monkeypatch):
    """Discarding the stored option is not enough on its own: a fetch started
    under the PREVIOUS run would otherwise finish afterwards and write its
    stale option straight back into the reactive just cleared -- a chart that
    reappears a second later, describing the wrong run, with nothing on screen
    to say so. Hence the cancel inside the discard.
    """
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.results.use_notifications", lambda: fake)
    monkeypatch.setattr(solara, "display", lambda obj: None)

    release = asyncio.Event()

    async def slow_fetch(gee_interface, maps, ctx, *, layer):
        await release.wait()
        return _FRAME

    monkeypatch.setattr("app.panels.results.fetch_areas_by_land_cover", slow_fetch)

    resolved = FakeResolved()
    first_run, second_run = _FakeMaps(resolved), _FakeMaps(resolved)
    ctx = object()

    async def main():
        box, rc = solara.render(
            ResultsPanel(maps=first_run, ctx=ctx, gee_interface=None), handle_error=False
        )
        assert rc is not None
        find_widget(box, ipyvuetify.Btn).click()
        await asyncio.sleep(0)  # let the task actually start and block

        rc.render(ResultsPanel(maps=second_run, ctx=ctx, gee_interface=None))
        rc.force_update()

        release.set()
        await asyncio.sleep(0.05)

    asyncio.run(main())

    assert fake.successes == [], "a fetch from the abandoned run reported a result"
