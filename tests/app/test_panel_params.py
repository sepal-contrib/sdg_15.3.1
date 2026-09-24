"""The merged PARAMS tab: four flat, headed sections.

Task 30 folded the four configuration tabs that follow AOI (Assessment
period, Productivity, Land cover, SOC) into one, ``app.panels.params.
ParamsPanel``, built the identical way task 28 built the merged outputs tab
(``app.panels.outputs.OutputsPanel``) -- flat sections, no accordion, each
introduced by ``app/panels/section_header.py``'s ``SectionHeader``. See
``app/panels/params.py``'s own module docstring for the full reasoning,
including why Assessment period stays FIRST.

The identity-wiring tests for the four steps this tab now calls moved here
from ``tests/app/test_tabs.py``, for the identical reason
``tests/app/test_panel_outputs.py``'s own docstring already gives for its
five: a monkeypatch targets the module that actually calls the thing, and
that is no longer ``app.tabs`` for these four -- it is ``app.panels.params``.
"""

from __future__ import annotations

from typing import Any

import ipyvuetify as v
import solara
from pysepal.sepalwidgets.vue_app import MapApp

from app import page as page_module
from app import tabs as tabs_module
from app.message import msg
from app.panels import params as params_module
from app.panels.params import param_sections
from app.steps.run import BuildOutcome
from tests.app.render_helpers import cell_texts, find_widget, find_widgets

# `param_sections()`'s own DISPLAY order -- see that function's docstring.
_RUN_INDEX = 0
_PRODUCTIVITY_INDEX = 1
_LAND_COVER_INDEX = 2
_SOC_INDEX = 3

# The merged PARAMS tab's own position among `workflow_tabs()`'s three --
# derived, not hand-typed, the same reason `test_panel_outputs.py`'s own
# `_OUTPUTS_TAB_INDEX` is: found by shape (the one tab whose `step` is a
# tuple), not by retyping a literal that could drift from `app/tabs.py`.
_PARAMS_TAB_INDEX = next(
    i for i, tab in enumerate(tabs_module.workflow_tabs()) if isinstance(tab.step, tuple)
)

_SECTION_TITLES_IN_ORDER = (
    msg("step.run"),
    msg("step.productivity"),
    msg("step.land_cover"),
    msg("step.soc"),
)

_SECTION_DESCRIPTIONS_IN_ORDER = (
    msg("run.description"),
    msg("productivity.description"),
    msg("land_cover.description"),
    msg("soc.description"),
)


def _workflow_widget(box: object) -> Any:
    """The real, reconciled ``WorkflowTabs`` widget -- same helper as
    ``tests/app/test_tabs.py``'s and ``tests/app/test_panel_outputs.py``'s,
    duplicated rather than imported, matching this suite's existing per-file
    convention."""
    mapapp = find_widget(box, MapApp)
    assert mapapp is not None
    workflow_widget: Any = mapapp.right_panel_content[0]["content"][0]
    return workflow_widget


# ---------------------------------------------------------------------------
# `param_sections()` -- pure, no render context. Mirrors `app.panels.outputs.
# output_sections`'s own order/shape tests.
# ---------------------------------------------------------------------------


def test_the_sections_are_in_the_period_first_order():
    """Assessment period -> Productivity -> Land cover -> SOC. Not
    arbitrary: ``app/steps/period_override.py``'s shared control shows the
    Land cover and SOC sections the window they INHERIT from Assessment
    period's own ``periods.overall`` -- that has to already be chosen, or
    the "inherited window" text they show is empty or misleading. This is
    also the mutation-catching test the brief names directly: reordering
    the sections so the period is not first fails here.
    """
    sections = param_sections()
    assert [s.title for s in sections] == list(_SECTION_TITLES_IN_ORDER)
    # Individual literals, not a second icon roster -- see
    # `test_panel_outputs.py`'s identical reasoning for why these are PINNED
    # against `app/panels/params.py`'s own hand-typed icons, not derived from
    # a second, independent source of truth.
    assert sections[0].icon == "mdi-calendar-range"
    assert sections[1].icon == "mdi-sprout-outline"
    assert sections[2].icon == "mdi-terrain"
    assert sections[3].icon == "mdi-layers-outline"


def test_there_are_exactly_four_sections():
    assert len(param_sections()) == 4


