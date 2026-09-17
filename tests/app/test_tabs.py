"""The right-panel workflow: three tabs, a segment strip and prev/next arrows
to move between them.

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
about the TAB LEVEL: order/shape, lock state, the PARAMS chip's own combined
state, theme-driven chip colours, navigation (segments and the arrows), and
the AOI step's own identity wiring (still called directly from this module).
"""

from __future__ import annotations

from typing import Any, ClassVar

import ipyvuetify as v
import pytest
import solara
from pysepal.sepalwidgets.vue_app import MapApp
from pysepal.solara import get_current_theme_state

from app import page as page_module
from app import tabs as tabs_module
from app.message import messages, msg
from app.panels import outputs as outputs_module
from app.state import STEP_PREFIXES, problems_for
from app.steps.run import build
from app.tabs import (
    TabDescriptor,
    _seg_style,
    _sync_draw_control,
    _tab_abbrev,
    _tab_state,
    _TabState,
    nav_targets,
    workflow_tabs,
)
from sdg1531.spec import RunSpec
from tests.app.render_helpers import find_widget, find_widgets, markdown_texts
from tests.spec_factory import default_spec

# `threshold=0.0`: `default_spec()`'s MODIS sensor needs a resolved float
# threshold for `build_indicator_maps()` to succeed (see
# `tests/app/test_step_run.py`); every test below that needs a REAL build,
# not just a runnable spec, uses this one.
_BUILDABLE_SPEC = default_spec(threshold=0.0)

