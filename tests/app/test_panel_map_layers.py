"""The map panel reads the seven layers; it does not re-derive them.

The click path is asynchronous (``add_ee_layer_async``), so most of these tests
render the panel on a live event loop -- the same harness pysepal's own
``test_asset_select.py`` uses for a ``use_task``-backed component -- click the
real rendered button, and wait for the task to settle before asserting.

**Two controls per row now, not one.** The eye toggles a layer on and off (and
cancels an add in flight); the export icon opens the export dialog on that
row's own layer. Both are plain ``ipyvuetify.Btn``, so anything reading
buttons positionally goes through ``_row_actions`` rather than indexing
``find_widgets(box, Btn)`` directly.

``_ExportDialogHost`` is stubbed out for the whole module by an autouse
fixture: the real one mounts ``use_export_dialog``, whose ``dependencies=[]``
task needs a running event loop, and the export CONTENT is tested in
``tests/app/test_panel_exports.py`` (the sources) plus one wiring test below.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import ipyvuetify
import pytest
import solara

from app.message import messages, msg
from app.panels import map_layers as map_layers_module
from app.panels.exports import export_sources
from app.panels.layer_style import layer_name, layer_vis_params
from app.panels.map_layers import MapLayersPanel, _ExportDialogHost
from sdg1531.enums import IndicatorLayer
from tests.app.render_helpers import cell_texts, find_widget, find_widgets, markdown_texts


@solara.component
def _noop_export_dialog_host(**_kwargs: object) -> None:
    """Stands in for the real dialog host -- see this module's docstring."""


@pytest.fixture(autouse=True)
def _stub_export_dialog(monkeypatch):
    monkeypatch.setattr(map_layers_module, "_ExportDialogHost", _noop_export_dialog_host)


class _FakeImage:
    """Stands in for ``ee.Image``: records the display chain as a name.

    ``select``/``clip``/``selfMask`` each return a NEW ``_FakeImage`` whose
    name carries what was applied, so a test can assert the whole chain --
    and its ORDER -- from the single value that reaches
    ``add_ee_layer_async``.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    def select(self, band: str) -> _FakeImage:
        return _FakeImage(f"{self.name}:{band}")

    def clip(self, region: object) -> _FakeImage:
        return _FakeImage(f"{self.name}|clip({region})")

    def selfMask(self) -> _FakeImage:
        return _FakeImage(f"{self.name}|selfMask")

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _FakeImage) and other.name == self.name

    def __repr__(self) -> str:
        return f"_FakeImage({self.name!r})"


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


class _FakeCtx:
    """Stands in for ``ExecutionContext``: only ``.geometry`` is read by this
    panel (it is what every drawn layer is clipped to), plus
    ``.feature_collection`` by ``export_sources``."""

    geometry = "AOI-GEOMETRY"
    feature_collection = "AOI-COLLECTION"


_CTX = _FakeCtx()


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


def _row_actions(box: object) -> list[tuple[object, object]]:
    """``(eye, export)`` for each row, in row order.

    ``_LayerRow`` renders exactly two ``ipyvuetify.Btn`` per row, in that
    order, and the panel renders no other button -- so pairing them off the
    flat tree walk is what turns "the fourth button" back into "row two's
    export icon".
    """
    buttons = find_widgets(box, ipyvuetify.Btn)
    assert len(buttons) % 2 == 0, "every row renders exactly two buttons"
    return [(buttons[i], buttons[i + 1]) for i in range(0, len(buttons), 2)]


def _eye_icons(box: object) -> list[object]:
    """Each row's eye icon name, or ``None`` while that row is pending (the
    eye is replaced by a spinner, which carries no icon name)."""
    icons = []
    for eye, _export in _row_actions(box):
        child = eye.children[0]
        icons.append(child.children[0] if isinstance(child, ipyvuetify.Icon) else None)
    return icons


_HIDDEN = "mdi-eye-off-outline"
_SHOWN = "mdi-eye"


def test_the_panel_renders_with_no_maps(monkeypatch):
    """Shown before Build has run."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: fake)
    box, rc = solara.render(
        MapLayersPanel(maps=None, ctx=None, map_=None, gee_interface=None), handle_error=False
    )
    assert rc is not None
    assert markdown_texts(box) == [f"<p>{msg('layers.build_first')}</p>"]
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
        MapLayersPanel(
            maps=_FakeMaps(_THREE_LAYERS), ctx=_CTX, map_=_RecordingMap(), gee_interface=None
        ),
        handle_error=False,
    )
    assert rc is not None
    assert cell_texts(box, "th") == [msg("layers.columns.name"), msg("layers.columns.action")]
    assert cell_texts(box, "td") == [layer_name(layer_id) for layer_id in _THREE_LAYERS]

    rows = _row_actions(box)
    assert len(rows) == len(_THREE_LAYERS)
    assert _eye_icons(box) == [_HIDDEN] * len(_THREE_LAYERS)
    # Every row's eye and export icon names the layer it belongs to -- an
    # icon-only control has no text, so this tooltip is its only affordance
    # (and its `aria-label`).
    for (eye, export), layer_id in zip(rows, _THREE_LAYERS, strict=True):
        name = layer_name(layer_id)
        assert eye.attributes["title"] == msg("layers.show", name=name)
        assert eye.attributes["aria-label"] == eye.attributes["title"]
        assert export.attributes["title"] == msg("layers.export", name=name)
        assert export.attributes["aria-label"] == export.attributes["title"]