def test_each_sections_own_description_travels_with_it():
    """Each section's own ``msg("<step>.description")`` now rides along on
    the ``SectionDescriptor`` itself, for ``ParamsPanel`` to hand to
    ``SectionHeader`` -- the step components themselves no longer render it
    (see ``app/panels/params.py``'s own docstring, and
    ``test_panel_outputs.py``'s identical test for the precedent this
    follows)."""
    sections = param_sections()
    assert [s.description for s in sections] == list(_SECTION_DESCRIPTIONS_IN_ORDER)


# ---------------------------------------------------------------------------
# `ParamsPanel` rendered -- flat sections, title/description on screen.
# ---------------------------------------------------------------------------


def _section_titles(root: object) -> list[str]:
    """Every ``SectionHeader`` title in ``root``, in tree order.

    Selected on the header's own class rather than by taking every ``<span>``:
    a step is free to render spans of its own -- the transition matrix's value
    legend does -- and an unfiltered sweep would read those as section titles
    and fail for a reason that has nothing to do with what this test is for.
    """
    return [
        child
        for span in find_widgets(root, v.Html)
        if span.tag == "span" and "subtitle-2" in (span.class_ or "")
        for child in (span.children or [])
        if isinstance(child, str)
    ]


def test_every_sections_title_and_description_render_on_screen():
    """The render-level half of ``test_each_sections_own_description_travels_
    with_it`` above. Scoped to the PARAMS ``TabItem`` alone
    (``_PARAMS_TAB_INDEX``), not the whole workflow widget: the merged
    outputs tab ALSO uses ``SectionHeader`` for its own five sections, and
    ``rv.TabsItems`` never unmounts an inactive tab (``app/tabs.py``'s own
    docstring), so both tabs' spans/paragraphs are live in the same tree at
    once. ``tests/app/test_panel_outputs.py``'s own identical test scopes to
    the outputs ``TabItem`` for the same reason.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    workflow_widget = _workflow_widget(box)
    params_sheet = find_widgets(workflow_widget, v.TabItem)[_PARAMS_TAB_INDEX]
    assert _section_titles(params_sheet) == list(_SECTION_TITLES_IN_ORDER)
    assert cell_texts(params_sheet, "p") == list(_SECTION_DESCRIPTIONS_IN_ORDER)


# ---------------------------------------------------------------------------
# Identity wiring -- `app.tabs.WorkflowTabs` -> `ParamsPanel` -> each of the
# four steps, end to end through the real `Sdg1531App` render. Monkeypatches
# target `params_module`, since that is what actually calls each step now.
# ---------------------------------------------------------------------------


def test_the_productivity_step_shares_the_aoi_step_s_spec(monkeypatch):
    """A private copy of ``RunSpec`` here would let Productivity edit a spec
    AOI never sees."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_aoi_step(*, spec: Any = None, map_: Any = None) -> None:
        captured["aoi_spec"] = spec

    @solara.component
    def _spy_productivity_step(*, spec: Any = None) -> None:
        captured["productivity_spec"] = spec

    monkeypatch.setattr(tabs_module, "AoiStep", _spy_aoi_step)
    monkeypatch.setattr(params_module, "ProductivityStep", _spy_productivity_step)

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
    monkeypatch.setattr(params_module, "LandCoverStep", _spy_land_cover_step)

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
    monkeypatch.setattr(params_module, "SocStep", _spy_soc_step)

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
    monkeypatch.setattr(params_module, "RunStep", _spy_run_step)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    assert captured["run_spec"] is captured["aoi_spec"]
    assert isinstance(captured["outcome"], BuildOutcome)
    assert captured["outcome"] == BuildOutcome()


def test_the_land_cover_step_is_wired_with_a_real_gee_interface(monkeypatch):
    """``gee_interface`` is threaded through from ``page.py`` rather than
    left for ``LandCoverStep``'s own fallback to resolve -- the same
    identity-wiring concern every other step/panel in this app is checked
    against."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_land_cover_step(*, spec: Any = None, gee_interface: Any = None) -> None:
        captured["gee_interface"] = gee_interface

    monkeypatch.setattr(params_module, "LandCoverStep", _spy_land_cover_step)

    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    assert captured["gee_interface"] is not None
