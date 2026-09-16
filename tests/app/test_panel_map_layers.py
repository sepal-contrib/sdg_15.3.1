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

from app.message import messages, msg
from app.panels.map_layers import MapLayersPanel, layer_name, layer_vis_params
from sdg1531.enums import IndicatorLayer
from tests.app.render_helpers import cell_texts, find_widget, find_widgets, markdown_texts


class _FakeImage:
    """Stands in for ``ee.Image``: only ``.select(band)`` is ever called."""

    def __init__(self, name: str) -> None:
        self.name = name

    def select(self, band: str) -> str:
        return f"{self.name}:{band}"


class _FakeLayer:
    """Stands in for ``ClassifiedLayer``: image/band only -- ``label`` is the
    domain's raw id and no production code path reads it any more (M1)."""

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
    """Records every ``add_ee_layer_async``/``remove_layer`` call.

    ``fail_on`` raises for one named layer, standing in for a GEE call that
    refuses.
    """

    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.removed: list[tuple[str, bool]] = []
        self._fail_on = fail_on

    async def add_ee_layer_async(
        self, image: object, vis_params: dict, name: str, key: str = ""
    ) -> None:
        await asyncio.sleep(0)
        if name == self._fail_on:
            raise RuntimeError(f"GEE refused {name}")
        self.calls.append({"image": image, "vis_params": vis_params, "name": name, "key": key})

    def remove_layer(self, key: str, base: bool = False, none_ok: bool = False) -> None:
        self.removed.append((key, none_ok))


class _FakeNotifier:
    """A spy standing in for ``use_notifications()``'s real bus-backed notifier."""

    def __init__(self) -> None:
        self.successes: list[str] = []
        self.errors: list[str] = []

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


def _add_button_labels(box: object) -> list[list[object]]:
    """Every button's ``.children``, in row order -- an "Add" row renders
    ``TaskButtonComponent``'s button, a "shown" row the plain remove button;
    both are ``ipyvuetify.Btn`` instances."""
    return [btn.children for btn in find_widgets(box, ipyvuetify.Btn)]


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
    assert find_widget(box, ipyvuetify.Btn) is None  # no dead action before Build
    assert fake.successes == fake.errors == []


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


def test_every_indicator_layer_resolves_to_a_translated_name_in_every_locale(monkeypatch):
    """Final-review finding M1: ``ClassifiedLayer.label`` is the raw snake
    id, and the app never supplied a translated one. Walks the real
    ``IndicatorLayer`` enum -- not a hand-typed roster of its seven members,
    which would just restate the enum with nothing independent to check it
    against -- across every shipped locale, not only English.

    Monkeypatches ``current_locale`` where ``BoundCatalog.msg`` looks it up,
    rather than calling the real, global ``pysepal.i18n.set_locale``: that
    writes a ``solara.reactive`` every earlier test's still-mounted (and
    never explicitly torn down) render tree may be subscribed to, and would
    re-render them -- with THEIR OWN test's ``use_notifications`` monkeypatch
    already undone -- as a side effect of this one.
    """
    import pysepal.i18n.binding as i18n_binding

    for code in messages.available_locales():
        monkeypatch.setattr(i18n_binding, "current_locale", lambda code=code: code)
        for layer_id in IndicatorLayer:
            name = layer_name(layer_id)
            assert name
            assert name != layer_id.value


def test_the_table_lists_every_layer_translated_and_every_row_starts_addable(monkeypatch):
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: _FakeNotifier())
    box, rc = solara.render(
        MapLayersPanel(maps=_FakeMaps(_THREE_LAYERS), map_=_RecordingMap(), gee_interface=None),
        handle_error=False,
    )
    assert rc is not None
    assert cell_texts(box, "th") == [msg("layers.columns.name"), msg("layers.columns.action")]
    assert cell_texts(box, "td") == [layer_name(layer_id) for layer_id in _THREE_LAYERS]

    buttons = find_widgets(box, ipyvuetify.Btn)
    assert len(buttons) == len(_THREE_LAYERS)
    assert all(btn.children == [msg("layers.add")] for btn in buttons)