def test_clicking_add_draws_only_that_rows_layer_and_reports_its_name(monkeypatch):
    """A real click on the THIRD row's rendered button, not a captured spy or
    the first row -- a naive "the add action ignores its row and always adds
    the first layer" bug would draw LAND_COVER here instead."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: fake)
    fake_map = _RecordingMap()

    async def main():
        box, rc = solara.render(
            MapLayersPanel(
                maps=_FakeMaps(_THREE_LAYERS), ctx=_CTX, map_=fake_map, gee_interface=None
            ),
            handle_error=False,
        )
        assert rc is not None
        rows = _row_actions(box)
        assert len(rows) == 3
        rows[2][0].click()  # PRODUCTIVITY_PERFORMANCE's eye -- the third row, not the first
        assert await _wait_for(lambda: fake.successes or fake.errors)

    asyncio.run(main())

    target = IndicatorLayer.PRODUCTIVITY_PERFORMANCE
    assert len(fake_map.calls) == 1
    call = fake_map.calls[0]
    assert call["name"] == layer_name(target)
    assert call["key"] == target.value
    assert call["vis_params"] == layer_vis_params(target)
    # The whole display chain, in order: `.select(layer.band)`, then
    # `.clip(ctx.geometry)`, then `.selfMask()`. `ClassifiedLayer.image` may
    # carry more bands than the one this panel draws, and an image that is
    # neither clipped nor self-masked paints the palette's first colour over
    # the whole globe (see `app/panels/layer_style.py`). The fake bakes each
    # call into its name, so dropping any of the three shows up here.
    assert call["image"] == _FakeImage(
        "productivity_performance:productivity_performance_band|clip(AOI-GEOMETRY)|selfMask"
    )
    assert fake.successes == [msg("layers.added", name=layer_name(target))]
    assert fake.errors == []
    assert fake_map.removed == []  # adding never touches a layer that wasn't shown


def test_a_shown_layer_switches_to_an_open_eye_and_re_adds_with_the_same_key(monkeypatch):
    """Covers both remaining single-row rules at once: hiding must really
    call ``remove_layer`` (not be a no-op), and taking a layer off and back
    on must reuse the same stable ``key`` both times -- what makes a second
    add replace rather than accumulate. One control does all three states
    (hidden / pending / shown), so the eye's own icon is what says which.
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
            MapLayersPanel(
                maps=_FakeMaps(_TWO_LAYERS), ctx=_CTX, map_=fake_map, gee_interface=None
            ),
            handle_error=False,
        )
        assert rc is not None

        _row_actions(box)[1][0].click()
        assert await _wait_for(lambda: len(fake.successes) == 1)
        assert _eye_icons(box)[1] == _SHOWN
        first_key = fake_map.calls[0]["key"]

        _row_actions(box)[1][0].click()  # hide -- fully synchronous
        assert fake_map.removed == [(target.value, True)]
        assert _eye_icons(box)[1] == _HIDDEN  # back to hidden

        _row_actions(box)[1][0].click()  # show again
        assert await _wait_for(lambda: len(fake.successes) == 2)
        assert fake_map.calls[1]["key"] == first_key == target.value
        assert _eye_icons(box)[1] == _SHOWN

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
            MapLayersPanel(
                maps=_FakeMaps(_TWO_LAYERS), ctx=_CTX, map_=fake_map, gee_interface=None
            ),
            handle_error=False,
        )
        assert rc is not None
        _row_actions(box)[1][0].click()
        assert await _wait_for(lambda: fake.successes or fake.errors)
        return box

    box = asyncio.run(main())

    assert fake.successes == []
    # The toast NAMES the layer: one task serves all seven rows, so Earth
    # Engine's own message ("Image.remap: Parameter 'image' ...") would
    # otherwise leave the user with no idea which row failed.
    assert fake.errors == [
        msg(
            "layers.add_failed",
            name=layer_name(target),
            reason="GEE refused " + layer_name(target),
        )
    ]
    assert layer_name(target) in fake.errors[0]
    assert _eye_icons(box)[1] == _HIDDEN  # never marked shown
    assert fake_map.removed == []


