"""The merged outputs tab: five panels as ``rv.ExpansionPanel`` sections.

Task 27 folded the five output tabs (Layers, Transitions, Results, Zonal,
Export) into one, ``app.panels.outputs.OutputsPanel``. The identity-wiring
tests for those five panels moved here from ``tests/app/test_tabs.py`` along
with their monkeypatch target -- Task 21's own reasoning for moving them
INTO ``test_tabs.py`` in the first place applies again: a monkeypatch targets
the module that actually calls the thing, and that is no longer ``app.tabs``
for these five.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import ipyvuetify as v
import solara
from pysepal.sepalwidgets.vue_app import MapApp

from app import page as page_module
from app import tabs as tabs_module
from app.message import msg
from app.panels import outputs as outputs_module
from app.panels.outputs import output_sections
from sdg1531.spec import Period, RunSpec
from tests.app.render_helpers import find_widget, find_widgets
from tests.spec_factory import DEFAULT_PERIODS, default_spec

# `threshold=0.0`: `default_spec()`'s MODIS sensor needs a resolved float
# threshold for `build_indicator_maps()` to succeed (see
# `tests/app/test_step_run.py`); every test below that needs a REAL build,
# not just a runnable spec, uses this one.
_BUILDABLE_SPEC = default_spec(threshold=0.0)

# `output_sections()`'s own DISPLAY order -- see that function's docstring.
_LAYERS_INDEX = 0
_TRANSITIONS_INDEX = 1
_RESULTS_INDEX = 2
_ZONAL_INDEX = 3
_EXPORTS_INDEX = 4

_SECTION_TITLES_IN_ORDER = (
    msg("layers.title"),
    msg("transitions.title"),
    msg("results.title"),
    msg("zonal.title"),
    msg("exports.title"),
)


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
    """The real, reconciled ``WorkflowTabs`` widget -- same helper as
    ``tests/app/test_tabs.py``'s, duplicated rather than imported: it is
    three lines, and every other fixture/fake in this suite is per-file
    already (``_FakeMaps``, ``_FakeNotifier``, ...).
    """
    mapapp = find_widget(box, MapApp)
    assert mapapp is not None
    workflow_widget: Any = mapapp.right_panel_content[0]["content"][0]
    return workflow_widget


# ---------------------------------------------------------------------------
# `output_sections()` -- pure, no render context. Mirrors `app.tabs.
# workflow_tabs`'s own order/shape tests.
# ---------------------------------------------------------------------------


def test_the_sections_are_in_the_old_tab_order():
    """Layers -> Transitions -> Results -> Zonal -> Export -- the brief's own
    words: "Section order is the old tab order and must not change". This is
    also the mutation-catching test for that promise: reordering two entries
    in ``output_sections()``'s return list, or dropping one, fails here (see
    ``test_there_are_exactly_five_sections`` for the drop case specifically).
    """
    sections = output_sections()
    assert [s.title for s in sections] == list(_SECTION_TITLES_IN_ORDER)
    # Individual literals, not a roster -- same reasoning as `app/tabs.py`'s
    # own icon assertions (`tests/test_rosters.py` would flag a tuple here as
    # an unaccounted-for hand-maintained string list; these five, like that
    # file's ten, are a PIN against `app/panels/outputs.py`'s own hand-typed
    # icons, not a derivation with a second source of truth to check against).
    assert sections[0].icon == "mdi-layers"
    assert sections[1].icon == "mdi-transit-transfer"
    assert sections[2].icon == "mdi-chart-bar"
    assert sections[3].icon == "mdi-table"
    assert sections[4].icon == "mdi-export-variant"


def test_there_are_exactly_five_sections():
    assert len(output_sections()) == 5


# ---------------------------------------------------------------------------
# `OutputsPanel` rendered -- which section opens by default, and the
# chart-mount `is_open` wiring for Results/Transitions.
# ---------------------------------------------------------------------------


def test_the_layers_section_is_open_by_default(monkeypatch):
    """Layers needs no button click to be useful (a read-only table of what a
    run produced); the other four show nothing until Compute is pressed, so
    opening one of those instead would still look empty. All five collapsed
    was rejected outright -- the brief this task follows is explicit that the
    tab must not open looking empty.
    """
    monkeypatch.setattr(outputs_module, "ExportsPanel", _noop_exports_panel)
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    expansion_panels = find_widget(_workflow_widget(box), v.ExpansionPanels)
    assert expansion_panels is not None
    assert expansion_panels.v_model == _LAYERS_INDEX


def test_there_are_exactly_five_expansion_panels(monkeypatch):
    monkeypatch.setattr(outputs_module, "ExportsPanel", _noop_exports_panel)
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    panels = find_widgets(_workflow_widget(box), v.ExpansionPanel)
    assert len(panels) == 5


# ---------------------------------------------------------------------------
# Identity wiring -- `app.tabs.WorkflowTabs` -> `OutputsPanel` -> each of the
# five panels, end to end through the real `Sdg1531App` render.
# ---------------------------------------------------------------------------


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
    monkeypatch.setattr(outputs_module, "MapLayersPanel", _spy_map_layers_panel)
    monkeypatch.setattr(outputs_module, "ExportsPanel", _noop_exports_panel)

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

    monkeypatch.setattr(outputs_module, "MapLayersPanel", _spy_map_layers_panel)
    monkeypatch.setattr(page_module, "MapLegend", _spy_map_legend)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    assert isinstance(captured["panel_shown"], solara.Reactive)
    assert captured["panel_shown"] is captured["legend_shown"]


def test_the_results_panel_is_wired_with_the_shared_outcome_gee_interface_and_is_open(monkeypatch):
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_run_step(*, spec: Any = None, outcome: Any = None) -> None:
        captured["spec"] = spec
        captured["outcome"] = outcome

    @solara.component
    def _spy_results_panel(
        *, maps: Any = None, ctx: Any = None, gee_interface: Any = None, is_open: Any = None
    ) -> None:
        captured.update(
            panel_maps=maps, panel_ctx=ctx, gee_interface=gee_interface, panel_is_open=is_open
        )

    monkeypatch.setattr(tabs_module, "RunStep", _spy_run_step)
    monkeypatch.setattr(outputs_module, "ResultsPanel", _spy_results_panel)
    monkeypatch.setattr(outputs_module, "ExportsPanel", _noop_exports_panel)

    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    captured["spec"].value = _BUILDABLE_SPEC

    assert captured["outcome"].maps is not None
    assert captured["panel_maps"] is captured["outcome"].maps
    assert captured["panel_ctx"] is captured["outcome"].ctx
    assert captured["gee_interface"] is not None
    # Layers is the section open by default, not Results -- see the chart-mount
    # trap `app/panels/outputs.py`'s module docstring explains.
    assert captured["panel_is_open"] is False

    expansion_panels = find_widget(_workflow_widget(box), v.ExpansionPanels)
    assert expansion_panels is not None
    expansion_panels.v_model = _RESULTS_INDEX
    rc.force_update()
    assert captured["panel_is_open"] is True


def test_the_transitions_panel_is_wired_with_the_shared_outcome_gee_interface_and_is_open(
    monkeypatch,
):
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_run_step(*, spec: Any = None, outcome: Any = None) -> None:
        captured["spec"] = spec
        captured["outcome"] = outcome

    @solara.component
    def _spy_transitions_panel(
        *, maps: Any = None, ctx: Any = None, gee_interface: Any = None, is_open: Any = None
    ) -> None:
        captured.update(
            panel_maps=maps, panel_ctx=ctx, gee_interface=gee_interface, panel_is_open=is_open
        )

    monkeypatch.setattr(tabs_module, "RunStep", _spy_run_step)
    monkeypatch.setattr(outputs_module, "TransitionsPanel", _spy_transitions_panel)
    monkeypatch.setattr(outputs_module, "ExportsPanel", _noop_exports_panel)

    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    captured["spec"].value = _BUILDABLE_SPEC

    assert captured["outcome"].maps is not None
    assert captured["panel_maps"] is captured["outcome"].maps
    assert captured["panel_ctx"] is captured["outcome"].ctx
    assert captured["gee_interface"] is not None
    assert captured["panel_is_open"] is False

    expansion_panels = find_widget(_workflow_widget(box), v.ExpansionPanels)
    assert expansion_panels is not None
    expansion_panels.v_model = _TRANSITIONS_INDEX
    rc.force_update()
    assert captured["panel_is_open"] is True


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
    monkeypatch.setattr(outputs_module, "ZonalPanel", _spy_zonal_panel)
    monkeypatch.setattr(outputs_module, "ExportsPanel", _noop_exports_panel)

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
    monkeypatch.setattr(outputs_module, "ExportsPanel", _spy_exports_panel)

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
    monkeypatch.setattr(outputs_module, "ExportsPanel", _noop_exports_panel)

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
    monkeypatch.setattr(outputs_module, "ExportsPanel", _spy_exports_panel)

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