_TAB_TITLES_IN_ORDER = (
    msg("step.aoi"),
    msg("params.title"),  # task 30: Assessment period/Productivity/Land cover/SOC, merged
    msg("outputs.title"),  # the merged outputs tab: its own key, NOT the ResultsPanel section's
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
    """The three segment-strip cells, in tab order.

    ``_SegmentCell`` builds two ``rv.Html`` divs per tab -- a padded,
    titled wrapper that owns the click and tooltip, and a plain inner bar
    that carries only the visual style -- so a ``title`` attribute is what
    picks the wrapper out from both. ``rv.Html`` is used nowhere else in this
    app's render tree.
    """
    return [w for w in find_widgets(root, v.Html) if w.attributes.get("title")]


def _nav_arrows(root: object) -> list[Any]:
    """The prev/next arrow ``v.Btn`` widgets, in that order.

    ``_NavArrow`` is the only place in this app's whole render tree that
    passes ``icon=True`` to a ``v.Btn`` -- ``TaskButtonComponent`` (used by
    every compute/download button) never does (see
    ``pysepal/solara/components/task_button.py``), and ``map_layers.py``'s
    own ``_RemoveButton`` passes ``outlined=True``, not ``icon=True`` -- so
    that trait alone picks the two arrows out from every other button in the
    tree, real or not-yet-visited.
    """
    return [w for w in find_widgets(root, v.Btn) if w.icon]


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
# `_tab_abbrev` -- each segment chip's up-to-three-character label.
# ---------------------------------------------------------------------------


def test_every_tabs_abbreviation_is_unique_and_at_most_three_characters():
    """The owner's own words: "show inside them a max-three-char reference".
    Directly catches the brief's own named mutation: two chips sharing an
    abbreviation."""
    tabs = workflow_tabs()
    abbrevs = [_tab_abbrev(tab) for tab in tabs]
    assert len(abbrevs) == len(set(abbrevs)), abbrevs
    for abbrev in abbrevs:
        assert 1 <= len(abbrev) <= 3, abbrev


def test_every_locales_abbreviations_are_unique_and_at_most_three_characters(monkeypatch):
    """Walks every shipped locale, not only English -- an abbreviation MAY
    legitimately repeat across locales (the brief's own words), but within
    one locale the three must stay distinct and short.

    Monkeypatches ``current_locale`` where ``BoundCatalog.msg`` looks it up,
    rather than calling the real, global ``pysepal.i18n.set_locale`` -- see
    ``tests/app/test_panel_map_layers.py``'s identical comment for why: that
    would re-render every earlier test's still-mounted render tree with that
    test's own monkeypatches already undone.
    """
    import pysepal.i18n.binding as i18n_binding

    tabs = workflow_tabs()
    for code in messages.available_locales():
        monkeypatch.setattr(i18n_binding, "current_locale", lambda code=code: code)
        abbrevs = [_tab_abbrev(tab) for tab in tabs]
        assert len(abbrevs) == len(set(abbrevs)), (code, abbrevs)
        for abbrev in abbrevs:
            assert 1 <= len(abbrev) <= 3, (code, abbrev)


def test_the_segment_chips_render_their_abbreviation_as_text():
    """The render-level half of the abbreviation tests above: proves the
    label actually reaches the rendered chip, not just ``_tab_abbrev``
    itself. ``cell.children[0]`` is the inner, coloured chip div
    ``_SegmentCell`` builds; its own ``children`` is the one-item
    ``[label]`` list passed to it."""
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    tabs = workflow_tabs()
    expected = [_tab_abbrev(tab) for tab in tabs]

    cells = _wrapper_cells(_workflow_widget(box))
    rendered = [cell.children[0].children[0] for cell in cells]
    assert rendered == expected


def test_the_full_title_tooltip_still_exists_alongside_the_abbreviation():
    """The abbreviation is an ADDITION to the hover tooltip, never a
    replacement for it -- the owner's own words: "show inside them a
    max-three-char reference", not "replace the label with one"."""
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    tabs = workflow_tabs()
    cells = _wrapper_cells(_workflow_widget(box))
    assert [cell.attributes.get("title") for cell in cells] == [tab.title for tab in tabs]


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
# Theme-driven chip colours (task 30). A first attempt used
# `var(--v-divider-base, <literal fallback>)` -- `app/panels/section_header.py`'s
# own technique -- but a real browser check (this task's report) measured
# that CSS variable as never defined in this app's actual Vuetify/ipyvuetify
# setup: `getComputedStyle(...).getPropertyValue("--v-divider-base")` on
# `.v-application` returned `""` in BOTH themes, so the chip's rendered
# background was IDENTICAL in light and dark mode despite the source
# embedding a `var(...)` wrapper -- looks theme-aware, is not. Replaced with
# the route already proven to work in this exact file: picking between two
# literals in PYTHON, off the live `solara.lab.use_dark_effective()` flag,
# the same mechanism `_WorkflowSegments` already uses for `primary`. The
# tests below are the render-level proof that replaced the (wrong) static
# source scan: a literal that never changes with the theme cannot be caught
# by reading the source text alone, only by rendering both themes and
# comparing what actually comes out -- exactly what a static scan cannot see,
# and exactly why the brief asked for a browser check here specifically.
# ---------------------------------------------------------------------------


def test_seg_style_uses_whichever_incomplete_and_locked_fill_it_is_given():
    """``_seg_style`` itself is theme-agnostic -- it renders exactly the
    ``incomplete_fill``/``locked_fill`` its caller hands it, never a value of
    its own. The theme-AWARE half is ``_WorkflowSegments``'s own choice of
    which pair to pass, proven separately below; this pins that
    ``_seg_style`` cannot silently ignore that choice and fall back to a
    fixed value regardless of the argument.
    """
    incomplete_light = _seg_style(
        _TabState.INCOMPLETE, "#000000", "LIGHT-FILL", "LOCKED-FILL", active=False
    )
    incomplete_dark = _seg_style(
        _TabState.INCOMPLETE, "#000000", "DARK-FILL", "LOCKED-FILL", active=False
    )
    assert "LIGHT-FILL" in incomplete_light
    assert "DARK-FILL" in incomplete_dark
    assert incomplete_light != incomplete_dark

    locked_a = _seg_style(_TabState.LOCKED, "#000000", "INCOMPLETE-FILL", "LOCKED-A", active=False)
    locked_b = _seg_style(_TabState.LOCKED, "#000000", "INCOMPLETE-FILL", "LOCKED-B", active=False)
    assert "LOCKED-A" in locked_a
    assert "LOCKED-B" in locked_b
    assert locked_a != locked_b


def test_the_incomplete_fill_is_two_distinct_literals_for_light_and_dark():
    """A floor beneath the render-level test below: the two constants
    ``_WorkflowSegments`` picks between must actually differ, or that test
    would pass by coincidence (both branches choosing the identical value).
    Directly catches the brief's own named mutation in the exact shape it
    was actually found here: a single shared literal used for both themes.
    """
    assert tabs_module._SEG_INCOMPLETE_LIGHT != tabs_module._SEG_INCOMPLETE_DARK
    assert tabs_module._SEG_LOCKED_LIGHT != tabs_module._SEG_LOCKED_DARK


def test_the_incomplete_fill_actually_differs_between_light_and_dark_mode_on_screen():
    """The render-level proof the source-only tests above cannot give: a
    genuinely rendered INCOMPLETE chip's computed style must differ between
    themes, driven through the real component the same way a live theme
    toggle would. This is the exact check that would have caught BOTH dead
    ends this module's own comment describes: a CSS-variable attempt with
    two different-LOOKING source strings that rendered identically in both
    themes, and then a ``solara.lab.use_dark_effective()`` attempt that
    changed nothing when THIS APP'S real theme toggle was clicked in a
    browser, because that flag is a disconnected, process-wide default
    rather than this app's own per-session state. Only reading the ACTUAL
    rendered style after flipping the SAME state the app's real toggle
    drives catches either failure; a plain source read cannot.

    ``get_current_theme_state().dark`` is set directly, not through a real
    frontend click -- ``use_theme_dark()`` is a subscription over exactly
    that trait, and toggling it is what a real click on the app's own theme
    control also does (that control is wired to this same
    ``ThemeState``, threaded into ``MapApp`` by ``page.py``). Restored in a
    ``finally`` block: ``get_current_theme_state()`` is scoped per kernel,
    not per test, so leaving it flipped could leak into a later test's
    render in the same process.
    """
    theme_state = get_current_theme_state()
    original = theme_state.dark
    try:
        theme_state.dark = False
        box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
        assert rc is not None
        light_style = _wrapper_cells(_workflow_widget(box))[_AOI_INDEX].children[0].style_

        theme_state.dark = True
        rc.force_update()
        dark_style = _wrapper_cells(_workflow_widget(box))[_AOI_INDEX].children[0].style_

        assert light_style != dark_style
        assert tabs_module._SEG_INCOMPLETE_LIGHT in light_style
        assert tabs_module._SEG_INCOMPLETE_DARK in dark_style
    finally:
        theme_state.dark = original


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
    in every markdown fragment the PARAMS tab renders, not by position: since
    task 30, Run's own section is FIRST among four (see
    ``app/panels/params.py``), not the tab's only content, so its refusal
    text is no longer reliably the LAST markdown fragment the way it was
    when Run held its own tab.

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
    assert f"<p><strong>{exc_info.value}</strong></p>" in markdown_texts(params_sheet)