def test_clicking_add_draws_only_that_rows_layer_and_reports_its_name(monkeypatch):
    """A real click on the THIRD row's rendered button, not a captured spy or
    the first row -- a naive "the add action ignores its row and always adds
    the first layer" bug would draw LAND_COVER here instead."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: fake)
    fake_map = _RecordingMap()

    async def main():
        box, rc = solara.render(
            MapLayersPanel(maps=_FakeMaps(_THREE_LAYERS), map_=fake_map, gee_interface=None),
            handle_error=False,
        )
        assert rc is not None
        buttons = find_widgets(box, ipyvuetify.Btn)
        assert len(buttons) == 3
        buttons[2].click()  # PRODUCTIVITY_PERFORMANCE, the third layer -- not the first
        assert await _wait_for(lambda: fake.successes or fake.errors)

    asyncio.run(main())

    target = IndicatorLayer.PRODUCTIVITY_PERFORMANCE
    assert len(fake_map.calls) == 1
    call = fake_map.calls[0]
    assert call["name"] == layer_name(target)
    assert call["key"] == target.value
    assert call["vis_params"] == layer_vis_params(target)
    # `.select(layer.band)`, not `.image` alone -- `ClassifiedLayer.image` may
    # carry more bands than the one this panel draws, and the fake's
    # `select` bakes the band into its result, so a dropped `.select(...)`
    # would show up as the bare `_FakeImage` instead.
    assert call["image"] == "productivity_performance:productivity_performance_band"
    assert fake.successes == [msg("layers.added", name=layer_name(target))]
    assert fake.errors == []
    assert fake_map.removed == []  # adding never touches a layer that wasn't shown


def test_a_shown_layer_switches_to_remove_and_re_adds_with_the_same_key(monkeypatch):
    """Covers both remaining single-row rules at once: the remove action must
    really call ``remove_layer`` (not be a no-op), and taking a layer off and
    back on must reuse the same stable ``key`` both times -- what makes a
    second add replace rather than accumulate.
    """
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: fake)
    fake_map = _RecordingMap()
    target = IndicatorLayer.SOC  # the second row of `_TWO_LAYERS`

    # Everything below runs inside ONE `asyncio.run` -- `use_task`'s scheduler
    # binds a task to whichever loop is running when it is started, so a
    # second, later add started from a DIFFERENT loop (e.g. a fresh
    # `asyncio.run` after this one has returned) is not something this
    # panel's plumbing is exercised against elsewhere in the suite either.
    async def main() -> None:
        box, rc = solara.render(
            MapLayersPanel(maps=_FakeMaps(_TWO_LAYERS), map_=fake_map, gee_interface=None),
            handle_error=False,
        )
        assert rc is not None

        find_widgets(box, ipyvuetify.Btn)[1].click()
        assert await _wait_for(lambda: len(fake.successes) == 1)
        assert _add_button_labels(box)[1] == [msg("layers.remove")]
        first_key = fake_map.calls[0]["key"]

        find_widgets(box, ipyvuetify.Btn)[1].click()  # remove -- fully synchronous
        assert fake_map.removed == [(target.value, True)]
        assert _add_button_labels(box)[1] == [msg("layers.add")]  # back to addable

        find_widgets(box, ipyvuetify.Btn)[1].click()  # add again
        assert await _wait_for(lambda: len(fake.successes) == 2)
        assert fake_map.calls[1]["key"] == first_key == target.value
        assert _add_button_labels(box)[1] == [msg("layers.remove")]

    asyncio.run(main())
    assert len(fake_map.calls) == 2


def test_a_layer_that_fails_to_add_reports_the_error_and_stays_addable(monkeypatch):
    """``raise_error=False`` keeps the render alive; the effect is what must
    still surface the failure, and the row must not flip to "shown" over a
    layer that was never actually drawn."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: fake)
    target = IndicatorLayer.SOC
    fake_map = _RecordingMap(fail_on=layer_name(target))

    async def main():
        box, rc = solara.render(
            MapLayersPanel(maps=_FakeMaps(_TWO_LAYERS), map_=fake_map, gee_interface=None),
            handle_error=False,
        )
        assert rc is not None
        find_widgets(box, ipyvuetify.Btn)[1].click()
        assert await _wait_for(lambda: fake.successes or fake.errors)
        return box

    box = asyncio.run(main())

    assert fake.successes == []
    assert fake.errors == ["GEE refused " + layer_name(target)]
    assert _add_button_labels(box)[1] == [msg("layers.add")]  # never marked shown
    assert fake_map.removed == []


