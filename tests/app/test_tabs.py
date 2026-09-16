"""The right-panel workflow: ten tabs, a segment strip to move between them.

Every ``page.py`` identity-wiring concern that used to be checked by
monkeypatching ``app.page``'s step/panel imports now targets ``app.tabs``
instead -- Task 21 moved those imports (and ``build_workflow_sections``,
renamed ``workflow_tabs``) out of ``page.py`` and into this module, since
``WorkflowTabs`` is what actually calls them now. ``page.py`` itself is
still exercised end to end here (``solara.render(page_module.Sdg1531App(),
...)``): only the monkeypatch TARGET moved, not the render entry point.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, ClassVar

import ipyvuetify as v
import pytest
import solara
from pysepal.sepalwidgets.vue_app import MapApp

from app import page as page_module
from app import tabs as tabs_module
from app.message import msg
from app.state import STEP_PREFIXES, problems_for
from app.steps.run import BuildOutcome, build
from app.tabs import TabDescriptor, _sync_draw_control, _tab_state, _TabState, workflow_tabs
from sdg1531.spec import Period, RunSpec
from tests.app.render_helpers import find_widget, find_widgets, markdown_texts
from tests.spec_factory import DEFAULT_PERIODS, default_spec

# `threshold=0.0`: `default_spec()`'s MODIS sensor needs a resolved float
# threshold for `build_indicator_maps()` to succeed (see
# `tests/app/test_step_run.py`); every test below that needs a REAL build,
# not just a runnable spec, uses this one.
_BUILDABLE_SPEC = default_spec(threshold=0.0)

_TAB_TITLES_IN_ORDER = (
    msg("step.aoi"),
    msg("step.productivity"),
    msg("step.land_cover"),
    msg("step.soc"),
    msg("step.run"),
    msg("layers.title"),
    msg("transitions.title"),
    msg("results.title"),
    msg("zonal.title"),
    msg("exports.title"),
)
_AOI_INDEX = 0
_PRODUCTIVITY_INDEX = 1
_RUN_INDEX = 4
_EXPORTS_INDEX = 9


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


def _workflow_widget(box: object) -> Any:
    """The real, reconciled ``WorkflowTabs`` widget.

    ``right_panel_content`` is a widget PROPERTY of ``MapApp``, not a reacton
    child of ``box`` -- ``find_widgets(box, ...)`` walks ``.children`` and
    finds nothing under it, the same reason ``markdown_texts(box)`` finds
    nothing there either (see ``test_a_real_refusal_reaches_the_screen_
    through_the_real_wiring``). This is the one section's sole content item.
    """
    mapapp = find_widget(box, MapApp)
    assert mapapp is not None
    workflow_widget: Any = mapapp.right_panel_content[0]["content"][0]
    return workflow_widget


def _wrapper_cells(root: object) -> list[Any]:
    """The ten segment-strip cells, in tab order.

    ``_SegmentCell`` builds two ``rv.Html`` divs per tab -- a padded,
    titled wrapper that owns the click and tooltip, and a plain inner bar
    that carries only the visual style -- so a ``title`` attribute is what
    picks the wrapper out from both. ``rv.Html`` is used nowhere else in this
    app's render tree.
    """
    return [w for w in find_widgets(root, v.Html) if w.attributes.get("title")]


# ---------------------------------------------------------------------------
# Order and shape -- pure `workflow_tabs()`, no render context at all.
# ---------------------------------------------------------------------------


def test_the_tabs_are_in_the_sub_indicator_order():
    """AOI -> Productivity -> Land cover -> SOC -> Run -> Layers ->
    Transitions -> Results -> Zonal -> Export (design decision A6; unchanged
    by Task 18's move into ``right_panel_content`` and Task 21's move from
    ten sections into one ``WorkflowTabs`` component). Position is what
    orders them -- ``WorkflowTabs`` renders ``workflow_tabs()`` as given, and
    a ``TabDescriptor`` has no ``id`` for a stray sort to key on.

    Compared against ``msg(...)`` rather than English literals so the
    assertion pins ORDER without also pinning the copy.
    """
    tabs = workflow_tabs()
    assert [tab.title for tab in tabs] == list(_TAB_TITLES_IN_ORDER)
    # Individual literals, not a second icon roster next to `workflow_tabs()`'s
    # own -- `tests/test_rosters.py` holds every hand-maintained roster of
    # string constants to an account, and a roster here would just restate the
    # one in `app/tabs.py` with nothing to check it against.
    #
    # A PIN, not a derivation: unlike the `msg(...)` titles above (checked
    # against the message catalogue, so a typo in either side shows up), an
    # mdi icon name has no second, independent source of truth in this repo
    # to import and compare against -- these ten strings are hand-typed here
    # against ten hand-typed strings in `app/tabs.py`, so both sides could be
    # wrong together and this would still pass. Kept anyway (matching the
    # pattern the original, reviewed `test_page.py` used) because a literal
    # match is still the only way to catch an icon that actually changed --
    # just don't mistake it for proof the icon is CORRECT, only that it is
    # UNCHANGED.
    assert tabs[0].icon == "mdi-map-marker-check"
    assert tabs[1].icon == "mdi-sprout-outline"
    assert tabs[2].icon == "mdi-terrain"
    assert tabs[3].icon == "mdi-layers-outline"
    assert tabs[4].icon == "mdi-play-circle-outline"
    assert tabs[5].icon == "mdi-layers"
    assert tabs[6].icon == "mdi-transit-transfer"
    assert tabs[7].icon == "mdi-chart-bar"
    assert tabs[8].icon == "mdi-table"
    assert tabs[9].icon == "mdi-export-variant"


def test_the_configuration_tabs_carry_their_state_prefixes_key_and_the_output_tabs_carry_none():
    """``tab.step`` is what ``_tab_state`` reads a configuration tab's
    problems by -- it must be a real ``STEP_PREFIXES`` key, not a
    hand-typed string that happens to look like one, or the two would drift
    apart silently. The five output tabs carry ``None``: they are gated by
    ``outcome.maps`` instead (see ``_tab_state``), not by any step's
    problems.
    """
    tabs = workflow_tabs()
    steps = [tab.step for tab in tabs]
    assert steps == [
        "aoi",
        "productivity",
        "land_cover",
        "soc",
        "run",
        None,
        None,
        None,
        None,
        None,
    ]
    for step in steps:
        if step is not None:
            assert step in STEP_PREFIXES


# ---------------------------------------------------------------------------
# `_tab_state` -- derived from `problems_for`/`outcome.maps`, not hand-assigned.
# ---------------------------------------------------------------------------


def test_a_configuration_tab_with_a_fatal_problem_is_incomplete():
    empty_spec = RunSpec()
    aoi_tab = TabDescriptor("aoi", "AOI", "mdi-x", [])
    assert any(p.fatal for p in problems_for("aoi", empty_spec))
    assert _tab_state(aoi_tab, empty_spec, has_maps=False) is _TabState.INCOMPLETE


def test_a_configuration_tab_with_no_fatal_problem_is_satisfied():
    aoi_tab = TabDescriptor("aoi", "AOI", "mdi-x", [])
    assert _tab_state(aoi_tab, _BUILDABLE_SPEC, has_maps=False) is _TabState.SATISFIED


def test_an_output_tab_is_locked_without_maps_and_satisfied_with_them():
    output_tab = TabDescriptor(None, "Layers", "mdi-x", [])
    assert _tab_state(output_tab, RunSpec(), has_maps=False) is _TabState.LOCKED
    assert _tab_state(output_tab, RunSpec(), has_maps=True) is _TabState.SATISFIED


# ---------------------------------------------------------------------------
# `_sync_draw_control` -- a fast, isolated proof of the pure state machine.
# ---------------------------------------------------------------------------


class _FakeMap:
    """The narrow slice of ``SepalMap`` (really ``ipyleaflet.Map``)
    ``_sync_draw_control`` touches: ``dc``, ``controls``, ``add_control``,
    ``remove_control``. Mirrors this suite's existing fake-map convention
    (``tests/app/test_panel_map_layers.py``'s ``_RecordingMap``) rather than
    standing up a real, GEE-backed ``SepalMap`` for a check that needs none
    of it.
    """

    def __init__(self) -> None:
        self.dc = object()
        self.controls: list[object] = []

    def add_control(self, control: object) -> None:
        self.controls.append(control)

    def remove_control(self, control: object) -> None:
        self.controls.remove(control)


def test_sync_draw_control_removes_it_on_leaving_the_aoi_tab():
    map_ = _FakeMap()
    map_.add_control(map_.dc)

    was_hidden = _sync_draw_control(map_, aoi_active=False, was_hidden=False)

    assert was_hidden is True
    assert map_.dc not in map_.controls


def test_sync_draw_control_never_adds_a_control_the_user_never_placed():
    """Returning to the AOI tab must not conjure the control out of nothing
    -- only restore one THIS function removed."""
    map_ = _FakeMap()

    was_hidden = _sync_draw_control(map_, aoi_active=True, was_hidden=False)

    assert was_hidden is False
    assert map_.dc not in map_.controls


def test_sync_draw_control_restores_what_it_hid():
    map_ = _FakeMap()
    map_.add_control(map_.dc)
    was_hidden = _sync_draw_control(map_, aoi_active=False, was_hidden=False)
    assert map_.dc not in map_.controls

    was_hidden = _sync_draw_control(map_, aoi_active=True, was_hidden=was_hidden)

    assert was_hidden is False
    assert map_.dc in map_.controls


def test_sync_draw_control_is_a_no_op_with_no_map_or_no_control():
    assert _sync_draw_control(None, aoi_active=False, was_hidden=True) is True

    class _NoDrawControl:
        controls: ClassVar[list[object]] = []

    assert _sync_draw_control(_NoDrawControl(), aoi_active=True, was_hidden=True) is True


# ---------------------------------------------------------------------------
# Identity wiring -- `page.py` -> `WorkflowTabs` -> each step/panel, end to
# end through the real `Sdg1531App` render. Monkeypatches target `tabs_module`
# now, since that is what actually imports and calls each step/panel.
# ---------------------------------------------------------------------------


def test_the_aoi_step_is_wired_with_the_shared_spec_and_a_real_map(monkeypatch):
    """Substituting a spy for ``AoiStep`` and reading what ``WorkflowTabs``
    actually calls it with proves identity: the same reactive ``Sdg1531App``
    holds, not a private copy, and the real ``SepalMap``, not ``None``."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_aoi_step(*, spec: Any = None, map_: Any = None) -> None:
        captured.update(spec=spec, map_=map_)

    monkeypatch.setattr(tabs_module, "AoiStep", _spy_aoi_step)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    assert isinstance(captured.get("spec"), solara.Reactive)
    assert isinstance(captured["spec"].value, RunSpec)
    assert captured.get("map_") is not None


def test_the_productivity_step_shares_the_aoi_step_s_spec(monkeypatch):
    """A private copy of ``RunSpec`` here would let Productivity edit a spec
    Run never sees."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_aoi_step(*, spec: Any = None, map_: Any = None) -> None:
        captured["aoi_spec"] = spec

    @solara.component
    def _spy_productivity_step(*, spec: Any = None) -> None:
        captured["productivity_spec"] = spec

    monkeypatch.setattr(tabs_module, "AoiStep", _spy_aoi_step)
    monkeypatch.setattr(tabs_module, "ProductivityStep", _spy_productivity_step)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    assert captured["productivity_spec"] is captured["aoi_spec"]


def test_the_land_cover_step_shares_the_aoi_step_s_spec(monkeypatch):
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_aoi_step(*, spec: Any = None, map_: Any = None) -> None:
        captured["aoi_spec"] = spec

    @solara.component
    def _spy_land_cover_step(*, spec: Any = None, gee_interface: Any = None) -> None:
        captured["land_cover_spec"] = spec

    monkeypatch.setattr(tabs_module, "AoiStep", _spy_aoi_step)
    monkeypatch.setattr(tabs_module, "LandCoverStep", _spy_land_cover_step)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    assert captured["land_cover_spec"] is captured["aoi_spec"]


def test_the_soc_step_shares_the_aoi_step_s_spec(monkeypatch):
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_aoi_step(*, spec: Any = None, map_: Any = None) -> None:
        captured["aoi_spec"] = spec

    @solara.component
    def _spy_soc_step(*, spec: Any = None) -> None:
        captured["soc_spec"] = spec

    monkeypatch.setattr(tabs_module, "AoiStep", _spy_aoi_step)
    monkeypatch.setattr(tabs_module, "SocStep", _spy_soc_step)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    assert captured["soc_spec"] is captured["aoi_spec"]


def test_the_run_step_shares_the_aoi_step_s_spec_and_gets_a_real_outcome(monkeypatch):
    """``outcome`` must be the real ``BuildOutcome`` ``page.py`` derives from
    the shared spec via ``build_outcome``, not a placeholder."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_aoi_step(*, spec: Any = None, map_: Any = None) -> None:
        captured["aoi_spec"] = spec

    @solara.component
    def _spy_run_step(*, spec: Any = None, outcome: Any = None) -> None:
        captured.update(run_spec=spec, outcome=outcome)

    monkeypatch.setattr(tabs_module, "AoiStep", _spy_aoi_step)
    monkeypatch.setattr(tabs_module, "RunStep", _spy_run_step)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    assert captured["run_spec"] is captured["aoi_spec"]
    assert isinstance(captured["outcome"], BuildOutcome)
    assert captured["outcome"] == BuildOutcome()


def test_the_layers_panel_is_wired_with_the_shared_outcome_and_the_real_map_and_gee_interface(
    monkeypatch,
):
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_run_step(*, spec: Any = None, outcome: Any = None) -> None:
        captured["spec"] = spec
        captured["outcome"] = outcome

    @solara.component
    def _spy_map_layers_panel(
        *, maps: Any = None, map_: Any = None, gee_interface: Any = None, shown: Any = None
    ) -> None:
        captured.update(panel_maps=maps, map_=map_, gee_interface=gee_interface, panel_shown=shown)

    monkeypatch.setattr(tabs_module, "RunStep", _spy_run_step)
    monkeypatch.setattr(tabs_module, "MapLayersPanel", _spy_map_layers_panel)
    monkeypatch.setattr(tabs_module, "ExportsPanel", _noop_exports_panel)

    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    captured["spec"].value = _BUILDABLE_SPEC

    mapapp = find_widget(box, MapApp)
    assert mapapp is not None

    assert captured["outcome"].maps is not None
    assert captured["panel_maps"] is captured["outcome"].maps
    assert captured["map_"] is mapapp.main_map[0]
    assert captured["gee_interface"] is not None
    assert isinstance(captured["panel_shown"], solara.Reactive)


def test_the_layers_panel_and_the_legend_share_the_same_shown_reactive(monkeypatch):
    """Task 24: a private copy of the shown set in either consumer would let
    one add a layer the other never finds out about."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_map_layers_panel(*, shown: Any = None, **_kwargs: Any) -> None:
        captured["panel_shown"] = shown

    @solara.component
    def _spy_map_legend(*, maps: Any = None, shown: Any = None) -> None:
        captured["legend_shown"] = shown

    monkeypatch.setattr(tabs_module, "MapLayersPanel", _spy_map_layers_panel)
    monkeypatch.setattr(page_module, "MapLegend", _spy_map_legend)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    assert isinstance(captured["panel_shown"], solara.Reactive)
    assert captured["panel_shown"] is captured["legend_shown"]


def test_the_results_panel_is_wired_with_the_shared_outcome_and_gee_interface(monkeypatch):
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_run_step(*, spec: Any = None, outcome: Any = None) -> None:
        captured["spec"] = spec
        captured["outcome"] = outcome

    @solara.component
    def _spy_results_panel(*, maps: Any = None, ctx: Any = None, gee_interface: Any = None) -> None:
        captured.update(panel_maps=maps, panel_ctx=ctx, gee_interface=gee_interface)

    monkeypatch.setattr(tabs_module, "RunStep", _spy_run_step)
    monkeypatch.setattr(tabs_module, "ResultsPanel", _spy_results_panel)
    monkeypatch.setattr(tabs_module, "ExportsPanel", _noop_exports_panel)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    captured["spec"].value = _BUILDABLE_SPEC

    assert captured["outcome"].maps is not None
    assert captured["panel_maps"] is captured["outcome"].maps
    assert captured["panel_ctx"] is captured["outcome"].ctx
    assert captured["gee_interface"] is not None


def test_the_transitions_panel_is_wired_with_the_shared_outcome_and_gee_interface(monkeypatch):
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

    monkeypatch.setattr(tabs_module, "RunStep", _spy_run_step)
    monkeypatch.setattr(tabs_module, "TransitionsPanel", _spy_transitions_panel)
    monkeypatch.setattr(tabs_module, "ExportsPanel", _noop_exports_panel)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    captured["spec"].value = _BUILDABLE_SPEC

    assert captured["outcome"].maps is not None
    assert captured["panel_maps"] is captured["outcome"].maps
    assert captured["panel_ctx"] is captured["outcome"].ctx
    assert captured["gee_interface"] is not None


def test_the_zonal_panel_is_wired_with_the_shared_outcome_and_a_sepal_client(monkeypatch):
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

    monkeypatch.setattr(tabs_module, "RunStep", _spy_run_step)
    monkeypatch.setattr(tabs_module, "ZonalPanel", _spy_zonal_panel)
    monkeypatch.setattr(tabs_module, "ExportsPanel", _noop_exports_panel)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    captured["spec"].value = _BUILDABLE_SPEC

    assert captured["outcome"].maps is not None
    assert captured["panel_maps"] is captured["outcome"].maps
    assert captured["panel_ctx"] is captured["outcome"].ctx
    assert captured["gee_interface"] is not None
    # `get_current_sepal_client()`'s documented "no SEPAL identity" case returns
    # `None` outside a sandbox, which is exactly this test environment -- the
    # identity that matters here is that it is called and threaded through at
    # all, not a particular truthiness.
    assert "sepal_client" in captured


def test_the_exports_panel_is_wired_with_the_shared_outcome_spec_and_gee_interface(monkeypatch):
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

    monkeypatch.setattr(tabs_module, "AoiStep", _spy_aoi_step)
    monkeypatch.setattr(tabs_module, "RunStep", _spy_run_step)
    monkeypatch.setattr(tabs_module, "ExportsPanel", _spy_exports_panel)

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
    """``RunSpec`` compares by field equality, and reacton's own ``use_memo``
    compares its dependency list the same way, so an unrelated re-render that
    leaves ``spec`` structurally equal to what it already was must NOT
    recompute ``page.py``'s ``outcome`` -- only a real edit does.
    """
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_run_step(*, spec: Any = None, outcome: Any = None) -> None:
        captured["spec"] = spec
        captured["outcome"] = outcome

    monkeypatch.setattr(tabs_module, "RunStep", _spy_run_step)
    monkeypatch.setattr(tabs_module, "ExportsPanel", _noop_exports_panel)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    first_outcome = captured["outcome"]
    spec = captured["spec"]

    spec.value = RunSpec()
    rc.force_update()
    assert captured["outcome"] is first_outcome

    spec.value = _BUILDABLE_SPEC
    assert captured["outcome"] is not first_outcome
    assert captured["outcome"].maps is not None


def test_changing_the_spec_does_not_leave_a_stale_build_on_a_panel(monkeypatch):
    """Build under one period, change it to a DIFFERENT buildable period, and
    the exports panel must reflect the CURRENT spec, not a stale one.

    Anchored against ``resolved.spec.periods.overall``, a literal field the
    domain's own ``ResolvedSpec`` carries -- not a value ``build_outcome``
    computes itself, so a mutation that breaks ``build_outcome``'s own logic
    cannot also fake this anchor into agreeing with itself.
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

    monkeypatch.setattr(tabs_module, "RunStep", _spy_run_step)
    monkeypatch.setattr(tabs_module, "ExportsPanel", _spy_exports_panel)

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
    """The real path a user hits runs a real spec through ``page.py``'s real
    ``use_memo`` into the real ``RunStep``, inside the real ``WorkflowTabs``.
    Only ``AoiStep`` is substituted, and only to reach the shared spec
    reactive without rendering its own ``AssetSelectComponent``.

    ``RunStep``'s rendered content is read back off the Run ``TabItem`` --
    a widget PROPERTY of ``MapApp.right_panel_content``'s sole section, not a
    reacton child of ``box`` -- the same reason every other test in this file
    reads identity off a spy instead of rendered text.

    Anchored against a direct call to ``build()``, not a hardcoded guess at
    the domain's wording, so a change to that message updates both sides
    together.
    """
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_aoi_step(*, spec: Any = None, map_: Any = None) -> None:
        captured["spec"] = spec

    monkeypatch.setattr(tabs_module, "AoiStep", _spy_aoi_step)

    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    mapapp = find_widget(box, MapApp)
    assert mapapp is not None

    refusing_spec = default_spec()  # threshold=None: is_runnable() True, build() refuses
    with pytest.raises(Exception) as exc_info:
        build(refusing_spec)

    captured["spec"].value = refusing_spec

    workflow_widget = mapapp.right_panel_content[0]["content"][0]
    tab_items = find_widgets(workflow_widget, v.TabItem)
    assert len(tab_items) == 10
    run_sheet = tab_items[_RUN_INDEX]
    assert markdown_texts(run_sheet)[-1] == f"<p><strong>{exc_info.value}</strong></p>"


# ---------------------------------------------------------------------------
# `WorkflowTabs` itself: renders ten tabs, the active index selects which
# `TabItem`'s content is live, and switching tabs does not rebuild the rest.
# ---------------------------------------------------------------------------


def test_workflow_tabs_renders_ten_tab_items_and_ten_segments():
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    workflow_widget = _workflow_widget(box)

    tab_items = find_widgets(workflow_widget, v.TabItem)
    assert len(tab_items) == 10

    cells = _wrapper_cells(workflow_widget)
    assert len(cells) == 10


def test_clicking_a_segment_moves_the_active_tab():
    """The active index selects which ``TabItem``'s content is live:
    ``rv.TabsItems.v_model`` is what Vuetify reads to decide that, so a real
    click through the real segment cell must change it. Also the direct
    counter-proof for the ``rv.TabsItems(v_model=0)`` mutation: hardcoding
    the index would leave this stuck at 0."""
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    workflow_widget = _workflow_widget(box)

    tabs_items_widget = find_widget(workflow_widget, v.TabsItems)
    assert tabs_items_widget is not None
    assert tabs_items_widget.v_model == _AOI_INDEX

    cells = _wrapper_cells(workflow_widget)
    cells[_PRODUCTIVITY_INDEX].fire_event("click", None)
    rc.force_update()

    tabs_items_widget = find_widget(_workflow_widget(box), v.TabsItems)
    assert tabs_items_widget is not None
    assert tabs_items_widget.v_model == _PRODUCTIVITY_INDEX


def test_a_locked_output_tab_does_not_navigate_on_click():
    """Layers/Transitions/Results/Zonal/Export are LOCKED while
    ``outcome.maps`` is ``None`` (the default, empty spec) -- clicking their
    segment must be a genuine no-op, not merely visually muted. Directly
    catches "mark every step unlocked regardless of state": under that
    mutation this click WOULD navigate.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    cells = _wrapper_cells(_workflow_widget(box))
    cells[_EXPORTS_INDEX].fire_event("click", None)
    rc.force_update()

    tabs_items_widget = find_widget(_workflow_widget(box), v.TabsItems)
    assert tabs_items_widget is not None
    assert tabs_items_widget.v_model == _AOI_INDEX


def test_a_locked_segment_cell_also_carries_pointer_events_none():
    """The test above proves inertness through the HANDLER's ``if not
    locked`` recheck alone -- ``fire_event`` calls the registered Python
    callback directly and never dispatches a real browser pointer event, so
    nothing else in this suite exercises ``_SegmentCell``'s CSS half. The
    handler recheck is genuinely sufficient on its own (the hook must attach
    on every render regardless of state, so the no-op has to live inside it
    either way) -- but the reference this mirrors carries BOTH mechanisms for
    a reason: the CSS is what stops a locked cell from looking clickable in
    the first place, a job the handler alone does not do. Pinned here so a
    future edit does not read the CSS line as redundant and drop it.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    rc.force_update()  # settle ProductivityStep's mount-time threshold-seeding effect first

    cells = _wrapper_cells(_workflow_widget(box))
    assert "pointer-events: none" in cells[_EXPORTS_INDEX].style_
    assert "pointer-events: none" not in cells[_AOI_INDEX].style_


def test_switching_tabs_does_not_rebuild_the_others_widgets():
    """``rv.TabsItems`` hides inactive tabs client-side WITHOUT unmounting
    them; the ten ``TabItem`` calls happen in the same order on every render
    regardless of which is active, so reacton's positional reconciliation
    must keep every ``TabItem``'s underlying widget (and everything mounted
    inside it) stable across a switch, not tear it down and rebuild it.
    Checked the same way ``test_the_map_is_memoized_across_rerenders`` checks
    the shared map: by widget IDENTITY, not merely a repeat ``isinstance``.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    before = find_widgets(_workflow_widget(box), v.TabItem)
    assert len(before) == 10

    cells = _wrapper_cells(_workflow_widget(box))
    cells[_PRODUCTIVITY_INDEX].fire_event("click", None)
    rc.force_update()

    after = find_widgets(_workflow_widget(box), v.TabItem)
    assert len(after) == 10
    for i in (_AOI_INDEX, _RUN_INDEX, _EXPORTS_INDEX):
        assert after[i] is before[i], f"tab {i} was rebuilt on an unrelated tab switch"


def test_switching_away_from_aoi_clears_the_draw_control_and_restores_it_on_return():
    """``AoiStep`` mounts ``AoiView`` against the shared map, which owns
    ``map_.dc`` while the DRAW method is selected. Since ``TabsItems`` never
    unmounts the AOI tab, only ``WorkflowTabs``'s own mirroring effect can
    take the control off the map on a switch -- deleting that effect is
    exactly the mutation this proves against.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    mapapp = find_widget(box, MapApp)
    assert mapapp is not None
    sepal_map = mapapp.main_map[0]

    # Simulate the user having chosen the DRAW method while on the AOI tab --
    # `AoiView`'s own effect is what would normally do this; this test's
    # concern is `WorkflowTabs`'s side of the trap, not `AoiView`'s.
    sepal_map.add_control(sepal_map.dc)
    assert sepal_map.dc in sepal_map.controls

    cells = _wrapper_cells(_workflow_widget(box))
    cells[_PRODUCTIVITY_INDEX].fire_event("click", None)
    rc.force_update()

    assert sepal_map.dc not in sepal_map.controls

    cells = _wrapper_cells(_workflow_widget(box))
    cells[_AOI_INDEX].fire_event("click", None)
    rc.force_update()

    assert sepal_map.dc in sepal_map.controls
