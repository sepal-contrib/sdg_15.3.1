"""The right-panel workflow: three standard Vuetify tabs.

Every ``page.py`` identity-wiring concern that used to be checked by
monkeypatching ``app.page``'s step/panel imports now targets ``app.tabs``
instead -- Task 21 moved those imports (and ``build_workflow_sections``,
renamed ``workflow_tabs``) out of ``page.py`` and into this module, since
``WorkflowTabs`` is what actually calls them now. ``page.py`` itself is
still exercised end to end here (``solara.render(page_module.Sdg1531App(),
...)``): only the monkeypatch TARGET moved, not the render entry point.

Task 27 folded the five output tabs into one (``app.panels.outputs``); the
identity-wiring tests for the five panels it now calls (Layers, Transitions,
Results, Zonal, Export) moved to ``tests/app/test_panel_outputs.py`` along
with their monkeypatch target, for the same reason Task 21 moved them here in
the first place -- the thing they monkeypatch lives where it is actually
called from. Task 30 did the identical move a second time, for the OTHER
four configuration tabs (Assessment period, Productivity, Land cover, SOC):
they are folded into one PARAMS tab (``app.panels.params``), so their own
identity-wiring tests moved to ``tests/app/test_panel_params.py``, patching
``params_module`` instead of ``tabs_module``. What stays here is everything
about the TAB LEVEL: order/shape, lock state, the PARAMS tab's own combined
state, navigation, and the AOI step's own identity wiring (still called
directly from this module).

The hand-built segment strip and its prev/next arrows are gone -- the repo
owner asked for plain ``rv.Tabs`` instead (see ``app/tabs.py``'s docstring) --
and with them every test that had no subject but the strip: abbreviations,
per-state chip fills, the light/dark fill pair, ``pointer-events: none``, and
``nav_targets``. What those tests were protecting that still EXISTS -- three
navigable tabs, an outputs tab that cannot be reached before a build, the
active index really driving ``TabsItems`` -- is all still proven below,
against ``v.Tab`` instead of against a ``title``-carrying ``rv.Html``.
"""

from __future__ import annotations

from typing import Any, ClassVar

import ipyvuetify as v
import pytest
import solara
from pysepal.sepalwidgets.vue_app import MapApp

from app import page as page_module
from app import tabs as tabs_module
from app.message import messages, msg
from app.panels import map_layers as map_layers_module
from app.state import STEP_PREFIXES, problems_for
from app.steps.run import BuildOutcome, build
from app.tabs import (
    TabDescriptor,
    _sync_draw_control,
    _tab_state,
    _TabState,
    tab_reachable,
    workflow_tabs,
)
from sdg1531.spec import RunSpec
from tests.app.render_helpers import alert_texts, find_widget, find_widgets
from tests.spec_factory import default_spec

# `threshold=0.0`: `default_spec()`'s MODIS sensor needs a resolved float
# threshold for `build_indicator_maps()` to succeed (see
# `tests/app/test_step_run.py`); every test below that needs a REAL build,
# not just a runnable spec, uses this one.
_BUILDABLE_SPEC = default_spec(threshold=0.0)

_TAB_TITLES_IN_ORDER = (
    msg("tabs.aoi"),
    msg("tabs.params"),  # task 30: Assessment period/Productivity/Land cover/SOC, merged
    msg("tabs.results"),  # the merged outputs tab: its own key, NOT the ResultsPanel section's
)


def _index_of(step: str | tuple[str, ...] | None) -> int:
    """Where the tab identified by ``step`` sits, derived from ``workflow_tabs()``.

    NOT hand-typed literals, which is what these were until task 28's reorder
    showed why that is unsafe: moving the period step from position 4 to
    position 1 is a ROTATION, so every index from 1 to 4 kept its number while
    changing identity. Stale constants stayed numerically valid and silently
    pointed at the wrong tab -- the review reproduced the naive bump and found
    all four affected tests still passed, proving nothing their names claimed.

    ``_TAB_TITLES_IN_ORDER`` above deliberately does NOT use this: that roster
    is what pins the ORDER, so deriving it from the same source it checks would
    make it agree with itself. Everything below asks "the PARAMS tab", not
    "index 1", so identity is the right key for those and order is not their
    subject.
    """
    return next(i for i, tab in enumerate(workflow_tabs()) if tab.step == step)