def test_clicking_cancel_while_pending_stops_the_add_without_marking_it_shown(monkeypatch):
    """The Async Button Convention's single toggle button: clicking it again
    while the add is running must cancel the task, and cancelling must not
    quietly leave the row looking as if the layer landed."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: fake)
    fake_map = _RecordingMap()

    async def main():
        box, rc = solara.render(
            MapLayersPanel(maps=_FakeMaps(_TWO_LAYERS), map_=fake_map, gee_interface=None),
            handle_error=False,
        )
        assert rc is not None
        button = find_widgets(box, ipyvuetify.Btn)[0]
        button.click()  # start the add
        await asyncio.sleep(0)  # let the task begin, before its own `sleep(0)` resolves
        button.click()  # the SAME button, now in cancel state
        await asyncio.sleep(0.05)
        return box

    box = asyncio.run(main())

    assert fake_map.calls == []
    assert fake.successes == fake.errors == []
    assert _add_button_labels(box)[0] == [msg("layers.add")]


@solara.component
def _Harness(maps_reactive: solara.Reactive[_FakeMaps | None], map_: object) -> None:
    """Lets a test swap the ``maps`` PROP on an already-mounted
    ``MapLayersPanel`` -- Task 20 made ``maps`` a plain value, not a
    reactive the panel itself owns, so a real "the run changed" render can
    only be produced from a level above it, exactly as ``page.py`` does with
    its own memoised ``outcome``.
    """
    MapLayersPanel(maps=maps_reactive.value, map_=map_, gee_interface=None)


def test_a_new_maps_identity_clears_every_layer_the_previous_run_added(monkeypatch):
    """Task 20: a new ``maps`` object is a different run, and the tiles this
    panel already drew are from the run BEFORE it. Two ``_FakeMaps`` built
    from equal-looking layer dicts stand in for "the spec changed and
    produced a new ``IndicatorMaps``" -- ``_FakeMaps`` compares by identity
    (no ``__eq__`` override), the same as the real, frozen ``IndicatorMaps``
    the domain hands back (its ``ee.Image`` fields compare by identity too).
    """
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: fake)
    fake_map = _RecordingMap()
    maps_reactive = solara.reactive(_FakeMaps(_TWO_LAYERS))

    async def add_both():
        box, rc = solara.render(
            _Harness(maps_reactive=maps_reactive, map_=fake_map), handle_error=False
        )
        assert rc is not None
        for index in range(2):
            find_widgets(box, ipyvuetify.Btn)[index].click()
            assert await _wait_for(lambda n=index: len(fake.successes) == n + 1)
        return box

    box = asyncio.run(add_both())

    assert len(fake_map.calls) == 2
    assert fake_map.removed == []  # nothing to clear yet: still the same run

    maps_reactive.value = _FakeMaps(_TWO_LAYERS)  # a NEW object: a different run

    assert sorted(fake_map.removed) == sorted((layer_id.value, True) for layer_id in _TWO_LAYERS)
    # The shown SET was cleared too, not just the map's own layers -- every
    # row is addable again under the new run.
    assert all(labels == [msg("layers.add")] for labels in _add_button_labels(box))


def test_maps_becoming_none_also_clears_the_map(monkeypatch):
    """The spec can stop being runnable entirely -- ``maps`` going from a
    real run to ``None`` must clear the old run's tiles the same way a
    change to a different run does, not leave them shown with nothing left
    to manage them."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: fake)
    fake_map = _RecordingMap()
    maps_reactive: solara.Reactive[_FakeMaps | None] = solara.reactive(_FakeMaps(_TWO_LAYERS))

    async def add_one():
        box, rc = solara.render(
            _Harness(maps_reactive=maps_reactive, map_=fake_map), handle_error=False
        )
        assert rc is not None
        find_widgets(box, ipyvuetify.Btn)[0].click()
        assert await _wait_for(lambda: fake.successes)
        return box

    box = asyncio.run(add_one())
    assert fake_map.removed == []

    maps_reactive.value = None

    assert fake_map.removed == [(IndicatorLayer.LAND_COVER.value, True)]
    assert markdown_texts(box)[-1] == f"<p>{msg('layers.build_first')}</p>"