# ---------------------------------------------------------------------------
# `WorkflowTabs` itself: renders three tabs, the active index selects which
# `TabItem`'s content is live, and switching tabs does not rebuild the rest.
# ---------------------------------------------------------------------------


def test_workflow_tabs_renders_three_tab_items_and_three_segments():
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    workflow_widget = _workflow_widget(box)

    tab_items = find_widgets(workflow_widget, v.TabItem)
    assert len(tab_items) == 3

    cells = _wrapper_cells(workflow_widget)
    assert len(cells) == 3


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
    cells[_PARAMS_INDEX].fire_event("click", None)
    rc.force_update()

    tabs_items_widget = find_widget(_workflow_widget(box), v.TabsItems)
    assert tabs_items_widget is not None
    assert tabs_items_widget.v_model == _PARAMS_INDEX


def test_a_locked_output_tab_does_not_navigate_on_click():
    """The merged outputs tab is LOCKED while ``outcome.maps`` is ``None``
    (the default, empty spec) -- clicking its segment must be a genuine
    no-op, not merely visually muted. Directly catches "mark every step
    unlocked regardless of state": under that mutation this click WOULD
    navigate.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    cells = _wrapper_cells(_workflow_widget(box))
    cells[_OUTPUTS_INDEX].fire_event("click", None)
    rc.force_update()

    tabs_items_widget = find_widget(_workflow_widget(box), v.TabsItems)
    assert tabs_items_widget is not None
    assert tabs_items_widget.v_model == _AOI_INDEX


def test_both_nav_arrows_carry_a_hover_and_screen_reader_label():
    """An icon-only button has no text, so its `title`/`aria-label` is the
    only affordance it has -- a user hovering sees nothing and a screen
    reader announces nothing without them. The segment cells already solve
    this the same way; the arrows were added later and did not.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    rc.force_update()

    arrows = [
        b
        for b in find_widgets(_workflow_widget(box), v.Btn)
        if b.attributes.get("title") in (msg("tabs.previous"), msg("tabs.next"))
    ]
    assert len(arrows) == 2, "expected exactly one previous and one next arrow"
    for arrow in arrows:
        assert arrow.attributes.get("title"), "arrow has no hover label"
        assert arrow.attributes.get("aria-label") == arrow.attributes["title"]


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
    assert "pointer-events: none" in cells[_OUTPUTS_INDEX].style_
    assert "pointer-events: none" not in cells[_AOI_INDEX].style_


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

    cells = _wrapper_cells(_workflow_widget(box))
    cells[_PARAMS_INDEX].fire_event("click", None)
    rc.force_update()

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

    cells = _wrapper_cells(_workflow_widget(box))
    cells[_PARAMS_INDEX].fire_event("click", None)
    rc.force_update()

    assert sepal_map.dc not in sepal_map.controls

    cells = _wrapper_cells(_workflow_widget(box))
    cells[_AOI_INDEX].fire_event("click", None)
    rc.force_update()

    assert sepal_map.dc in sepal_map.controls


