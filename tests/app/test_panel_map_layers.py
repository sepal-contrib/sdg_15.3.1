"""The map panel reads the seven layers; it does not re-derive them.

The click path is asynchronous (``add_ee_layer_async``), so most of these tests
render the panel on a live event loop -- the same harness pysepal's own
``test_asset_select.py`` uses for a ``use_task``-backed component -- click the
real rendered button, and wait for the task to settle before asserting.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import ipyvuetify
import solara

from app.message import msg
from app.panels.map_layers import MapLayersPanel, layer_vis_params
from sdg1531.enums import IndicatorLayer
from tests.app.render_helpers import find_widget, markdown_texts


class _FakeImage:
    """Stands in for ``ee.Image``: only ``.select(band)`` is ever called."""

    def __init__(self, name: str) -> None:
        self.name = name

    def select(self, band: str) -> str:
        return f"{self.name}:{band}"


class _FakeLayer:
    """Stands in for ``ClassifiedLayer``: image/band/label only."""

    def __init__(self, name: str) -> None:
        self.image = _FakeImage(name)
        self.band = f"{name}_band"
        self.label = name


class _FakeMaps:
    """Stands in for ``IndicatorMaps``: only ``.layers()`` is used."""

    def __init__(self, layers: dict[IndicatorLayer, _FakeLayer]) -> None:
        self._layers = layers

    def layers(self) -> dict[IndicatorLayer, _FakeLayer]:
        return self._layers


_TWO_LAYERS = {
    IndicatorLayer.LAND_COVER: _FakeLayer("land_cover"),
    IndicatorLayer.SOC: _FakeLayer("soc"),
}

# LAND_COVER and SOC both take `layer_vis_params`'s default branch, so a fixture
# built only from them cannot tell a correct per-layer mapping from one constant
# vis dict shared by every layer: PRODUCTIVITY_PERFORMANCE is the only id with a
# genuinely different `layer_vis_params(...)` result (min=1, max=2, a 2-colour
# palette), so it is the layer that makes that distinction actually testable.
_THREE_LAYERS = {
    **_TWO_LAYERS,
    IndicatorLayer.PRODUCTIVITY_PERFORMANCE: _FakeLayer("productivity_performance"),
}


class _RecordingMap:
    """Records every ``add_ee_layer_async`` call.

    ``on_first_call`` runs synchronously before the first call's own
    ``await`` -- the hook a test uses to mutate ``maps.value`` mid-flight and
    check the running task does not notice. ``fail_on`` raises for one named
    layer, standing in for a GEE call that refuses.
    """

    def __init__(
        self,
        on_first_call: Callable[[], None] | None = None,
        fail_on: str | None = None,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self._on_first_call = on_first_call
        self._fail_on = fail_on

    async def add_ee_layer_async(
        self, image: object, vis_params: dict, name: str, key: str = ""
    ) -> None:
        if self._on_first_call is not None and not self.calls:
            self._on_first_call()
        await asyncio.sleep(0)
        if name == self._fail_on:
            raise RuntimeError(f"GEE refused {name}")
        self.calls.append({"image": image, "vis_params": vis_params, "name": name, "key": key})


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


async def _wait_for(predicate: Callable[[], bool], timeout: float = 2.0) -> bool:
    """Give the scheduled ``use_task`` coroutine a chance to run on the live loop."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            return False
        await asyncio.sleep(0.01)
    return True


def test_the_panel_renders_with_no_maps(monkeypatch):
    """Shown before Build has run."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: fake)
    box, rc = solara.render(
        MapLayersPanel(maps=None, map_=None, gee_interface=None), handle_error=False
    )
    assert rc is not None
    assert markdown_texts(box) == [
        f"<p>{msg('layers.description')}</p>",
        f"<p>{msg('layers.build_first')}</p>",
    ]
    assert find_widget(box, ipyvuetify.Btn) is None  # no dead button before Build
    assert fake.tracked == []  # nothing to show yet, so nothing was started


def test_vis_params_come_from_the_domain_palette():
    """The app must not invent colours: the palette is the domain's, and the
    exported assets carry the same one."""
    from sdg1531.tables import DEGRADATION_COLORS

    vis = layer_vis_params(IndicatorLayer.INDICATOR_15_3_1)
    assert vis["palette"] == list(DEGRADATION_COLORS.values())[1:]
    assert vis["min"] == 1
    assert vis["max"] == 3


def test_the_performance_layer_gets_its_own_two_class_vis():
    """``sdg1531/tables.py`` deliberately ships no palette for
    ``PROD_PERFORMANCE_LABELS`` and hands that choice to whichever phase first
    renders the layer -- this one. It is the only id ``layer_vis_params``
    treats differently, so it is what makes a "one constant vis for every
    layer" regression actually detectable."""
    from sdg1531.tables import DEGRADATION_COLORS

    vis = layer_vis_params(IndicatorLayer.PRODUCTIVITY_PERFORMANCE)
    assert vis["min"] == 1
    assert vis["max"] == 2
    assert vis["palette"] == list(DEGRADATION_COLORS.values())[1:3]


