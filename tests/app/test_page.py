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
    panel config, no language selector). ``right_panel_content`` is checked
    only by shape here (title/icon, ``len(content) == 1``) -- this check
    alone cannot tell a placeholder widget from the real ``MapLayersPanel`` or
    AOI step, since both would pass it --
    ``test_the_layers_panel_is_wired_with_the_shared_maps_and_the_real_map_and_gee_interface``,
    ``test_the_aoi_step_is_wired_with_the_shared_spec_and_a_real_map`` and
    ``test_the_productivity_step_shares_the_aoi_step_s_spec`` below prove
    identity instead.

    The five workflow steps live in ``right_panel_content`` now, not
    ``steps_data`` (Task 18 moved them to match the ``sbae-design`` /
    ``sepal-gee-bundle`` layout) -- ``steps_data`` is asserted empty here for
    the same reason ``test_the_layers_panel_is_wired...`` below matters: a
    leftover copy of a step in the old home would render it twice.
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
    assert mapapp.steps_data == []
    assert len(mapapp.right_panel_content) == 8
    aoi_section = mapapp.right_panel_content[0]
    assert aoi_section["title"] == msg("step.aoi")
    assert aoi_section["icon"] == "mdi-map-marker-check"
    assert len(aoi_section["content"]) == 1
    productivity_section = mapapp.right_panel_content[1]
    assert productivity_section["title"] == msg("step.productivity")
    assert productivity_section["icon"] == "mdi-sprout-outline"
    assert len(productivity_section["content"]) == 1
    land_cover_section = mapapp.right_panel_content[2]
    assert land_cover_section["title"] == msg("step.land_cover")
    assert land_cover_section["icon"] == "mdi-terrain"
    assert len(land_cover_section["content"]) == 1
    soc_section = mapapp.right_panel_content[3]
    assert soc_section["title"] == msg("step.soc")
    assert soc_section["icon"] == "mdi-layers-outline"
    assert len(soc_section["content"]) == 1
    run_section = mapapp.right_panel_content[4]
    assert run_section["title"] == msg("step.run")
    assert run_section["icon"] == "mdi-play-circle-outline"
    assert len(run_section["content"]) == 1
    layers_section = mapapp.right_panel_content[5]
    assert layers_section["title"] == msg("layers.title")
    assert layers_section["icon"] == "mdi-layers"
    assert layers_section["description"] == msg("layers.description")
    assert len(layers_section["content"]) == 1
    results_section = mapapp.right_panel_content[6]
    assert results_section["title"] == msg("results.title")
    assert results_section["icon"] == "mdi-chart-bar"
    assert results_section["description"] == msg("results.description")
    assert len(results_section["content"]) == 1
    zonal_section = mapapp.right_panel_content[7]
    assert zonal_section["title"] == msg("zonal.title")
    assert zonal_section["icon"] == "mdi-table"
    assert zonal_section["description"] == msg("zonal.description")
    assert len(zonal_section["content"]) == 1
    assert mapapp.right_panel_open is True
    assert len(mapapp.language_selector) == 1
    offered = {locale["code"] for locale in mapapp.language_selector[0].available_locales}
    assert offered == set(messages.available_locales())


def test_the_map_is_memoized_across_rerenders():
    """``Sdg1531App`` used to build a brand-new ``SepalMap`` on every render,
    discarding the previous one's basemap, zoom and layers each time.
    ``solara.use_memo``, keyed on ``id(gee_interface)``, is supposed to
    prevent that -- proven here by forcing a second render and checking the
    SAME ``SepalMap`` instance comes back, not merely another one that would
    also pass an ``isinstance`` check.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    mapapp = find_widget(box, MapApp)
    assert mapapp is not None
    first_map = mapapp.main_map[0]

    rc.force_update()

    mapapp_again = find_widget(box, MapApp)
    assert mapapp_again is not None
    assert mapapp_again.main_map[0] is first_map


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


def test_the_results_panel_is_wired_with_the_shared_maps_ctx_and_gee_interface(monkeypatch):
    """Same identity concern as the layers panel above, for the two reactives
    ``ResultsPanel`` needs: the ``maps`` AND the ``ctx`` a Build actually
    writes into (not private copies that would never see one), and the real
    session-backed ``gee_interface``."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_run_step(*, spec: Any = None, maps: Any = None, ctx: Any = None) -> None:
        captured["run_maps"] = maps
        captured["run_ctx"] = ctx

    @solara.component
    def _spy_results_panel(*, maps: Any = None, ctx: Any = None, gee_interface: Any = None) -> None:
        captured.update(panel_maps=maps, panel_ctx=ctx, gee_interface=gee_interface)

    monkeypatch.setattr(page_module, "RunStep", _spy_run_step)
    monkeypatch.setattr(page_module, "ResultsPanel", _spy_results_panel)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    assert captured["panel_maps"] is captured["run_maps"]
    assert captured["panel_ctx"] is captured["run_ctx"]
    assert captured["gee_interface"] is not None


def test_the_zonal_panel_is_wired_with_the_shared_maps_ctx_and_a_sepal_client(monkeypatch):
    """Same identity concern as the results panel above, for the two shared
    reactives ``ZonalPanel`` needs plus its own extra dependency: a
    ``sepal_client``, without which the shapefile download has nothing to
    upload through."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_run_step(*, spec: Any = None, maps: Any = None, ctx: Any = None) -> None:
        captured["run_maps"] = maps
        captured["run_ctx"] = ctx

    @solara.component
    def _spy_zonal_panel(
        *, maps: Any = None, ctx: Any = None, gee_interface: Any = None, sepal_client: Any = None
    ) -> None:
        captured.update(
            panel_maps=maps, panel_ctx=ctx, gee_interface=gee_interface, sepal_client=sepal_client
        )

    monkeypatch.setattr(page_module, "RunStep", _spy_run_step)
    monkeypatch.setattr(page_module, "ZonalPanel", _spy_zonal_panel)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    assert captured["panel_maps"] is captured["run_maps"]
    assert captured["panel_ctx"] is captured["run_ctx"]
    assert captured["gee_interface"] is not None
    # `get_current_sepal_client()`'s documented "no SEPAL identity" case
    # returns `None` outside a sandbox, which is exactly this test
    # environment -- the identity that matters here is that `page.py` calls
    # it at all and passes the result through, not a particular truthiness.
    assert "sepal_client" in captured


def test_the_steps_are_in_the_sub_indicator_order():
    """AOI -> Productivity -> Land cover -> SOC -> Run (design decision A6;
    unchanged by Task 18's move from `steps_data` into `right_panel_content`).
    Position is what orders them: MapApp renders `right_panel_content` as
    given, so a section appended in the wrong place displays in the wrong
    place -- and a section has no `id` at all for a stray sort to key on.

    Compared against `msg(...)` rather than English literals so the assertion
    pins ORDER without also pinning the copy, and so it does not break when
    Task 14 adds locales.
    """
    sections = page_module.build_workflow_sections()
    assert [section["title"] for section in sections] == [
        msg("step.aoi"),
        msg("step.productivity"),
        msg("step.land_cover"),
        msg("step.soc"),
        msg("step.run"),
    ]