# ---------------------------------------------------------------------------
# `nav_targets` -- pure, ported from spatial-risk's own
# `pipeline_header.nav_targets`. No render context needed: it only reads
# `_tab_state` over a plain `TabDescriptor` list.
# ---------------------------------------------------------------------------

_UNLOCKED_SPEC = RunSpec()  # configuration tabs are never LOCKED, whatever their state


def test_nav_targets_returns_the_adjacent_indices_with_nothing_locked():
    tabs = [
        TabDescriptor("aoi", "AOI", "i", []),
        TabDescriptor("productivity", "Productivity", "i", []),
        TabDescriptor("land_cover", "Land cover", "i", []),
    ]
    assert nav_targets(tabs, 1, _UNLOCKED_SPEC, has_maps=False) == (0, 2)


def test_nav_targets_prev_is_none_at_the_first_tab():
    tabs = [TabDescriptor("aoi", "AOI", "i", []), TabDescriptor("productivity", "P", "i", [])]
    prev_t, _next_t = nav_targets(tabs, 0, _UNLOCKED_SPEC, has_maps=False)
    assert prev_t is None


def test_nav_targets_next_is_none_at_the_last_tab():
    tabs = [TabDescriptor("aoi", "AOI", "i", []), TabDescriptor("productivity", "P", "i", [])]
    _prev_t, next_t = nav_targets(tabs, 1, _UNLOCKED_SPEC, has_maps=False)
    assert next_t is None


def test_nav_targets_next_skips_a_locked_tab_and_finds_nothing_past_it():
    """The shape of this app's own three tabs since task 30's second fold:
    PARAMS, then one LOCKED output tab, nothing after it. "Next" from PARAMS
    must not land on the locked tab -- it must find nothing. Directly catches
    the mutation the brief names: "'next' no longer skips a locked tab" would
    instead return the locked tab's own index here. Uses a generic
    single-step tab (``"soc"``, still a real ``STEP_PREFIXES`` key) rather
    than the real combined PARAMS tuple -- ``nav_targets`` and ``_tab_state``
    treat a 1-tuple and several names identically (see ``_tab_state``'s own
    docstring), so this pins the algorithm generically rather than re-typing
    the real app's own shape.
    """
    tabs = [TabDescriptor("soc", "Soc", "i", []), TabDescriptor(None, "Outputs", "i", [])]
    _prev_t, next_t = nav_targets(tabs, 0, RunSpec(), has_maps=False)
    assert next_t is None


def test_nav_targets_next_reaches_the_output_tab_once_it_unlocks():
    """The positive case: once ``has_maps`` is true the same tab is no
    longer LOCKED, so "next" from SOC finds it."""
    tabs = [TabDescriptor("soc", "Soc", "i", []), TabDescriptor(None, "Outputs", "i", [])]
    _prev_t, next_t = nav_targets(tabs, 0, RunSpec(), has_maps=True)
    assert next_t == 1


def test_nav_targets_skips_a_run_of_more_than_one_locked_tab():
    """``nav_targets`` itself has no notion of "exactly one" locked tab --
    proven generically here with two, even though this app's own three tabs
    never produce more than one (``_tab_state`` locks every ``step=None``
    tab identically, off the same ``has_maps``)."""
    tabs = [
        TabDescriptor("soc", "Soc", "i", []),
        TabDescriptor(None, "Locked 1", "i", []),
        TabDescriptor(None, "Locked 2", "i", []),
    ]
    _prev_t, next_t = nav_targets(tabs, 0, RunSpec(), has_maps=False)
    assert next_t is None


# ---------------------------------------------------------------------------
# The prev/next arrows, rendered -- the repo owner asked for these directly
# ("can we add arrows to the tabs component? so I can easily navigate
# back-and-forth?"); task 21 had deliberately left them out.
# ---------------------------------------------------------------------------


def test_the_arrows_render_exactly_two_icon_buttons():
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    arrows = _nav_arrows(_workflow_widget(box))
    assert len(arrows) == 2


