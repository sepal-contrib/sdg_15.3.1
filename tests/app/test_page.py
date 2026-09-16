"""The shell renders and is wired the way pysepal requires."""

from __future__ import annotations

from typing import Any

import reacton.core
import solara
from pysepal.mapping.sepal_map import SepalMap
from pysepal.sepalwidgets.vue_app import MapApp

from app import page as page_module
from app.message import messages, msg
from sdg1531.spec import RunSpec
from tests.app.render_helpers import find_widget


def test_page_is_a_solara_component():
    # reacton.core.Component, not solara.core.Component -- the latter does not
    # exist. @solara.component returns a reacton ComponentFunction, which is a
    # reacton.core.Component; solara re-exports no Component name at all.
    assert isinstance(page_module.Page, reacton.core.Component)
    assert isinstance(page_module.Sdg1531App, reacton.core.Component)


def test_the_shell_renders():
    """A render that raises takes the whole app down at load; this is the
    cheapest possible guard against that."""
    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None


def test_the_shell_builds_a_correctly_configured_mapapp():
    """A source grep for ``MapApp.element(`` only proves a spelling. This is
    the behavioural check that dominates it: ``MapApp(...)`` builds a widget
    outside Reacton's render tree, so no ``MapApp`` instance is reachable from
    the rendered box at all under that mistake -- and, unlike a grep, it also
    catches a dropped or misspelled kwarg for every field this task gives a
    genuinely non-empty expected value (an empty map, a wrong title, a wrong
    panel config, no language selector). ``right_panel_content`` and
    ``steps_data`` are checked only by shape here (title/icon/description,
    ``len(content) == 1``) -- this check alone cannot tell a placeholder
    widget from the real ``MapLayersPanel`` or AOI step, since both would
    pass it -- ``test_the_layers_panel_is_wired_with_the_shared_maps_and_the_real_map_and_gee_interface``,
    ``test_the_aoi_step_is_wired_with_the_shared_spec_and_a_real_map`` and
    ``test_the_productivity_step_shares_the_aoi_step_s_spec`` below prove
    identity instead.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    mapapp = find_widget(box, MapApp)
    assert mapapp is not None, "no MapApp in the render tree; MapApp(...) builds outside it"

    assert mapapp.app_title == msg("app.title")
    assert mapapp.app_icon == "mdi-earth"
    assert len(mapapp.main_map) == 1
    assert isinstance(mapapp.main_map[0], SepalMap)
    assert mapapp.right_panel_config == {
        "title": msg("panel.title"),
        "icon": "mdi-chart-box-outline",
        "width": 450,
        "description": msg("panel.description"),
    }
    assert len(mapapp.right_panel_content) == 1
    layers_section = mapapp.right_panel_content[0]
    assert layers_section["title"] == msg("layers.title")
    assert layers_section["icon"] == "mdi-layers"
    assert layers_section["description"] == msg("layers.description")
    assert len(layers_section["content"]) == 1
    assert mapapp.right_panel_open is True
    assert len(mapapp.steps_data) == 5
    aoi_step = mapapp.steps_data[0]
    assert aoi_step["id"] == 1
    assert aoi_step["name"] == msg("step.aoi")
    assert aoi_step["icon"] == "mdi-map-marker-check"
    assert aoi_step["display"] == "step"
    assert len(aoi_step["content"]) == 1
    productivity_step = mapapp.steps_data[1]
    assert productivity_step["id"] == 2
    assert productivity_step["name"] == msg("step.productivity")
    assert productivity_step["icon"] == "mdi-sprout-outline"
    assert productivity_step["display"] == "step"
    assert len(productivity_step["content"]) == 1
    land_cover_step = mapapp.steps_data[2]
    assert land_cover_step["id"] == 3
    assert land_cover_step["name"] == msg("step.land_cover")
    assert land_cover_step["icon"] == "mdi-terrain"
    assert land_cover_step["display"] == "step"
    assert len(land_cover_step["content"]) == 1
    soc_step = mapapp.steps_data[3]
    assert soc_step["id"] == 4
    assert soc_step["name"] == msg("step.soc")
    assert soc_step["icon"] == "mdi-layers-outline"
    assert soc_step["display"] == "step"
    assert len(soc_step["content"]) == 1
    run_step = mapapp.steps_data[4]
    assert run_step["id"] == 5
    assert run_step["name"] == msg("step.run")
    assert run_step["icon"] == "mdi-play-circle-outline"
    assert run_step["display"] == "step"
    assert len(run_step["content"]) == 1
    assert len(mapapp.language_selector) == 1
    offered = {locale["code"] for locale in mapapp.language_selector[0].available_locales}
    assert offered == set(messages.available_locales())


def test_the_aoi_step_is_wired_with_the_shared_spec_and_a_real_map(monkeypatch):
    """``steps_data[0]["content"]`` above is checked only by length: a
    placeholder widget, or the AOI step built with ``map_=None``, both pass
    it. Substituting a spy for ``AoiStep`` and reading what ``Sdg1531App``
    actually calls it with proves the identity instead -- the same reactive
    ``Sdg1531App`` holds, not a private copy, and the real ``SepalMap``, not
    ``None`` (which silently drops the DRAW method from the picker; a
    plausible copy-paste once Tasks 6-9 add steps that take no map)."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_aoi_step(*, spec: Any = None, map_: Any = None) -> None:
        captured.update(spec=spec, map_=map_)

    monkeypatch.setattr(page_module, "AoiStep", _spy_aoi_step)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    assert isinstance(captured.get("spec"), solara.Reactive)
    assert isinstance(captured["spec"].value, RunSpec)
    assert isinstance(captured.get("map_"), SepalMap)