_AOI_INDEX = _index_of("aoi")
# The merged PARAMS tab (task 30) is the one tab whose `step` is a tuple --
# found by shape, not by retyping its four step names a second time here.
_PARAMS_INDEX = next(i for i, tab in enumerate(workflow_tabs()) if isinstance(tab.step, tuple))
_OUTPUTS_INDEX = _index_of(None)  # the merged outputs tab carries no step id


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


@solara.component
def _noop_export_dialog_host(**_kwargs: Any) -> None:
    """A stand-in for ``map_layers._ExportDialogHost`` in tests that drive a
    REAL build. ``use_export_dialog`` mounts a task with ``dependencies=[]``,
    which schedules real async work through ``asyncio.create_task`` the moment
    it first renders -- and this bare ``solara.render()`` harness has no
    running loop. The host only mounts once a build exists (see its own
    docstring), so only the tests below that set a buildable spec need this.
    """


def _tab_buttons(root: object) -> list[Any]:
    """The three ``v.Tab`` widgets, in tab order.

    ``v.Tab`` appears nowhere else in this app's render tree, so the class
    alone identifies them -- no ``title``-attribute filter of the kind the
    old hand-built strip needed to tell its wrapper div from its inner one.
    """
    return find_widgets(root, v.Tab)


def _active_index(box: object) -> int:
    """Which tab's content ``rv.TabsItems`` is currently showing.

    Read off ``TabsItems``, not off the ``Tabs`` strip: the strip is the
    control, but ``TabsItems.v_model`` is what actually decides which
    ``TabItem`` is live, so it is the thing worth asserting on.
    """
    widget = find_widget(_workflow_widget(box), v.TabsItems)
    assert widget is not None
    index: int = widget.v_model
    return index


def _select_tab(box: object, rc: Any, index: int) -> None:
    """Activate a tab the way a real click does.

    Vuetify's own click handler sets the strip's ``v_model``; reacton's
    ``on_v_model`` then calls back into ``WorkflowTabs``. Writing the trait
    directly drives that same path, and -- unlike ``fire_event`` on a
    ``v.Tab`` -- it goes through the ``Tabs`` component that owns the
    selection, rather than around it.
    """
    strip = find_widget(_workflow_widget(box), v.Tabs)
    assert strip is not None
    strip.v_model = index
    rc.force_update()


# ---------------------------------------------------------------------------
# Order and shape -- pure `workflow_tabs()`, no render context at all.
# ---------------------------------------------------------------------------