def test_the_prev_arrow_is_disabled_and_the_next_arrow_enabled_on_the_first_tab():
    """Disabled, not hidden or absent -- a disabled control tells the user
    where they are; a vanishing one would make the strip jump. Directly
    catches "arrows stay enabled at the first/last tab": under that mutation
    the prev arrow's ``disabled`` would read ``False`` here.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    prev_arrow, next_arrow = _nav_arrows(_workflow_widget(box))
    assert prev_arrow.disabled is True
    assert next_arrow.disabled is False


def test_the_next_arrow_is_disabled_on_params_while_the_outputs_tab_is_still_locked():
    """The default, empty spec has no build, so the merged outputs tab --
    the only tab after PARAMS, task 30's second fold made it the last
    configuration tab -- is LOCKED. The next arrow must show that, not just
    silently refuse to navigate.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    cells = _wrapper_cells(_workflow_widget(box))
    cells[_PARAMS_INDEX].fire_event("click", None)
    rc.force_update()

    _prev_arrow, next_arrow = _nav_arrows(_workflow_widget(box))
    assert next_arrow.disabled is True


def test_clicking_the_next_arrow_moves_forward_and_the_prev_arrow_moves_back():
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    workflow_widget = _workflow_widget(box)

    tabs_items_widget = find_widget(workflow_widget, v.TabsItems)
    assert tabs_items_widget is not None
    assert tabs_items_widget.v_model == _AOI_INDEX

    _prev_arrow, next_arrow = _nav_arrows(workflow_widget)
    next_arrow.fire_event("click", None)
    rc.force_update()

    tabs_items_widget = find_widget(_workflow_widget(box), v.TabsItems)
    assert tabs_items_widget is not None
    assert tabs_items_widget.v_model == _PARAMS_INDEX

    prev_arrow, _next_arrow = _nav_arrows(_workflow_widget(box))
    prev_arrow.fire_event("click", None)
    rc.force_update()

    tabs_items_widget = find_widget(_workflow_widget(box), v.TabsItems)
    assert tabs_items_widget is not None
    assert tabs_items_widget.v_model == _AOI_INDEX


def test_clicking_the_next_arrow_on_params_does_not_navigate_into_a_locked_outputs_tab():
    """The direct counter-proof for "'next' no longer skips a locked tab":
    under that mutation this click WOULD move ``v_model`` to the outputs tab
    even though it is still LOCKED. Uses ``fire_event``, which bypasses the
    widget's own ``disabled`` prop (a raw Python-level call, not a real
    browser click) -- so this also proves ``_activate_next``'s own
    ``is not None`` recheck, not merely the CSS-level ``disabled`` state the
    test above already covers.
    """
    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None

    cells = _wrapper_cells(_workflow_widget(box))
    cells[_PARAMS_INDEX].fire_event("click", None)
    rc.force_update()

    _prev_arrow, next_arrow = _nav_arrows(_workflow_widget(box))
    next_arrow.fire_event("click", None)
    rc.force_update()

    tabs_items_widget = find_widget(_workflow_widget(box), v.TabsItems)
    assert tabs_items_widget is not None
    assert tabs_items_widget.v_model == _PARAMS_INDEX


def test_clicking_the_next_arrow_on_params_reaches_the_outputs_tab_once_unlocked(monkeypatch):
    """The positive case, through the real render tree: once a build exists
    the outputs tab is reachable, and "next" from PARAMS (the last
    configuration tab since task 30's second fold) lands on it directly
    (there is nothing else after it to skip)."""
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_aoi_step(*, spec: Any = None, map_: Any = None) -> None:
        captured["spec"] = spec

    monkeypatch.setattr(tabs_module, "AoiStep", _spy_aoi_step)
    # `ExportsPanel`'s real `ExportLauncher` starts a task the moment it
    # mounts (see `_noop_exports_panel`'s own docstring) -- a buildable spec
    # makes `OutputsPanel` actually reach it, so it needs the same stand-in
    # every panel-identity test in `test_panel_outputs.py` uses.
    monkeypatch.setattr(outputs_module, "ExportsPanel", _noop_exports_panel)

    box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None
    captured["spec"].value = _BUILDABLE_SPEC

    cells = _wrapper_cells(_workflow_widget(box))
    cells[_PARAMS_INDEX].fire_event("click", None)
    rc.force_update()

    _prev_arrow, next_arrow = _nav_arrows(_workflow_widget(box))
    assert next_arrow.disabled is False
    next_arrow.fire_event("click", None)
    rc.force_update()

    tabs_items_widget = find_widget(_workflow_widget(box), v.TabsItems)
    assert tabs_items_widget is not None
    assert tabs_items_widget.v_model == _OUTPUTS_INDEX
