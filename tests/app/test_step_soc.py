"""The SOC period, and the asymmetric clamp the domain warns about."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import ipyvuetify
import pytest
import solara

from app.message import msg
from app.state import is_runnable, problems_for
from app.steps.soc import SocStep
from sdg1531.catalog import L4_START
from sdg1531.resolve import resolve
from sdg1531.spec import Period, PeriodOverride
from tests.app.render_helpers import alert_texts, find_widgets, markdown_texts
from tests.spec_factory import DEFAULT_PERIODS, default_spec

# Same range the legacy's PickerLineSOC offers (component/widget/picker_line_soc.py:8):
# `range(sensor_max_year, L4_start - 1, -1)`, i.e. last year down to 1982. `L4_START`
# comes from `sdg1531.catalog` -- the same constant `app/steps/soc.py` imports --
# rather than a second hardcoded `1981`, so the two cannot drift apart.
_YEARS = list(range(date.today().year - 1, L4_START - 1, -1))

# `DEFAULT_PERIODS.overall` (`tests/spec_factory.py`) is what an unset SOC
# override inherits from -- the text every "collapsed" case below expects to
# see stated plainly, matching `PeriodOverrideControl`'s own catalogue key.
# Wrapped in `<p>...</p>` to match `markdown_texts`'s own rendered-HTML shape
# (see its docstring).
_INHERITED_MSG = msg(
    "period_override.inherited",
    start=DEFAULT_PERIODS.overall.start,
    end=DEFAULT_PERIODS.overall.end,
)
_INHERITED_TEXT = f"<p>{_INHERITED_MSG}</p>"


def _checkbox(box: object) -> object:
    """The step's one override-toggle checkbox."""
    boxes = find_widgets(box, ipyvuetify.Checkbox)
    assert len(boxes) == 1
    return boxes[0]


def _selects(box: object) -> tuple[object, object]:
    """The step's two ``ipyvuetify.Select`` widgets, in source order: start,
    end -- present only once the override checkbox is enabled."""
    widgets = find_widgets(box, ipyvuetify.Select)
    assert len(widgets) == 2
    return tuple(widgets)  # type: ignore[return-value]


def test_the_step_renders():
    spec = solara.reactive(default_spec())
    _box, rc = solara.render(SocStep(spec=spec), handle_error=False)
    assert rc is not None


def test_a_soc_start_before_the_cci_range_warns_rather_than_blocks():
    """The legacy clamps only the end year. The domain preserves that and
    reports the shift; the UI must surface it, not hide it by clamping."""
    spec = default_spec().evolve(
        periods=replace(default_spec().periods, soc=PeriodOverride(1980, 2015))
    )
    problems = problems_for("soc", spec)
    warning = [p for p in problems if p.code == "soc_start_before_cci"]
    assert warning, [p.code for p in problems]
    assert warning[0].fatal is False


def test_the_override_checkbox_starts_unchecked_and_shows_the_inherited_window():
    """``periods.soc`` is an OPTIONAL override -- ``default_spec()`` leaves it
    ``PeriodOverride(None, None)``. The three controls (Run's overall period,
    this one, land cover's) are one requirement and two optional narrowings,
    not three equal date ranges: an unset override must show the window it
    ACTUALLY uses, plainly, rather than two empty year Selects that look like
    a required third date range."""
    spec = solara.reactive(default_spec())
    assert spec.value.periods.soc == PeriodOverride(None, None)

    box, rc = solara.render(SocStep(spec=spec), handle_error=False)
    assert rc is not None

    checkbox = _checkbox(box)
    assert checkbox.v_model is False
    assert find_widgets(box, ipyvuetify.Select) == []
    assert _INHERITED_TEXT in markdown_texts(box)


def test_the_inherited_text_matches_resolves_own_derived_period():
    """Directly catches "the inherited window shown in the UI stops matching
    resolve()'s derived period": the plainly-stated window must be the SAME
    period ``resolve()`` actually derives for a run, not a
    coincidentally-matching literal."""
    spec = default_spec()
    box, rc = solara.render(SocStep(spec=solara.reactive(spec)), handle_error=False)
    assert rc is not None

    derived = resolve(spec).soc_period
    assert msg("period_override.inherited", start=derived.start, end=derived.end) == _INHERITED_MSG
    assert _INHERITED_TEXT in markdown_texts(box)


