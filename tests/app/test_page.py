"""The shell renders and is wired the way pysepal requires."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
import reacton.core
import solara
from pysepal.mapping.sepal_map import SepalMap
from pysepal.sepalwidgets.vue_app import MapApp

from app import page as page_module
from app.message import messages, msg
from app.steps.run import BuildOutcome, build
from sdg1531.spec import Period, RunSpec
from tests.app.render_helpers import find_widget, markdown_texts
from tests.spec_factory import DEFAULT_PERIODS, default_spec

# `threshold=0.0`: `default_spec()`'s MODIS sensor needs a resolved float
# threshold for `build_indicator_maps()` to succeed (see
# `tests/app/test_step_run.py`); every test below that needs a REAL build,
# not just a runnable spec, uses this one.
_BUILDABLE_SPEC = default_spec(threshold=0.0)


@solara.component
def _noop_exports_panel(**_kwargs: Any) -> None:
    """A stand-in for ``ExportsPanel`` in tests that drive a REAL build but
    care about a different panel. ``ExportLauncher`` (the real component
    behind ``ExportsPanel``) mounts one of its own tasks with
    ``dependencies=[]`` -- pysepal's own, unrelated to this task's
    ``dependencies=None`` invariant -- which starts a real asyncio task the
    moment it first mounts. That needs a running event loop this bare
    ``solara.render()`` harness does not have, so tests that are not
    exercising ``ExportsPanel`` itself substitute this instead of hitting it
    by accident."""


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
    assert len(mapapp.right_panel_content) == 10
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
    transitions_section = mapapp.right_panel_content[6]
    assert transitions_section["title"] == msg("transitions.title")
    assert transitions_section["icon"] == "mdi-transit-transfer"
    assert transitions_section["description"] == msg("transitions.description")
    assert len(transitions_section["content"]) == 1
    results_section = mapapp.right_panel_content[7]
    assert results_section["title"] == msg("results.title")
    assert results_section["icon"] == "mdi-chart-bar"
    assert results_section["description"] == msg("results.description")
    assert len(results_section["content"]) == 1
    zonal_section = mapapp.right_panel_content[8]
    assert zonal_section["title"] == msg("zonal.title")
    assert zonal_section["icon"] == "mdi-table"
    assert zonal_section["description"] == msg("zonal.description")
    assert len(zonal_section["content"]) == 1
    exports_section = mapapp.right_panel_content[9]
    assert exports_section["title"] == msg("exports.title")
    assert exports_section["icon"] == "mdi-export-variant"
    assert exports_section["description"] == msg("exports.description")
    assert len(exports_section["content"]) == 1
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
    def _spy_land_cover_step(*, spec: Any = None, gee_interface: Any = None) -> None:
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


def test_the_run_step_shares_the_aoi_step_s_spec_and_gets_a_real_outcome(monkeypatch):
    """The Run step must read the SAME ``RunSpec`` reactive the AOI step
    writes -- a private copy would let Run display against a stale spec --
    and ``outcome`` must be the real ``BuildOutcome`` ``page.py`` derives from
    that spec via ``build_outcome``, not a placeholder. The shell's initial
    spec (``RunSpec()``) has no AOI, sensor or threshold, so the real
    ``build_outcome`` reports that as an empty outcome -- not a stand-in
    ``None`` that would make every panel after it unable to tell "not built"
    from "wired wrong"."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_aoi_step(*, spec: Any = None, map_: Any = None) -> None:
        captured["aoi_spec"] = spec

    @solara.component
    def _spy_run_step(*, spec: Any = None, outcome: Any = None) -> None:
        captured.update(run_spec=spec, outcome=outcome)

    monkeypatch.setattr(page_module, "AoiStep", _spy_aoi_step)
    monkeypatch.setattr(page_module, "RunStep", _spy_run_step)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    assert captured["run_spec"] is captured["aoi_spec"]
    assert isinstance(captured["outcome"], BuildOutcome)
    assert captured["outcome"] == BuildOutcome()