def test_clicking_cancel_while_pending_stops_the_add_without_marking_it_shown(monkeypatch):
    """The Async Button Convention's single toggle control, kept through the
    move to an icon: clicking the eye again while the add is running must
    cancel the task, and cancelling must not quietly leave the row looking as
    if the layer landed."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: fake)
    fake_map = _RecordingMap()

    async def main():
        box, rc = solara.render(
            MapLayersPanel(
                maps=_FakeMaps(_TWO_LAYERS), ctx=_CTX, map_=fake_map, gee_interface=None
            ),
            handle_error=False,
        )
        assert rc is not None
        eye = _row_actions(box)[0][0]
        eye.click()  # start the add
        await asyncio.sleep(0)  # let the task begin, before its own `sleep(0)` resolves
        _row_actions(box)[0][0].click()  # the SAME control, now in cancel state
        await asyncio.sleep(0.05)
        return box

    box = asyncio.run(main())

    assert fake_map.calls == []
    assert fake.successes == fake.errors == []
    assert _eye_icons(box)[0] == _HIDDEN


def test_the_other_rows_eye_is_disabled_while_one_is_pending(monkeypatch):
    """One component-level ``use_task`` (the brief forbade a hook per row):
    clicking a SECOND row's eye while the first is still in flight would not
    queue it, it would REPLACE it -- the first row's add silently abandoned,
    with no toast and no explanation on either row. Disabling every other
    row's eye while one is pending (see ``_LayerToggle``) turns that into a
    click that cannot be made, rather than one that silently does nothing.
    """
    fake = _FakeNotifier()
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: fake)
    fake_map = _RecordingMap()

    async def main():
        box, rc = solara.render(
            MapLayersPanel(
                maps=_FakeMaps(_TWO_LAYERS), ctx=_CTX, map_=fake_map, gee_interface=None
            ),
            handle_error=False,
        )
        assert rc is not None
        _row_actions(box)[0][0].click()  # start LAND_COVER's add
        await asyncio.sleep(0)  # let the task begin, before its own `sleep(0)` resolves

        rows = _row_actions(box)
        assert rows[0][0].disabled is False  # the pending row's own eye: cancel, never disabled
        assert _eye_icons(box)[0] is None  # ... and showing a spinner, not an eye
        assert rows[1][0].disabled is True  # every OTHER row: disabled while busy elsewhere

        assert await _wait_for(lambda: fake.successes or fake.errors)
        assert _row_actions(box)[1][0].disabled is False  # re-enabled once nothing is pending

    asyncio.run(main())


@solara.component
def _Harness(maps_reactive: solara.Reactive[_FakeMaps | None], map_: object) -> None:
    """Lets a test swap the ``maps`` PROP on an already-mounted
    ``MapLayersPanel`` -- Task 20 made ``maps`` a plain value, not a
    reactive the panel itself owns, so a real "the run changed" render can
    only be produced from a level above it, exactly as ``page.py`` does with
    its own memoised ``outcome``.
    """
    MapLayersPanel(maps=maps_reactive.value, ctx=_CTX, map_=map_, gee_interface=None)


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
            _row_actions(box)[index][0].click()
            assert await _wait_for(lambda n=index: len(fake.successes) == n + 1)
        return box

    box = asyncio.run(add_both())

    assert len(fake_map.calls) == 2
    assert fake_map.removed == []  # nothing to clear yet: still the same run

    maps_reactive.value = _FakeMaps(_TWO_LAYERS)  # a NEW object: a different run

    # EVERY layer id is swept, not only the two this panel believes are shown
    # -- see `clear_stale_layers` for the render-time-snapshot window that
    # makes the narrower version leave an untracked tile on the map.
    # `remove_layer(..., none_ok=True)` makes the other five no-ops.
    assert sorted(fake_map.removed) == sorted((layer_id.value, True) for layer_id in IndicatorLayer)
    # The shown SET was cleared too, not just the map's own layers -- every
    # row is hidden again under the new run.
    assert _eye_icons(box) == [_HIDDEN] * len(_TWO_LAYERS)


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

    assert sorted(fake_map.removed) == sorted((layer_id.value, True) for layer_id in IndicatorLayer)
    assert markdown_texts(box)[-1] == f"<p>{msg('layers.build_first')}</p>"


def test_the_export_icon_asks_for_its_own_row_and_asks_again_on_a_second_press(monkeypatch):
    """Each row's export icon opens the dialog on THAT row's layer.

    The row never touches the export controller itself -- it raises an
    ``_ExportRequest``, and ``_ExportDialogHost`` is what turns that into a
    preselect-and-open (see those two in ``app/panels/map_layers.py``). So
    this asserts the request, which is the whole of the panel's own side of
    the contract.

    The second press is not redundant: the host opens the dialog from a
    ``use_effect`` keyed on the request value, so a request carrying only a
    layer id would compare EQUAL to the previous one and re-opening a dialog
    the user had closed would silently do nothing. The nonce is what stops
    that, and this is what would catch its removal.
    """
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: _FakeNotifier())
    captured: list[object] = []

    @solara.component
    def _spy_host(*, request: object = None, **_kwargs: object) -> None:
        captured.append(request)

    monkeypatch.setattr(map_layers_module, "_ExportDialogHost", _spy_host)

    box, rc = solara.render(
        MapLayersPanel(
            maps=_FakeMaps(_THREE_LAYERS), ctx=_CTX, map_=_RecordingMap(), gee_interface=None
        ),
        handle_error=False,
    )
    assert rc is not None
    assert captured[-1].layer_id == ""  # nothing asked for yet

    _row_actions(box)[1][1].click()  # SOC's export icon -- the second row, not the first
    assert captured[-1].layer_id == IndicatorLayer.SOC.value
    first_nonce = captured[-1].nonce

    _row_actions(box)[1][1].click()  # the SAME row again
    assert captured[-1].layer_id == IndicatorLayer.SOC.value
    assert captured[-1].nonce != first_nonce, (
        "a repeat press must be a distinct request, or the host's effect never re-fires"
    )


def test_the_export_host_is_only_mounted_once_a_build_exists(monkeypatch):
    """``use_export_dialog`` schedules real async work at mount, so mounting
    it before there is anything to export would make every render of this app
    need an event loop for a dialog no one opened -- see
    ``_ExportDialogHost``'s own docstring."""
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: _FakeNotifier())
    mounted: list[bool] = []

    @solara.component
    def _spy_host(**_kwargs: object) -> None:
        mounted.append(True)

    monkeypatch.setattr(map_layers_module, "_ExportDialogHost", _spy_host)

    _box, rc = solara.render(
        MapLayersPanel(maps=None, ctx=None, map_=None, gee_interface=None), handle_error=False
    )
    assert rc is not None
    assert mounted == []

    _box, rc = solara.render(
        MapLayersPanel(
            maps=_FakeMaps(_TWO_LAYERS), ctx=_CTX, map_=_RecordingMap(), gee_interface=None
        ),
        handle_error=False,
    )
    assert rc is not None
    assert mounted == [True]