def test_the_tabs_are_in_the_sub_indicator_order():
    """AOI -> PARAMS -> the merged outputs tab. Design decision A6's own
    order was unchanged by Task 18's move into ``right_panel_content``, Task
    21's move from ten sections into one ``WorkflowTabs`` component, and Task
    27's fold of the last five of those ten into one tab -- task 28 then
    moved the step long called "Run" to run first among the configuration
    steps, and task 30 folded it and the three remaining configuration tabs
    (Productivity, Land cover, SOC) into one PARAMS tab, in that same
    relative order (see ``app/panels/params.py``). Position is what orders
    them -- ``WorkflowTabs`` renders ``workflow_tabs()`` as given, and a
    ``TabDescriptor`` has no ``id`` for a stray sort to key on.

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
    # to import and compare against -- these three strings are hand-typed here
    # against three hand-typed strings in `app/tabs.py`, so both sides could be
    # wrong together and this would still pass. Kept anyway (matching the
    # pattern the original, reviewed `test_page.py` used) because a literal
    # match is still the only way to catch an icon that actually changed --
    # just don't mistake it for proof the icon is CORRECT, only that it is
    # UNCHANGED.
    assert tabs[0].icon == "mdi-map-marker-check"
    # "mdi-cogs", task 30: a settings-gear icon for the tab that is now
    # itself a settings panel, not any one folded step's own icon.
    assert tabs[1].icon == "mdi-cogs"
    assert tabs[2].icon == "mdi-chart-bar"


def test_the_configuration_tabs_carry_their_state_prefixes_key_and_the_output_tab_carries_none():
    """``tab.step`` is what ``_tab_state`` reads a tab's problems by -- a
    real ``STEP_PREFIXES`` key (or, for PARAMS since task 30, a tuple of
    them) for a configuration tab, never a hand-typed string that happens to
    look like one, or it would drift apart silently from ``app/state.py``.
    The merged outputs tab carries ``None``: it is gated by ``outcome.maps``
    instead (see ``_tab_state``), not by any step's problems.
    """
    tabs = workflow_tabs()
    steps = [tab.step for tab in tabs]
    assert steps[0] == "aoi"
    assert steps[1] == ("run", "productivity", "land_cover", "soc")
    assert steps[2] is None
    for step in steps:
        if step is None:
            continue
        names = (step,) if isinstance(step, str) else step
        for name in names:
            assert name in STEP_PREFIXES


# ---------------------------------------------------------------------------
# `_tab_state` -- derived from `problems_for`/`outcome.maps`, not hand-assigned.
# ---------------------------------------------------------------------------


def test_a_configuration_tab_other_than_aoi_is_locked_until_an_aoi_exists():
    """The repo owner's own ask: *"if the AOI is not set, PARAMS should be
    deactivated"*. Every parameter in PARAMS describes how to compute
    something over an area, so with no area chosen there is nothing any of
    them can be checked against.

    `RunSpec()` has no AOI AND fatal problems in all four PARAMS steps, so
    LOCKED must beat INCOMPLETE here -- a naive "report the worst state"
    ordering would return INCOMPLETE and leave the tab reachable.
    """
    params_tab = TabDescriptor(("run", "productivity", "land_cover", "soc"), "P", "i", [])
    assert _tab_state(params_tab, RunSpec(), has_maps=False) is _TabState.LOCKED


def test_the_aoi_tab_itself_is_never_locked_by_its_own_missing_aoi():
    """The asymmetry is the point: AOI is the one tab that is always
    reachable, because it is where the thing every other tab waits for gets
    chosen. Locking it would leave the app with no reachable tab at all.
    """
    aoi_tab = TabDescriptor("aoi", "AOI", "i", [])
    assert _tab_state(aoi_tab, RunSpec(), has_maps=False) is _TabState.INCOMPLETE


def test_choosing_an_aoi_unlocks_the_other_configuration_tabs():
    """The positive half: the lock is derived from the AOI's own problems, not
    hardcoded, so a spec that HAS an AOI must release it. Without this,
    `LOCKED` returned unconditionally would pass the two tests above."""
    params_tab = TabDescriptor(("run", "productivity", "land_cover", "soc"), "P", "i", [])
    with_aoi = RunSpec().evolve(aoi=default_spec().aoi)

    assert any(p.fatal for p in problems_for("productivity", with_aoi)), (
        "this spec must still have PARAMS problems, or the test cannot tell "
        "'unlocked' from 'satisfied'"
    )
    assert _tab_state(params_tab, with_aoi, has_maps=False) is _TabState.INCOMPLETE


def test_the_params_tab_is_rendered_disabled_until_an_aoi_is_chosen(monkeypatch):
    """The render-level half, through the real tree: `rv.Tab(disabled=...)` is
    what a user actually meets, and Vuetify refuses to activate it."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_aoi_step(*, spec: Any = None, map_: Any = None) -> None:
        captured["spec"] = spec

    monkeypatch.setattr(tabs_module, "AoiStep", _spy_aoi_step)
    monkeypatch.setattr(map_layers_module, "_ExportDialogHost", _noop_export_dialog_host)

    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    buttons = _tab_buttons(_workflow_widget(box))
    assert buttons[_PARAMS_INDEX].disabled is True
    assert buttons[_AOI_INDEX].disabled is False

    captured["spec"].value = _BUILDABLE_SPEC
    rc.force_update()

    assert _tab_buttons(_workflow_widget(box))[_PARAMS_INDEX].disabled is False


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


def test_a_combined_tab_is_incomplete_when_only_one_of_its_named_steps_has_a_fatal_problem():
    """PARAMS' own combining rule (task 30, defended in the task's report):
    satisfied only when EVERY step behind the chip is -- a single chip is the
    only signal a user watching the segment strip has for everything folded
    behind it, so reading it as satisfied while one of the four still has a
    fatal problem would be reporting a false all-clear.

    ``_BUILDABLE_SPEC`` clears every fatal problem across all four steps;
    breaking ONLY ``water_mask`` (owned by "land_cover" alone -- see
    ``app/state.py``'s ``STEP_PREFIXES``) must still flip the WHOLE combined
    chip to INCOMPLETE, not just a per-step state nothing outside this test
    renders on its own. Directly catches the brief's own named mutation:
    "make the PARAMS chip satisfied while one section still has a fatal
    problem".
    """
    # The real tab, not a hand-typed copy of its four step names: found by
    # shape, the same way `_PARAMS_INDEX` above is.
    params_tab = next(tab for tab in workflow_tabs() if isinstance(tab.step, tuple))
    spec = default_spec(threshold=0.0, water_mask=None)
    assert any(p.fatal for p in problems_for("land_cover", spec))
    assert not any(p.fatal for p in problems_for("run", spec))
    assert not any(p.fatal for p in problems_for("productivity", spec))
    assert not any(p.fatal for p in problems_for("soc", spec))
    assert _tab_state(params_tab, spec, has_maps=False) is _TabState.INCOMPLETE