def test_the_layers_panel_is_wired_with_the_shared_outcome_and_the_real_map_and_gee_interface(
    monkeypatch,
):
    """``right_panel_content[0]["content"]`` above is checked only by length:
    a placeholder widget, or a panel built with ``map_=None``, both pass it.
    Substituting a spy for ``MapLayersPanel`` and reading what ``Sdg1531App``
    actually calls it with proves the identity instead -- the SAME ``maps``
    ``page.py``'s own ``outcome`` carries (not a private copy that would
    never see a build), the real ``SepalMap`` the layers must be drawn onto,
    and the real session-backed ``gee_interface``.

    Driving a real build through the shared spec (rather than asserting on
    the initial, unbuilt ``None``) is deliberate: ``None is None`` would pass
    this identity check even if ``page.py`` wired a hardcoded ``None``
    instead of the real outcome."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_run_step(*, spec: Any = None, outcome: Any = None) -> None:
        captured["spec"] = spec
        captured["outcome"] = outcome

    @solara.component
    def _spy_map_layers_panel(
        *, maps: Any = None, map_: Any = None, gee_interface: Any = None
    ) -> None:
        captured.update(panel_maps=maps, map_=map_, gee_interface=gee_interface)

    monkeypatch.setattr(page_module, "RunStep", _spy_run_step)
    monkeypatch.setattr(page_module, "MapLayersPanel", _spy_map_layers_panel)
    monkeypatch.setattr(page_module, "ExportsPanel", _noop_exports_panel)

    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    captured["spec"].value = _BUILDABLE_SPEC

    mapapp = find_widget(box, MapApp)
    assert mapapp is not None

    assert captured["outcome"].maps is not None
    assert captured["panel_maps"] is captured["outcome"].maps
    # `is`, not `isinstance`: a second, unrelated SepalMap would still pass an
    # isinstance check while drawing the seven layers onto a map the user is
    # not looking at -- `mapapp.main_map[0]` is the one actually in the tree.
    assert captured["map_"] is mapapp.main_map[0]
    assert captured["gee_interface"] is not None


def test_the_results_panel_is_wired_with_the_shared_outcome_and_gee_interface(monkeypatch):
    """Same identity concern as the layers panel above, for the two values
    ``ResultsPanel`` needs: the ``maps`` AND the ``ctx`` a real build
    produces (not private copies that would never see one), and the real
    session-backed ``gee_interface``."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_run_step(*, spec: Any = None, outcome: Any = None) -> None:
        captured["spec"] = spec
        captured["outcome"] = outcome

    @solara.component
    def _spy_results_panel(*, maps: Any = None, ctx: Any = None, gee_interface: Any = None) -> None:
        captured.update(panel_maps=maps, panel_ctx=ctx, gee_interface=gee_interface)

    monkeypatch.setattr(page_module, "RunStep", _spy_run_step)
    monkeypatch.setattr(page_module, "ResultsPanel", _spy_results_panel)
    monkeypatch.setattr(page_module, "ExportsPanel", _noop_exports_panel)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    captured["spec"].value = _BUILDABLE_SPEC

    assert captured["outcome"].maps is not None
    assert captured["panel_maps"] is captured["outcome"].maps
    assert captured["panel_ctx"] is captured["outcome"].ctx
    assert captured["gee_interface"] is not None


def test_the_transitions_panel_is_wired_with_the_shared_outcome_and_gee_interface(monkeypatch):
    """Same identity concern as the results panel above, for the two values
    ``TransitionsPanel`` needs: the ``maps`` AND the ``ctx`` a real build
    produces (not private copies that would never see one), and the real
    session-backed ``gee_interface``."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_run_step(*, spec: Any = None, outcome: Any = None) -> None:
        captured["spec"] = spec
        captured["outcome"] = outcome

    @solara.component
    def _spy_transitions_panel(
        *, maps: Any = None, ctx: Any = None, gee_interface: Any = None
    ) -> None:
        captured.update(panel_maps=maps, panel_ctx=ctx, gee_interface=gee_interface)

    monkeypatch.setattr(page_module, "RunStep", _spy_run_step)
    monkeypatch.setattr(page_module, "TransitionsPanel", _spy_transitions_panel)
    monkeypatch.setattr(page_module, "ExportsPanel", _noop_exports_panel)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    captured["spec"].value = _BUILDABLE_SPEC

    assert captured["outcome"].maps is not None
    assert captured["panel_maps"] is captured["outcome"].maps
    assert captured["panel_ctx"] is captured["outcome"].ctx
    assert captured["gee_interface"] is not None


def test_the_zonal_panel_is_wired_with_the_shared_outcome_and_a_sepal_client(monkeypatch):
    """Same identity concern as the results panel above, for the two shared
    values ``ZonalPanel`` needs plus its own extra dependency: a
    ``sepal_client``, without which the shapefile download has nothing to
    upload through."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_run_step(*, spec: Any = None, outcome: Any = None) -> None:
        captured["spec"] = spec
        captured["outcome"] = outcome

    @solara.component
    def _spy_zonal_panel(
        *, maps: Any = None, ctx: Any = None, gee_interface: Any = None, sepal_client: Any = None
    ) -> None:
        captured.update(
            panel_maps=maps, panel_ctx=ctx, gee_interface=gee_interface, sepal_client=sepal_client
        )

    monkeypatch.setattr(page_module, "RunStep", _spy_run_step)
    monkeypatch.setattr(page_module, "ZonalPanel", _spy_zonal_panel)
    monkeypatch.setattr(page_module, "ExportsPanel", _noop_exports_panel)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    captured["spec"].value = _BUILDABLE_SPEC

    assert captured["outcome"].maps is not None
    assert captured["panel_maps"] is captured["outcome"].maps
    assert captured["panel_ctx"] is captured["outcome"].ctx
    assert captured["gee_interface"] is not None
    # `get_current_sepal_client()`'s documented "no SEPAL identity" case
    # returns `None` outside a sandbox, which is exactly this test
    # environment -- the identity that matters here is that `page.py` calls
    # it at all and passes the result through, not a particular truthiness.
    assert "sepal_client" in captured