def test_the_checkbox_starts_checked_and_the_selects_show_the_override_when_one_is_set():
    """A spec loaded with a real override must not hide that fact behind an
    unchecked box the user has no reason to tick -- pinned against the real
    render tree, not just the spec, so a control that fabricates a default
    only in the widget (leaving the spec alone) cannot pass this by
    coincidence."""
    spec = solara.reactive(
        default_spec(periods=replace(default_spec().periods, soc=PeriodOverride(1995, 2010)))
    )
    box, rc = solara.render(SocStep(spec=spec), handle_error=False)
    assert rc is not None

    assert _checkbox(box).v_model is True

    start, end = _selects(box)
    assert start.label == msg("soc.start")
    assert start.items == _YEARS
    assert start.v_model == 1995
    assert end.label == msg("soc.end")
    assert end.items == _YEARS
    assert end.v_model == 2010


def test_changing_the_start_year_updates_only_that_field():
    spec = solara.reactive(
        default_spec(periods=replace(default_spec().periods, soc=PeriodOverride(1995, 2010)))
    )
    box, rc = solara.render(SocStep(spec=spec), handle_error=False)
    assert rc is not None
    start, _end = _selects(box)
    before = spec.value

    start.v_model = 2000

    assert spec.value.periods.soc.start == 2000
    reverted = spec.value.evolve(
        periods=replace(
            spec.value.periods,
            soc=replace(spec.value.periods.soc, start=before.periods.soc.start),
        )
    )
    assert reverted == before


def test_changing_the_end_year_updates_only_that_field():
    spec = solara.reactive(
        default_spec(periods=replace(default_spec().periods, soc=PeriodOverride(1995, 2010)))
    )
    box, rc = solara.render(SocStep(spec=spec), handle_error=False)
    assert rc is not None
    _start, end = _selects(box)
    before = spec.value

    end.v_model = 2015

    assert spec.value.periods.soc.end == 2015
    reverted = spec.value.evolve(
        periods=replace(
            spec.value.periods,
            soc=replace(spec.value.periods.soc, end=before.periods.soc.end),
        )
    )
    assert reverted == before


def test_changing_one_bound_leaves_the_other_alone():
    """The handler rebuilds the whole ``PeriodOverride`` from scratch on every
    call (``PeriodOverride(start, end)``, not a partial ``replace``) -- so a
    version that forgot to read the sibling bound back out of the spec first
    would silently reset it to ``None`` instead of preserving it."""
    spec = solara.reactive(
        default_spec(periods=replace(default_spec().periods, soc=PeriodOverride(1995, 2010)))
    )
    box, rc = solara.render(SocStep(spec=spec), handle_error=False)
    assert rc is not None
    start, _end = _selects(box)

    start.v_model = 2000

    assert spec.value.periods.soc == PeriodOverride(2000, 2010)


def test_turning_the_override_on_writes_nothing_until_a_year_is_picked():
    """Ticking the checkbox reveals the Selects but must not itself invent a
    default year -- only an actual pick writes to the spec, the same "no
    invented default" rule the Selects themselves always followed."""
    spec = solara.reactive(default_spec())
    box, rc = solara.render(SocStep(spec=spec), handle_error=False)
    assert rc is not None
    before = spec.value

    _checkbox(box).v_model = True

    assert spec.value == before  # unchanged: no year picked yet
    start, end = _selects(box)
    assert start.v_model is None
    assert end.v_model is None


def test_turning_the_override_off_clears_it_rather_than_leaving_stale_years():
    """The brief's own named trap, directly: switching the override back off
    must CLEAR it, or the spec keeps computing years the UI no longer shows
    -- the failure class this project has spent the most effort eliminating.
    Directly catches "toggling an override off leaves the old years in the
    spec"."""
    spec = solara.reactive(
        default_spec(periods=replace(default_spec().periods, soc=PeriodOverride(1995, 2010)))
    )
    box, rc = solara.render(SocStep(spec=spec), handle_error=False)
    assert rc is not None
    assert _checkbox(box).v_model is True

    _checkbox(box).v_model = False

    assert spec.value.periods.soc == PeriodOverride(None, None)
    assert find_widgets(box, ipyvuetify.Select) == []
    assert _INHERITED_TEXT in markdown_texts(box)


def test_a_half_filled_override_leaves_the_spec_runnable():
    """Setting only ONE bound is a state the two independent year Selects
    reach naturally, one click before the other -- and it must stay usable
    while it lasts. Unlike ``periods.overall`` (whose own half-filled state
    reaches ``resolve()``'s empty ``max()`` and raises a bare ``ValueError``,
    per ``app.state.is_runnable``'s docstring), ``PeriodOverride.resolve()``
    fills a missing bound from ``periods.overall`` itself, so a half-filled
    OVERRIDE never reaches that gap. Pinned directly against ``is_runnable``
    and ``resolve()``'s own output, through the real widget, not just the
    leaf field -- a regression that reintroduced the `overall`-style gap for
    overrides too would fail here even though the leaf value is still
    correct."""
    spec = solara.reactive(default_spec())
    assert is_runnable(spec.value)  # fully configured before this step touches it

    box, rc = solara.render(SocStep(spec=spec), handle_error=False)
    assert rc is not None
    _checkbox(box).v_model = True
    start, _end = _selects(box)

    start.v_model = 1995

    assert spec.value.periods.soc == PeriodOverride(1995, None)
    assert is_runnable(spec.value)
    assert resolve(spec.value).soc_period == Period(1995, spec.value.periods.overall.end)