def test_the_export_host_is_wired_with_one_source_per_layer_and_the_threaded_gee_interface(
    monkeypatch,
):
    """Moved here from ``tests/app/test_panel_exports.py`` when the Export
    section became a column of icons in this table.

    A source grep cannot tell a threaded ``gee_interface`` from one left for
    ``use_export_dialog``'s own ``get_current_gee_interface()`` fallback to
    resolve -- and that fallback raises outside a SEPAL session, which is why
    it is threaded (see ``MapLayersPanel``'s docstring). Spying on the real
    kwargs is what proves it.
    """
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: _FakeNotifier())
    captured: dict[str, object] = {}

    @solara.component
    def _spy_host(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(map_layers_module, "_ExportDialogHost", _spy_host)
    sentinel_gee = object()
    sentinel_client = object()

    _box, rc = solara.render(
        MapLayersPanel(
            maps=_FakeMaps(_THREE_LAYERS),
            ctx=_CTX,
            map_=_RecordingMap(),
            gee_interface=sentinel_gee,
            sepal_client=sentinel_client,
        ),
        handle_error=False,
    )
    assert rc is not None

    assert captured["gee_interface"] is sentinel_gee
    assert captured["sepal_client"] is sentinel_client
    assert [source.id for source in captured["sources"]] == [
        layer_id.value for layer_id in _THREE_LAYERS
    ]


def test_the_real_dialog_opens_on_the_row_that_asked_for_it(monkeypatch):
    """The other side of the contract, against the REAL ``use_export_dialog``.

    Every test above this one stubs ``_ExportDialogHost`` out, so the panel's
    half -- "the icon raises a request naming its own layer" -- was covered
    while the half that turns a request into a selection was not tested at
    all. It was also wrong: ``open_dialog()`` RESETS the form, including
    ``selected_source_id.set("")`` (pysepal ``export_hook.py:803-805``), so
    preselecting before opening opened the dialog on nothing. The repo owner
    is the one who noticed -- *"if I select any of them, the export should
    populate that selection I believe no?"*.

    A fake controller could not have caught that: the bug lives entirely in
    pysepal's ordering, so the only thing worth asserting against is the real
    hook. It is mounted directly here rather than through ``MapLayersPanel``
    (whose module-level fixture replaces it), inside ``asyncio.run`` because
    the hook's ``dependencies=[]`` task schedules at first render.
    """
    captured: dict[str, object] = {}

    @solara.component
    def _spy_dialog(controller: object = None, **_kwargs: object) -> None:
        captured["controller"] = controller

    monkeypatch.setattr(map_layers_module, "ExportDialog", _spy_dialog)

    async def render_host() -> None:
        sources = export_sources(_FakeMaps(_THREE_LAYERS), _CTX)
        _box, rc = solara.render(
            _ExportDialogHost(
                sources=sources,
                request=map_layers_module._ExportRequest(1, IndicatorLayer.SOC.value),
                gee_interface=None,
                sepal_client=None,
            ),
            handle_error=False,
        )
        assert rc is not None

    asyncio.run(render_host())

    controller = captured["controller"]
    assert controller.open.value is True
    assert controller.selected_source_id.value == IndicatorLayer.SOC.value


def test_an_empty_request_leaves_the_real_dialog_shut(monkeypatch):
    """The first render carries the sentinel request nobody pressed. Without
    its guard the host would open an empty dialog over the panel the moment a
    build appeared -- and the test above, which only ever asserts an OPEN
    dialog, would still pass."""
    captured: dict[str, object] = {}

    @solara.component
    def _spy_dialog(controller: object = None, **_kwargs: object) -> None:
        captured["controller"] = controller

    monkeypatch.setattr(map_layers_module, "ExportDialog", _spy_dialog)

    async def render_host() -> None:
        _box, rc = solara.render(
            _ExportDialogHost(
                sources=export_sources(_FakeMaps(_THREE_LAYERS), _CTX),
                request=map_layers_module._ExportRequest(0, ""),
                gee_interface=None,
                sepal_client=None,
            ),
            handle_error=False,
        )
        assert rc is not None

    asyncio.run(render_host())

    assert captured["controller"].open.value is False


def _cells(box: object, tag: str) -> list[object]:
    """Every ``<th>`` or ``<td>`` widget, in tree order -- the widgets
    themselves, where ``cell_texts`` returns only their text."""
    return [w for w in find_widgets(box, ipyvuetify.Html) if w.tag == tag]


def test_the_action_column_and_its_icons_are_centred_on_the_same_axis(monkeypatch):
    """The repo owner's report: *"the icons in the action column should be
    centered with it, right now they're not centered against the title"*.

    Both were right-aligned, and an icon button carries its own padding, so
    the glyphs sat visibly left of where the heading's right edge fell.
    Asserting the pair together is the point -- either one centred alone
    reproduces the same misalignment.
    """
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: _FakeNotifier())
    box, rc = solara.render(
        MapLayersPanel(
            maps=_FakeMaps(_THREE_LAYERS), ctx=_CTX, map_=_RecordingMap(), gee_interface=None
        ),
        handle_error=False,
    )
    assert rc is not None

    # The second `<th>` is the action column; the action `<td>`s are the ones
    # holding buttons rather than a layer name.
    action_heading = _cells(box, "th")[1]
    action_cells = [td for td in _cells(box, "td") if find_widget(td, ipyvuetify.Btn) is not None]

    assert len(action_cells) == len(_THREE_LAYERS)
    assert "text-align: center" in action_heading.style_
    for cell in action_cells:
        assert "text-align: center" in cell.style_


def test_the_export_icon_is_a_cloud(monkeypatch):
    """Every destination the export dialog offers -- an Earth Engine asset,
    Google Drive, the SEPAL workspace -- is remote, and the arrow this used to
    carry read as a download to the user's own machine. The name itself is
    checked against the shipped webfont by ``tests/app/test_icons.py``; what
    this pins is that the row still uses it.
    """
    monkeypatch.setattr("app.panels.map_layers.use_notifications", lambda: _FakeNotifier())
    box, rc = solara.render(
        MapLayersPanel(
            maps=_FakeMaps(_THREE_LAYERS), ctx=_CTX, map_=_RecordingMap(), gee_interface=None
        ),
        handle_error=False,
    )
    assert rc is not None

    icons = [export.children[0].children[0] for _eye, export in _row_actions(box)]
    assert icons == ["mdi-cloud-upload-outline"] * len(_THREE_LAYERS)