def test_a_combined_tab_is_satisfied_only_once_every_named_step_is():
    """The positive half of the combining rule: nothing short of every named
    step being fatal-free reads as SATISFIED."""
    params_tab = next(tab for tab in workflow_tabs() if isinstance(tab.step, tuple))
    assert _tab_state(params_tab, _BUILDABLE_SPEC, has_maps=False) is _TabState.SATISFIED


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
# Identity wiring -- `page.py` -> `WorkflowTabs` -> the AOI step, end to end
# through the real `Sdg1531App` render. The other four steps' identity
# wiring (task 30: they render inside `ParamsPanel` now, not directly here)
# lives in `tests/app/test_panel_params.py`, patching `params_module`.
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


def test_a_real_refusal_reaches_the_screen_through_the_real_wiring(monkeypatch):
    """The real path a user hits runs a real spec through ``page.py``'s real
    ``use_memo`` into the real ``RunStep``, inside the real ``WorkflowTabs``
    (task 30: nested inside the real ``ParamsPanel``, alongside Productivity,
    Land cover and SOC). Only ``AoiStep`` is substituted, and only to reach
    the shared spec reactive without rendering its own ``AssetSelectComponent``.

    ``RunStep``'s rendered content is read back off the PARAMS ``TabItem`` --
    a widget PROPERTY of ``MapApp.right_panel_content``'s sole section, not a
    reacton child of ``box`` -- the same reason every other test in this file
    reads identity off a spy instead of rendered text. Checked by MEMBERSHIP
    in every alert the PARAMS tab renders, not by position: since task 30,
    Run's own section is FIRST among four (see ``app/panels/params.py``), not
    the tab's only content, so its refusal is no longer reliably the last
    message on the tab the way it was when Run held its own tab. Read off
    ``rv.Alert`` (``app/panels/problems.py``) rather than markdown, and as an
    ``"error"`` -- a build refusal is blocking, and the styled component is
    what now says so.

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
    assert len(tab_items) == 3
    params_sheet = tab_items[_PARAMS_INDEX]
    assert ("error", str(exc_info.value)) in alert_texts(params_sheet)


# ---------------------------------------------------------------------------
# `WorkflowTabs` itself: a standard `rv.Tabs` strip over three `TabItem`s, the
# active index selects which one's content is live, and switching does not
# rebuild the rest.
#
# The hand-built segment strip these tests used to drive is gone (see
# `app/tabs.py`'s own docstring: the repo owner asked for standard Vuetify
# tabs and no arrows). Everything it was tested FOR still has a test here --
# three navigable tabs, a locked outputs tab that cannot be reached, the
# active index actually driving `TabsItems` -- expressed against `v.Tab`
# instead of against a `title`-carrying `rv.Html` wrapper. What has no
# successor is what the strip alone had: abbreviations, per-state fills,
# `pointer-events: none`, and the arrows. Vuetify draws a disabled tab itself.
# ---------------------------------------------------------------------------


def test_workflow_tabs_renders_three_tab_items_and_three_tab_buttons():
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    workflow_widget = _workflow_widget(box)

    assert len(find_widgets(workflow_widget, v.TabItem)) == 3
    assert len(_tab_buttons(workflow_widget)) == 3


def test_each_tab_button_carries_its_title():
    """Standard tabs show the title itself -- there is no abbreviation and no
    hover tooltip standing in for one any more, so the label IS the whole
    affordance and must be the real, translated tab title."""
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    rendered = [button.children[0] for button in _tab_buttons(_workflow_widget(box))]
    assert rendered == [tab.title for tab in workflow_tabs()]


def test_every_locales_tab_labels_fit_the_strip_without_overflow_chevrons(monkeypatch):
    """The reason the strip does not reuse each step's own full title.

    Measured in a real browser at the app's own 450px panel: the strip is
    418px wide, Vuetify gives a tab ``min-width: 90px`` and ``padding: 0
    16px``, and its uppercase 14px Roboto label runs about 8.5px per
    character. The three full titles came to 418px in English -- exactly at
    the limit -- and 429px in Spanish, which tips Vuetify into drawing the
    overflow chevrons the repo owner asked to be rid of ("remove the arrows
    as well").

    This is a proxy for that measurement, not a re-measurement: it cannot see
    the real font, so it checks the thing a translator can actually break --
    total label LENGTH -- against a budget derived from the same geometry.
    The English titles that overflowed are 16 + 10 + 7 = 33 characters; the
    short labels are 3 + 10 + 7 = 20. A budget of 26 sits between them, so
    this fails on the layout that was measured as broken and passes on the
    one measured as fitting, in every shipped locale rather than only the one
    a developer happens to be running.

    Monkeypatches ``current_locale`` where ``BoundCatalog.msg`` looks it up
    rather than calling the global ``pysepal.i18n.set_locale`` -- see
    ``tests/app/test_panel_map_layers.py``'s identical comment for why.
    """
    import pysepal.i18n.binding as i18n_binding

    for code in messages.available_locales():
        monkeypatch.setattr(i18n_binding, "current_locale", lambda code=code: code)
        titles = [tab.title for tab in workflow_tabs()]
        assert len(titles) == 3, (code, titles)
        budget = sum(max(len(title), 3) for title in titles)
        assert budget <= 26, (code, titles, budget)


def test_selecting_a_tab_moves_the_active_tab():
    """The active index selects which ``TabItem``'s content is live:
    ``rv.TabsItems.v_model`` is what Vuetify reads to decide that, so driving
    the strip's own ``v_model`` -- which is what a real click does -- must
    change it. Also the direct counter-proof for the
    ``rv.TabsItems(v_model=0)`` mutation: hardcoding the index would leave
    this stuck at 0."""
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    assert _active_index(box) == _AOI_INDEX

    _select_tab(box, rc, _PARAMS_INDEX)

    assert _active_index(box) == _PARAMS_INDEX


def test_the_locked_output_tab_is_rendered_disabled():
    """The merged outputs tab is LOCKED while ``outcome.maps`` is ``None``
    (the default, empty spec). Vuetify refuses to activate a disabled tab and
    draws it dimmed, which is the whole of what the old strip needed a
    ``pointer-events: none`` wrapper plus a re-check inside its own click
    handler to achieve. Directly catches "mark every step unlocked regardless
    of state": under that mutation this tab's ``disabled`` reads ``False``.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    buttons = _tab_buttons(_workflow_widget(box))
    assert buttons[_OUTPUTS_INDEX].disabled is True
    # AOI is the only tab reachable from the empty spec this renders: PARAMS
    # is locked too, on the missing AOI rather than on a missing build (see
    # `test_the_params_tab_is_rendered_disabled_until_an_aoi_is_chosen`).
    assert buttons[_AOI_INDEX].disabled is False


def test_the_output_tab_stops_being_disabled_once_a_build_exists(monkeypatch):
    """The positive half of the test above, through the real render tree: the
    lock is derived from ``outcome.maps``, so a buildable spec must release
    it. Without this, ``disabled=True`` hardcoded on the outputs tab would
    pass every other test in this file."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_aoi_step(*, spec: Any = None, map_: Any = None) -> None:
        captured["spec"] = spec

    monkeypatch.setattr(tabs_module, "AoiStep", _spy_aoi_step)
    monkeypatch.setattr(map_layers_module, "_ExportDialogHost", _noop_export_dialog_host)

    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    assert _tab_buttons(_workflow_widget(box))[_OUTPUTS_INDEX].disabled is True

    captured["spec"].value = _BUILDABLE_SPEC
    rc.force_update()

    assert _tab_buttons(_workflow_widget(box))[_OUTPUTS_INDEX].disabled is False


def test_switching_tabs_does_not_rebuild_the_others_widgets():
    """``rv.TabsItems`` hides inactive tabs client-side WITHOUT unmounting
    them; the three ``TabItem`` calls happen in the same order on every
    render regardless of which is active, so reacton's positional
    reconciliation must keep every ``TabItem``'s underlying widget (and
    everything mounted inside it) stable across a switch, not tear it down
    and rebuild it. Checked the same way ``test_the_map_is_memoized_across_
    rerenders`` checks the shared map: by widget IDENTITY, not merely a
    repeat ``isinstance``.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    before = find_widgets(_workflow_widget(box), v.TabItem)
    assert len(before) == 3

    _select_tab(box, rc, _PARAMS_INDEX)

    after = find_widgets(_workflow_widget(box), v.TabItem)
    assert len(after) == 3
    for i in (_AOI_INDEX, _OUTPUTS_INDEX):
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

    _select_tab(box, rc, _PARAMS_INDEX)
    assert sepal_map.dc not in sepal_map.controls

    _select_tab(box, rc, _AOI_INDEX)
    assert sepal_map.dc in sepal_map.controls