def test_the_exports_panel_is_wired_with_the_shared_outcome_spec_and_gee_interface(monkeypatch):
    """Same identity concern as the results and zonal panels above, plus two
    of its own: the ``RunSpec`` value ``page.py`` reads out of the SAME spec
    reactive the AOI step writes (M4: ``ExportsPanel.spec`` is a plain
    ``RunSpec`` now, not a reactive), and ``gee_interface`` must be the real
    session interface, not ``None`` -- a ``None`` here would leave
    ``ExportLauncher`` to resolve ``get_current_gee_interface()`` itself,
    which raises outside a SEPAL session (``app/panels/exports.py``'s
    ``ExportsPanel`` docstring)."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_aoi_step(*, spec: Any = None, map_: Any = None) -> None:
        captured["aoi_spec"] = spec

    @solara.component
    def _spy_run_step(*, spec: Any = None, outcome: Any = None) -> None:
        captured["outcome"] = outcome

    @solara.component
    def _spy_exports_panel(
        *, maps: Any = None, ctx: Any = None, spec: Any = None, gee_interface: Any = None
    ) -> None:
        captured.update(
            exports_maps=maps,
            exports_ctx=ctx,
            exports_spec=spec,
            exports_gee_interface=gee_interface,
        )

    monkeypatch.setattr(page_module, "AoiStep", _spy_aoi_step)
    monkeypatch.setattr(page_module, "RunStep", _spy_run_step)
    monkeypatch.setattr(page_module, "ExportsPanel", _spy_exports_panel)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    captured["aoi_spec"].value = _BUILDABLE_SPEC

    assert captured["outcome"].maps is not None
    assert captured["exports_maps"] is captured["outcome"].maps
    assert captured["exports_ctx"] is captured["outcome"].ctx
    assert isinstance(captured["exports_spec"], RunSpec)
    assert captured["exports_spec"] is captured["aoi_spec"].value
    assert captured["exports_gee_interface"] is not None


def test_the_outcome_memo_recomputes_on_a_real_edit_not_on_an_unrelated_rerender(monkeypatch):
    """``RunSpec`` is a frozen dataclass of plain data, so it compares by
    field equality; reacton's own `use_memo` compares its dependency list the
    same way (`reacton.utils.equals`, which falls through to plain `==` for
    anything it has no special case for -- measured by reading the source,
    not assumed). So an unrelated re-render that leaves `spec` structurally
    equal to what it already was must NOT recompute `outcome` -- only a real
    edit does. This is the trap the brief warns about turned into a real
    assertion: proving the memo re-fires is not enough on its own (a
    `RunStep`/panel test could still pass while page.py never threads the new
    outcome anywhere useful), but this pins the OTHER half -- that page.py's
    memo does not fire needlessly either, at the exact granularity that
    matters for cost (an unrelated re-render must not re-run a real build).
    """
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_run_step(*, spec: Any = None, outcome: Any = None) -> None:
        captured["spec"] = spec
        captured["outcome"] = outcome

    monkeypatch.setattr(page_module, "RunStep", _spy_run_step)
    monkeypatch.setattr(page_module, "ExportsPanel", _noop_exports_panel)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    first_outcome = captured["outcome"]
    spec = captured["spec"]

    # A structurally-equal-but-new `RunSpec` object -- not the exact same
    # instance -- forces a re-render without changing what `spec.value`
    # equals.
    spec.value = RunSpec()
    rc.force_update()
    assert captured["outcome"] is first_outcome

    # A real, nested edit -- this must recompute.
    spec.value = _BUILDABLE_SPEC
    assert captured["outcome"] is not first_outcome
    assert captured["outcome"].maps is not None


def test_changing_the_spec_does_not_leave_a_stale_build_on_a_panel(monkeypatch):
    """The final review's blocking defect, pinned where it actually broke: at
    a PANEL, not at the memo. Build under one period, change it to a
    DIFFERENT buildable period, and the exports panel -- the brief's own
    example of where a stale value ships a wrong asset -- must reflect the
    CURRENT spec.

    Anchored against `resolved.spec.periods.overall`, a literal field the
    domain's own `ResolvedSpec` carries (`sdg1531.resolve.ResolvedSpec.spec`)
    -- not a value `build_outcome` computes itself, so a mutation that breaks
    `build_outcome`'s own logic cannot also fake this anchor into agreeing
    with itself.
    """
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_run_step(*, spec: Any = None, outcome: Any = None) -> None:
        captured["spec"] = spec

    @solara.component
    def _spy_exports_panel(
        *, maps: Any = None, ctx: Any = None, spec: Any = None, gee_interface: Any = None
    ) -> None:
        captured["exports_maps"] = maps

    monkeypatch.setattr(page_module, "RunStep", _spy_run_step)
    monkeypatch.setattr(page_module, "ExportsPanel", _spy_exports_panel)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    spec = captured["spec"]

    first = default_spec(
        threshold=0.0, periods=replace(DEFAULT_PERIODS, overall=Period(2001, 2015))
    )
    spec.value = first
    assert captured["exports_maps"] is not None
    assert captured["exports_maps"].resolved.spec.periods.overall == Period(2001, 2015)

    second = first.evolve(periods=replace(first.periods, overall=Period(2005, 2020)))
    spec.value = second
    assert captured["exports_maps"].resolved.spec.periods.overall == Period(2005, 2020)


def test_a_real_refusal_reaches_the_screen_through_the_real_wiring(monkeypatch):
    """The compositional gap fix round 1 flagged: ``build_outcome``'s error path
    (``test_step_run.py::test_build_outcome_carries_the_refusal_is_runnable_cannot_see``)
    and ``RunStep``'s rendering of ``outcome.error`` (``test_step_run.py``'s
    ``test_the_step_renders_only_its_own_text``, fed a hand-built ``BuildOutcome``)
    are each covered alone, but never joined -- the actual path a user hits runs
    a real spec through ``page.py``'s real ``use_memo`` into the real ``RunStep``.
    This drives that whole path and reads what actually landed on screen, with
    the real ``RunStep`` in the tree and no hand-built outcome anywhere.

    Only ``AoiStep`` is substituted, and only to reach the shared spec reactive
    without rendering its own ``AssetSelectComponent`` (the same concern the
    staleness regression test above has -- see its comment). ``RunStep`` is
    the real component; its rendered ``Sheet`` is read back off ``MapApp``'s own
    ``right_panel_content`` (a widget PROPERTY, not a reacton child of ``box`` --
    ``markdown_texts(box)`` finds nothing there, which is why every other test
    in this file reads identity off a spy instead of rendered text; this is the
    one test that needs the real text, so it reads it from where it actually
    lives instead).

    Anchored against a direct call to ``build()``, not a hardcoded guess at the
    domain's wording, so a change to that message updates both sides together.
    """
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_aoi_step(*, spec: Any = None, map_: Any = None) -> None:
        captured["spec"] = spec

    monkeypatch.setattr(page_module, "AoiStep", _spy_aoi_step)

    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    mapapp = find_widget(box, MapApp)
    assert mapapp is not None

    refusing_spec = default_spec()  # threshold=None: is_runnable() True, build() refuses
    with pytest.raises(Exception) as exc_info:
        build(refusing_spec)

    captured["spec"].value = refusing_spec

    # Index 4: the Run section (design decision A6; also pinned by
    # `test_the_steps_are_in_the_sub_indicator_order` and
    # `test_the_shell_builds_a_correctly_configured_mapapp`). `mapapp` is the
    # same widget instance across the re-render `.value =` above triggered
    # (`test_the_map_is_memoized_across_rerenders` proves that identity), so
    # its `right_panel_content` trait, read now, already reflects that render.
    run_sheet = mapapp.right_panel_content[4]["content"][0]
    assert markdown_texts(run_sheet)[-1] == f"<p><strong>{exc_info.value}</strong></p>"


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