def test_clicking_show_draws_every_layer_and_reports_the_real_count(monkeypatch):
    """A real click on the rendered button -- not a captured spy -- proves the
    task is wired to the domain's layers and that the toast carries the real
    count once every layer has been drawn.

    Three layers, not two: ``layer_vis_params`` only tells
    ``PRODUCTIVITY_PERFORMANCE`` apart from everything else, so a fixture of
    just LAND_COVER + SOC cannot distinguish a correct per-layer mapping from
    one constant vis dict reused for all seven layers.
    """
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: fake)
    fake_map = _RecordingMap()

    async def main():
        box, rc = solara.render(
            MapLayersPanel(maps=_FakeMaps(_THREE_LAYERS), map_=fake_map, gee_interface=None),
            handle_error=False,
        )
        assert rc is not None
        button = find_widget(box, ipyvuetify.Btn)
        assert button is not None
        assert button.children == [msg("layers.show")]
        button.click()
        assert await _wait_for(lambda: fake.successes or fake.errors)

    asyncio.run(main())

    recorded = {call["name"]: call for call in fake_map.calls}
    assert recorded.keys() == {layer.label for layer in _THREE_LAYERS.values()}
    # `.select(layer.band)`, not `.image` alone: `ClassifiedLayer.image` may
    # carry more bands than the one this panel is meant to draw (trend and
    # state both do), and the fake's `select` bakes the band into the result,
    # so a dropped `.select(...)` shows up as the bare `_FakeImage` instead.
    for name, call in recorded.items():
        assert call["image"] == f"{name}:{name}_band"
    # Per layer, not one dict shared by all three -- the mapping this panel
    # exists to own, not re-derive.
    assert {name: call["vis_params"] for name, call in recorded.items()} == {
        layer.label: layer_vis_params(layer_id) for layer_id, layer in _THREE_LAYERS.items()
    }
    assert fake.tracked == [(msg("layers.show"), 3)]
    assert fake.trackers[0].steps == [layer.label for layer in _THREE_LAYERS.values()]
    assert fake.successes == [msg("layers.shown", count=3)]
    assert fake.errors == []


def test_every_layer_gets_a_stable_key_so_a_second_click_replaces_not_accumulates(monkeypatch):
    """``add_ee_layer_async`` accepts a ``key`` and replaces an existing layer
    that carries the same one; a call with no key at all -- or one that
    changes between clicks -- is what would let two clicks pile up two
    copies of the same layer instead of one."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: fake)
    fake_map = _RecordingMap()

    async def main():
        box, rc = solara.render(
            MapLayersPanel(maps=_FakeMaps(_TWO_LAYERS), map_=fake_map, gee_interface=None),
            handle_error=False,
        )
        assert rc is not None
        button = find_widget(box, ipyvuetify.Btn)
        assert button is not None

        button.click()
        assert await _wait_for(lambda: fake.successes)
        first_keys = {call["name"]: call["key"] for call in fake_map.calls}

        fake_map.calls = []
        fake.successes = []
        button.click()  # the SAME button, on the SAME task -- a real second click
        assert await _wait_for(lambda: fake.successes)
        second_keys = {call["name"]: call["key"] for call in fake_map.calls}

        return first_keys, second_keys

    first_keys, second_keys = asyncio.run(main())

    assert first_keys == {"land_cover": "land_cover", "soc": "soc"}
    assert all(first_keys.values()), "a falsy key falls back to add_layer's own name-derived one"
    assert second_keys == first_keys


def test_the_layers_snapshot_is_taken_synchronously_inside_the_click_handler(monkeypatch):
    """``maps`` is a plain value now, not a reactive a build can mutate out
    from under a running task -- Task 20 removed the reactive that made a
    live-read even possible, so the click-time-snapshot concern this used to
    share a module with (a Build landing mid-flight) cannot recur at this
    panel any more; see ``tests/app/test_page.py``'s staleness regression
    test for where that guarantee now lives (the shared spec, one level up).

    What is still worth pinning here: a task scheduled with
    ``solara.lab.use_task`` never runs any of its body until the event loop
    is given a turn, so if ``.layers()`` is read where the guide requires --
    inside the synchronous click handler, before ``task(...)`` schedules
    anything -- it has already been called exactly once by the time
    ``button.click()`` returns, with no ``await`` in between. A version that
    instead handed the whole ``IndicatorMaps`` into the task and called
    ``.layers()`` from inside it would still show zero calls here, because
    that task has not had a turn to run yet.
    """
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: fake)

    class _CountingMaps(_FakeMaps):
        def __init__(self, layers: dict[IndicatorLayer, _FakeLayer]) -> None:
            super().__init__(layers)
            self.layers_call_count = 0

        def layers(self) -> dict[IndicatorLayer, _FakeLayer]:
            self.layers_call_count += 1
            return super().layers()

    async def main() -> int:
        counting_maps = _CountingMaps(_TWO_LAYERS)
        fake_map = _RecordingMap()
        box, rc = solara.render(
            MapLayersPanel(maps=counting_maps, map_=fake_map, gee_interface=None),
            handle_error=False,
        )
        assert rc is not None
        button = find_widget(box, ipyvuetify.Btn)
        assert button is not None

        button.click()  # fully synchronous: no `await` has happened yet
        count_right_after_click = counting_maps.layers_call_count

        assert await _wait_for(lambda: fake.successes or fake.errors)
        return count_right_after_click

    count_right_after_click = asyncio.run(main())

    assert count_right_after_click == 1


def test_a_layer_that_fails_reports_the_error_and_no_success(monkeypatch):
    """``raise_error=False`` keeps the render alive; the effect is what must
    still surface the failure -- silently swallowing it would look like
    success to the user."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: fake)
    fake_map = _RecordingMap(fail_on="soc")

    async def main():
        box, rc = solara.render(
            MapLayersPanel(maps=_FakeMaps(_TWO_LAYERS), map_=fake_map, gee_interface=None),
            handle_error=False,
        )
        assert rc is not None
        button = find_widget(box, ipyvuetify.Btn)
        assert button is not None
        button.click()
        assert await _wait_for(lambda: fake.successes or fake.errors)

    asyncio.run(main())

    assert fake.successes == []
    assert fake.errors == ["GEE refused soc"]