# ---------------------------------------------------------------------------
# The workflow footer: Back / Next, in the panel's own footer slot.
# ---------------------------------------------------------------------------


def _capture_spec(monkeypatch: Any, captured: dict[str, Any]) -> None:
    """Swap ``AoiStep`` for a spy that hands back the shared spec reactive.

    The same two monkeypatches ``test_the_params_tab_is_rendered_disabled_
    until_an_aoi_is_chosen`` makes, factored out because the footer tests
    below need the identical setup: a handle on the spec so a test can put a
    real AOI on it, and no export dialog mounting real tasks.
    """

    @solara.component
    def _spy_aoi_step(*, spec: Any = None, map_: Any = None) -> None:
        captured["spec"] = spec

    monkeypatch.setattr(tabs_module, "AoiStep", _spy_aoi_step)
    monkeypatch.setattr(map_layers_module, "_ExportDialogHost", _noop_export_dialog_host)


def _footer_widget(box: object) -> Any:
    """The rendered ``WorkflowFooter``, out of ``MapApp``'s footer slot.

    ``right_panel_footer`` is a widget PROPERTY of ``MapApp``, reached the
    same way ``_workflow_widget`` reaches the panel's content -- neither is a
    reacton child of ``box``, so ``find_widgets(box, ...)`` walks past both.
    """
    mapapp = find_widget(box, MapApp)
    assert mapapp is not None
    footer: Any = mapapp.right_panel_footer[0]
    return footer