def test_the_productivity_step_shares_the_aoi_step_s_spec(monkeypatch):
    """Same concern as the AOI check above, one step over: a private copy of
    ``RunSpec`` here would let Productivity edit a spec Run never sees."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_aoi_step(*, spec: Any = None, map_: Any = None) -> None:
        captured["aoi_spec"] = spec

    @solara.component
    def _spy_productivity_step(*, spec: Any = None) -> None:
        captured["productivity_spec"] = spec

    monkeypatch.setattr(page_module, "AoiStep", _spy_aoi_step)
    monkeypatch.setattr(page_module, "ProductivityStep", _spy_productivity_step)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    assert captured["productivity_spec"] is captured["aoi_spec"]


def test_the_land_cover_step_shares_the_aoi_step_s_spec(monkeypatch):
    """Same concern as the two checks above, one step further: a private copy
    of ``RunSpec`` here would let Land cover edit a spec Run never sees."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_aoi_step(*, spec: Any = None, map_: Any = None) -> None:
        captured["aoi_spec"] = spec

    @solara.component
    def _spy_land_cover_step(*, spec: Any = None) -> None:
        captured["land_cover_spec"] = spec

    monkeypatch.setattr(page_module, "AoiStep", _spy_aoi_step)
    monkeypatch.setattr(page_module, "LandCoverStep", _spy_land_cover_step)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    assert captured["land_cover_spec"] is captured["aoi_spec"]


def test_the_soc_step_shares_the_aoi_step_s_spec(monkeypatch):
    """Same concern as the two checks above, one step further: a private copy
    of ``RunSpec`` here would let SOC edit a spec Run never sees."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_aoi_step(*, spec: Any = None, map_: Any = None) -> None:
        captured["aoi_spec"] = spec

    @solara.component
    def _spy_soc_step(*, spec: Any = None) -> None:
        captured["soc_spec"] = spec

    monkeypatch.setattr(page_module, "AoiStep", _spy_aoi_step)
    monkeypatch.setattr(page_module, "SocStep", _spy_soc_step)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    assert captured["soc_spec"] is captured["aoi_spec"]


def test_the_run_step_shares_the_aoi_step_s_spec_and_gets_real_reactives(monkeypatch):
    """The Run step must read the SAME ``RunSpec`` reactive the AOI step
    writes -- a private copy would let Run build against a stale spec -- and
    ``maps``/``ctx`` must be real, writable reactives the Build trigger can
    populate, not ``None`` placeholders that would make every panel after it
    unable to receive a result."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_aoi_step(*, spec: Any = None, map_: Any = None) -> None:
        captured["aoi_spec"] = spec

    @solara.component
    def _spy_run_step(*, spec: Any = None, maps: Any = None, ctx: Any = None) -> None:
        captured.update(run_spec=spec, maps=maps, ctx=ctx)

    monkeypatch.setattr(page_module, "AoiStep", _spy_aoi_step)
    monkeypatch.setattr(page_module, "RunStep", _spy_run_step)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    assert captured["run_spec"] is captured["aoi_spec"]
    assert isinstance(captured["maps"], solara.Reactive)
    assert captured["maps"].value is None
    assert isinstance(captured["ctx"], solara.Reactive)
    assert captured["ctx"].value is None


def test_the_layers_panel_is_wired_with_the_shared_maps_and_the_real_map_and_gee_interface(
    monkeypatch,
):
    """``right_panel_content[0]["content"]`` above is checked only by length:
    a placeholder widget, or a panel built with ``map_=None``, both pass it.
    Substituting a spy for ``MapLayersPanel`` and reading what ``Sdg1531App``
    actually calls it with proves the identity instead -- the same ``maps``
    reactive the Run step writes into (not a private copy that would never
    see a Build), the real ``SepalMap`` the layers must be drawn onto, and
    the real session-backed ``gee_interface``."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_run_step(*, spec: Any = None, maps: Any = None, ctx: Any = None) -> None:
        captured["run_maps"] = maps

    @solara.component
    def _spy_map_layers_panel(
        *, maps: Any = None, map_: Any = None, gee_interface: Any = None
    ) -> None:
        captured.update(panel_maps=maps, map_=map_, gee_interface=gee_interface)

    monkeypatch.setattr(page_module, "RunStep", _spy_run_step)
    monkeypatch.setattr(page_module, "MapLayersPanel", _spy_map_layers_panel)

    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    mapapp = find_widget(box, MapApp)
    assert mapapp is not None

    assert captured["panel_maps"] is captured["run_maps"]
    # `is`, not `isinstance`: a second, unrelated SepalMap would still pass an
    # isinstance check while drawing the seven layers onto a map the user is
    # not looking at -- `mapapp.main_map[0]` is the one actually in the tree.
    assert captured["map_"] is mapapp.main_map[0]
    assert captured["gee_interface"] is not None


def test_the_steps_are_in_the_sub_indicator_order():
    """AOI -> Productivity -> Land cover -> SOC -> Run (design decision A6).
    Position is what orders them: MapApp renders `steps_data` as given, so a
    step appended in the wrong place displays in the wrong place however its
    `id` reads.

    Compared against `msg(...)` rather than English literals so the assertion
    pins ORDER without also pinning the copy, and so it does not break when
    Task 14 adds locales.
    """
    steps = page_module.build_steps_data()
    assert [step["id"] for step in steps] == [1, 2, 3, 4, 5]
    assert [step["name"] for step in steps] == [
        msg("step.aoi"),
        msg("step.productivity"),
        msg("step.land_cover"),
        msg("step.soc"),
        msg("step.run"),
    ]
