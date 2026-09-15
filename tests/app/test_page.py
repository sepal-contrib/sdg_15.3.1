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


def _find_widget(root: object, cls: type) -> object | None:
    """The first ``cls`` instance in the render tree, walking ``.children``."""
    if isinstance(root, cls):
        return root
    for child in getattr(root, "children", None) or []:
        found = _find_widget(child, cls)
        if found is not None:
            return found
    return None


def test_the_shell_builds_a_correctly_configured_mapapp():
    """A source grep for ``MapApp.element(`` only proves a spelling. This is
    the behavioural check that dominates it: ``MapApp(...)`` builds a widget
    outside Reacton's render tree, so no ``MapApp`` instance is reachable from
    the rendered box at all under that mistake -- and, unlike a grep, it also
    catches a dropped or misspelled kwarg for every field this task gives a
    genuinely non-empty expected value (an empty map, a wrong title, a wrong
    panel config, no language selector). It still cannot tell a misspelled
    ``right_panel_content`` kwarg from the correct one: it is legitimately
    ``[]`` until a later task gives it content. ``steps_data`` is no longer
    one of those for its shape (id/name/icon/display), but this check alone
    cannot tell a placeholder widget from the real AOI step, since both are
    ``len(content) == 1`` -- ``test_the_aoi_step_is_wired_with_the_shared_spec_and_a_real_map``
    below proves that identity instead.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    mapapp = _find_widget(box, MapApp)
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
    assert mapapp.right_panel_content == []
    assert mapapp.right_panel_open is False
    assert len(mapapp.steps_data) == 2
    aoi_step = mapapp.steps_data[0]
    assert aoi_step["id"] == 1
    assert aoi_step["name"] == msg("step.aoi")
    assert aoi_step["icon"] == "mdi-map-marker-check"
    assert aoi_step["display"] == "step"
    assert len(aoi_step["content"]) == 1
    run_step = mapapp.steps_data[1]
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