def _nav_buttons(root: object) -> dict[str, Any]:
    """The footer's buttons, keyed ``"back"`` / ``"next"``.

    A dict, not a pair: a direction that does not exist is not rendered at
    all, so the count varies by tab and positional indexing would silently
    read Next as Back on the first tab -- exactly the regression these tests
    are here to catch.
    """
    labels = {msg("nav.back"): "back", msg("nav.forward"): "next"}
    found: dict[str, Any] = {}
    for btn in find_widgets(root, v.Btn):
        text = next((c for c in btn.children if isinstance(c, str)), None)
        assert text in labels, f"unexpected button in the footer: {text!r}"
        found[labels[text]] = btn
    return found


def test_the_footer_is_mounted_in_the_panels_footer_slot_not_inside_a_tab():
    """The whole point of the pysepal slot: navigation sits outside the
    scrolling sections, so no tab's content carries it. Asserting BOTH halves
    is what stops it quietly reverting to a button at the end of a tab.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    assert set(_nav_buttons(_footer_widget(box))) == {"next"}  # AOI is the first tab
    items = find_widgets(_workflow_widget(box), v.TabItem)
    assert [len(find_widgets(item, v.Btn)) for item in items] == [0, 0, 0]


def test_the_footer_buttons_are_back_and_next(monkeypatch):
    """Just the direction, not the destination -- the repo owner asked for
    *"just the 'next >', or '< back'"*. The tab strip above already names
    where you are."""
    captured: dict[str, Any] = {}
    _capture_spec(monkeypatch, captured)

    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    captured["spec"].value = _BUILDABLE_SPEC
    rc.force_update()
    _nav_buttons(_footer_widget(box))["next"].click()  # onto PARAMS, where both show
    rc.force_update()

    buttons = _nav_buttons(_footer_widget(box))
    assert set(buttons) == {"back", "next"}
    # The arrow leads on Back and trails on Next, so the pair reads outward
    # from the middle of the bar.
    assert buttons["back"].children[0].children == ["mdi-arrow-left"]
    assert buttons["next"].children[1].children == ["mdi-arrow-right"]
    # `secondary`, so the bar is findable at the bottom of a long panel
    # without taking the colour the app spends on the work itself.
    assert buttons["back"].color == "secondary"
    assert buttons["next"].color == "secondary"


def test_a_direction_that_does_not_exist_is_not_rendered(monkeypatch):
    """No Back on the first tab, no Next on the last.

    Drawing it disabled instead would spend half the bar on a control that
    can never do anything. A direction that exists but is LOCKED is the other
    case and still renders -- checked below -- because there the user has
    something to fix.
    """
    captured: dict[str, Any] = {}
    _capture_spec(monkeypatch, captured)

    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    first = _nav_buttons(_footer_widget(box))
    assert set(first) == {"next"}
    # Present but locked, on the missing AOI: the distinction this test is for.
    assert first["next"].disabled is True
    assert first["next"].attributes["title"] == msg("nav.locked_params")

    captured["spec"].value = _BUILDABLE_SPEC
    rc.force_update()
    _nav_buttons(_footer_widget(box))["next"].click()
    rc.force_update()
    _nav_buttons(_footer_widget(box))["next"].click()  # onto the last tab
    rc.force_update()

    assert _active_index(box) == _OUTPUTS_INDEX
    assert set(_nav_buttons(_footer_widget(box))) == {"back"}


def test_next_unlocks_once_an_aoi_exists_and_names_where_it_goes(monkeypatch):
    """It tracks the same condition ``_tab_state`` locks the DESTINATION tab
    on -- a footer button that enabled while its target tab was still
    disabled would look like a dead control. Direct counter-proof for
    hardcoding ``enabled=True``.
    """
    captured: dict[str, Any] = {}
    _capture_spec(monkeypatch, captured)

    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    assert _nav_buttons(_footer_widget(box))["next"].disabled is True

    captured["spec"].value = _BUILDABLE_SPEC
    rc.force_update()

    forward = _nav_buttons(_footer_widget(box))["next"]
    assert forward.disabled is False
    assert forward.attributes["title"] == msg("nav.next", target=msg("tabs.params"))


def test_the_footer_moves_the_active_tab_in_both_directions(monkeypatch):
    """The footer and the tab strip drive the SAME index, which is why
    ``active_tab`` is owned by ``page.py`` rather than by either of them: the
    footer renders into a separate ``MapApp`` subtree, so a ``use_state``
    inside ``WorkflowTabs`` would be invisible to it.
    """
    captured: dict[str, Any] = {}
    _capture_spec(monkeypatch, captured)

    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    captured["spec"].value = _BUILDABLE_SPEC
    rc.force_update()

    assert _active_index(box) == _AOI_INDEX

    _nav_buttons(_footer_widget(box))["next"].click()
    rc.force_update()
    assert _active_index(box) == _PARAMS_INDEX

    _nav_buttons(_footer_widget(box))["back"].click()
    rc.force_update()
    assert _active_index(box) == _AOI_INDEX


def test_a_disabled_footer_button_does_not_move_the_active_tab():
    """Vuetify will not dispatch a click on a disabled button, but the handler
    re-checks anyway (``NavButton``'s ``_handle_click``) because this test
    drives the widget directly, past that guard. Without the re-check the
    empty spec below would jump to a tab the strip still refuses.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    forward = _nav_buttons(_footer_widget(box))["next"]
    assert forward.disabled is True
    forward.click()
    rc.force_update()

    assert _active_index(box) == _AOI_INDEX


def test_workflow_tabs_builds_no_navigation_of_its_own():
    """Navigation left ``workflow_tabs`` when it moved to the footer. A bare
    call is still content-free, which is what keeps every order/shape test
    above callable with no render context."""
    assert [len(tab.content) for tab in workflow_tabs()] == [0, 0, 0]


def test_tab_reachable_agrees_with_the_lock_the_strip_draws():
    """One rule, two readers: the footer must not enable a button onto a tab
    the strip renders disabled. Asserted against ``_tab_state`` itself rather
    than restating its conditions, and out of range is unreachable so the
    ends of the workflow need no special case at the call site.
    """
    tabs = workflow_tabs()
    empty = RunSpec()

    for index, tab in enumerate(tabs):
        locked = _tab_state(tab, empty, has_maps=False) is _TabState.LOCKED
        assert tab_reachable(tabs, index, empty, has_maps=False) is not locked

    assert tab_reachable(tabs, -1, empty, has_maps=False) is False
    assert tab_reachable(tabs, len(tabs), empty, has_maps=False) is False


def test_the_inline_fallback_renders_the_same_footer_inside_the_tabs(monkeypatch):
    """The degraded mode for a pysepal whose right panel has no footer slot.

    ``app/page.py``'s ``PANEL_FOOTER_SLOT`` is False there, and navigation
    falls back into this subtree so the app still navigates on the published
    pysepal that CI and the SEPAL image install. It is the SAME
    ``WorkflowFooter`` -- there is no second set of buttons to keep in sync,
    only a second place to put the one.
    """
    monkeypatch.setattr(map_layers_module, "_ExportDialogHost", _noop_export_dialog_host)
    spec = solara.reactive(RunSpec())
    active_tab = solara.reactive(0)

    box, rc = solara.render(
        tabs_module.WorkflowTabs(
            spec=spec,
            sepal_map=None,
            outcome=BuildOutcome(),
            shown_layers=solara.reactive(frozenset()),
            active_tab=active_tab,
            inline_footer=True,
        ),
        handle_error=False,
    )
    assert rc is not None

    # The footer's button -- Next alone, since tab 0 has nothing behind it --
    # and it is outside every TabItem.
    in_tabs = sum(len(find_widgets(item, v.Btn)) for item in find_widgets(box, v.TabItem))
    assert len(find_widgets(box, v.Btn)) == 1
    assert in_tabs == 0


def test_no_inline_footer_is_rendered_when_the_panel_slot_carries_it():
    """The other half: with the slot available the tabs subtree holds no
    navigation at all, so the footer is never drawn twice."""
    spec = solara.reactive(RunSpec())

    box, rc = solara.render(
        tabs_module.WorkflowTabs(
            spec=spec,
            sepal_map=None,
            outcome=BuildOutcome(),
            shown_layers=solara.reactive(frozenset()),
            active_tab=solara.reactive(0),
        ),
        handle_error=False,
    )
    assert rc is not None
    assert find_widgets(box, v.Btn) == []


def test_the_page_uses_the_footer_slot_when_the_installed_pysepal_has_one():
    """The capability gate itself, against the pysepal actually installed.

    ``PANEL_FOOTER_SLOT`` is read off ``MapApp.class_traits()`` rather than a
    version string, so this asserts the two agree: whichever branch the gate
    picks, the app must end up with exactly one footer -- in the slot, or
    inline, never both and never neither.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    mapapp = find_widget(box, MapApp)
    assert mapapp is not None
    in_slot = len(getattr(mapapp, "right_panel_footer", []))
    inline = sum(
        len(find_widgets(item, v.Btn)) for item in find_widgets(_workflow_widget(box), v.TabItem)
    )
    inline += len(find_widgets(_workflow_widget(box), v.Btn)) - inline

    if page_module.PANEL_FOOTER_SLOT:
        assert in_slot == 1
        assert inline == 0
    else:
        assert in_slot == 0
        assert inline == 1  # Next alone: the page opens on the first tab


def test_neither_tab_surface_paints_over_the_panel():
    """The strip and the tab content stay transparent.

    Vuetify paints ``.v-tabs-bar`` and ``.v-tabs-items`` with the theme's
    SURFACE colour, which is not the navigation drawer's -- measured in the
    browser as rgb(30,30,30) over the panel's rgb(26,26,26). The result was a
    lighter rectangle behind every tab's controls that read as a card, which
    pysepal's own ``demo_apps/solara_map_app`` (no tabs, content straight on
    the drawer) does not have.

    Asserted on the widgets rather than by eye because the difference is four
    values of grey: it went unnoticed through the whole of this app's
    development, and a default that comes back would go unnoticed again.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    workflow = _workflow_widget(box)

    strip = find_widget(workflow, v.Tabs)
    items = find_widget(workflow, v.TabsItems)
    assert strip is not None and items is not None

    assert strip.background_color == "transparent"
    assert "background-color: transparent" in (items.style_ or "")


def test_the_footer_is_one_unbroken_bar(monkeypatch):
    """Back and Next meet in the middle and run flush to both panel edges.

    A 6px seam was tried between them and taken back out: the pair reads as
    one bar, not two floating controls. What this pins is the geometry that
    makes that true -- no gap on the row, no margin on either button -- so
    the bar cannot drift into a pair of insets by accident.

    The margin half matters most at the ends of the workflow, where only one
    button renders: an inset there would pull the lone button off the panel
    edge it is supposed to sit flush against.
    """
    captured: dict[str, Any] = {}
    _capture_spec(monkeypatch, captured)

    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    captured["spec"].value = _BUILDABLE_SPEC
    rc.force_update()
    _nav_buttons(_footer_widget(box))["next"].click()
    rc.force_update()

    row = find_widget(_footer_widget(box), v.Html)
    assert row is not None
    assert "d-flex" in (row.class_ or "")
    assert "gap" not in (row.style_ or "")

    buttons = _nav_buttons(_footer_widget(box))
    assert set(buttons) == {"back", "next"}
    for button in buttons.values():
        assert "margin" not in (button.style_ or "")