def test_every_label_and_the_description_route_through_msg(monkeypatch):
    """Every other assertion in this file compares a rendered label against
    ``msg()``'s own English return value, so a hardcoded English literal in
    place of a ``msg()`` call would satisfy all of them by coincidence.
    Substituting a distinguishing stand-in for ``msg`` instead proves each
    rendered string is really that call's OUTPUT, not a literal that happens
    to match it. Patches ``msg`` in BOTH ``app.steps.soc`` (the two Select
    labels) and ``app.steps.period_override`` (the shared control's own
    checkbox label), since the two modules each import their own bound
    ``msg``.

    The description itself is no longer rendered by this step (task 30: it
    rides on ``ParamsPanel``'s own ``SectionHeader`` now -- see
    ``app/panels/params.py``); ``tests/app/test_panel_params.py``'s
    ``test_each_sections_own_description_travels_with_it`` pins it to
    ``msg("soc.description")`` instead.
    """

    def _fake_msg(key: str, **_: object) -> str:
        return f"<{key}>"

    monkeypatch.setattr("app.steps.soc.msg", _fake_msg)
    monkeypatch.setattr("app.steps.period_override.msg", _fake_msg)

    spec = solara.reactive(
        default_spec(periods=replace(default_spec().periods, soc=PeriodOverride(1995, 2010)))
    )
    box, rc = solara.render(SocStep(spec=spec), handle_error=False)
    assert rc is not None

    assert _checkbox(box).label == "<period_override.toggle>"

    start, end = _selects(box)
    assert start.label == "<soc.start>"
    assert end.label == "<soc.end>"


@pytest.mark.parametrize(
    ("spec", "expected_markdown", "expected_alerts"),
    [
        (default_spec(), [_INHERITED_TEXT], []),
        (
            # 1985, not the 1980 `test_a_soc_start_before_the_cci_range_warns_
            # rather_than_blocks` above uses (that value is the brief's own,
            # transcribed verbatim): 1985 is a year the control's own `_YEARS`
            # actually offers, so this case is reachable through the rendered
            # widget, not just through `problems_for` directly. The override
            # is SET here, so the checkbox starts checked and shows no
            # inherited text.
            default_spec(periods=replace(default_spec().periods, soc=PeriodOverride(1985, 2015))),
            [],
            [
                (
                    "warning",
                    "The soil organic carbon period starts before the CCI land "
                    "cover record (1992); the years before it contribute no land "
                    "cover transition.",
                )
            ],
        ),
        (
            # Entirely after the CCI record (soil_organic_carbon.py:161 -- a
            # negative band index): fatal, unlike the warning case above.
            default_spec(periods=replace(default_spec().periods, soc=PeriodOverride(2023, 2024))),
            [],
            [
                (
                    "error",
                    "The soil organic carbon period lies entirely after the end "
                    "of the CCI land cover record (2022), so it collapses to "
                    "nothing.",
                )
            ],
        ),
        (
            # A fatal problem belonging to ANOTHER step (missing AOI) -- the
            # case that actually distinguishes `problems_for("soc", ...)`
            # from `validate(...)`. The override is still unset here, so the
            # inherited text still shows.
            default_spec(aoi=None),
            [_INHERITED_TEXT],
            [],
        ),
    ],
)
def test_the_step_renders_only_its_own_text(spec, expected_markdown, expected_alerts):
    """The description no longer leads this list (task 30: it rides on
    ``ParamsPanel``'s own ``SectionHeader`` now -- see
    ``app/panels/params.py``).

    Problems and prose are now read separately: the inherited-period line is
    still ordinary markdown, while validation messages go through
    ``app/panels/problems.py``'s ``rv.Alert``. Reading the alert's own ``type``
    is also what pins fatal-vs-not, which the old bold-or-not markdown could
    only express as a string prefix -- so the warning case above is now
    asserted to be a warning, not merely to be unbolded.
    """
    spec_r = solara.reactive(spec)
    box, rc = solara.render(SocStep(spec=spec_r), handle_error=False)
    assert rc is not None
    assert markdown_texts(box) == expected_markdown
    assert alert_texts(box) == expected_alerts
