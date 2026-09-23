"""Build is pure graph construction: no network, no task, no spinner, and --
since Task 20 -- no button. ``build_outcome`` derives it fresh from the spec
on every render; ``RunStep`` only displays whatever outcome it is handed and
never calls ``resolve()`` or ``build_indicator_maps()`` itself, so it cannot
crash on a spec ``resolve()`` refuses.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import ipyvuetify
import pytest
import solara

from app.message import msg
from app.state import problems_for
from app.steps.run import BuildOutcome, RunStep, build, build_outcome
from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.indicator import IndicatorMaps
from sdg1531.spec import Period, PeriodOverride, RunSpec, SensorSelection, SubPeriods
from tests.app.render_helpers import alert_texts, field_messages, find_widgets
from tests.spec_factory import DEFAULT_PERIODS, default_spec

# Every non-overall sub-period pinned to a range that resolves on its own,
# independent of `overall` -- so inverting `overall` below trips only
# `_base_period_problems`, not every other check that falls back to it.
_ISOLATING_OVERRIDE = PeriodOverride(start=2000, end=2015)

# default_spec()'s sensor is MODIS, and MODIS is one of the rungs that
# `_process_modis` requires a resolved float threshold for (validate() does
# not check it -- there is no rule for it in sdg1531.validate -- so an actually
# buildable spec needs it set here, matching tests/engine/test_integration.py).
_BUILDABLE_SPEC = default_spec(threshold=0.0)

_SPEC_WITH_A_RUN_PROBLEM = default_spec(
    periods=SubPeriods(
        overall=Period(start=2020, end=2000),  # inverted: start_not_before_end
        trend=_ISOLATING_OVERRIDE,
        state=_ISOLATING_OVERRIDE,
        performance=_ISOLATING_OVERRIDE,
        land_cover=_ISOLATING_OVERRIDE,
        soc=_ISOLATING_OVERRIDE,
    )
)

# One fatal problem (field="aoi") that belongs to the AOI step, not Run -- the
# case that actually distinguishes `problems_for("run", ...)` from `validate(...)`.
_SPEC_WITH_ANOTHER_STEPS_PROBLEM = default_spec(aoi=None)


class _StubMaps:
    """Stands in for ``IndicatorMaps``: only ``.layers()`` is read by ``RunStep``."""

    def __init__(self, count: int) -> None:
        self._count = count

    def layers(self) -> dict[int, object]:
        return {i: object() for i in range(self._count)}


def test_build_returns_the_maps_and_the_context():
    """Both statistics calls need the context, so build hands it back rather
    than making each panel re-derive the analysis scale."""
    maps, ctx = build(_BUILDABLE_SPEC)
    assert isinstance(maps, IndicatorMaps)
    assert isinstance(ctx, ExecutionContext)
    assert len(maps.layers()) == 7


def test_build_touches_no_network():
    """If this ever needs credentials it has stopped being pure graph
    construction, and the UI's whole no-spinner design is wrong."""
    import socket

    original = socket.socket

    def forbidden(*args, **kwargs):
        raise AssertionError("build() opened a socket; it must stay offline")

    socket.socket = forbidden
    try:
        build(_BUILDABLE_SPEC)
    finally:
        socket.socket = original


# ---------------------------------------------------------------- build_outcome


def test_build_outcome_is_empty_for_a_spec_that_is_not_runnable():
    """An ordinary half-filled form, not an exception -- `RunStep` already
    renders `problems_for` for this state."""
    assert build_outcome(RunSpec()) == BuildOutcome()


def test_build_outcome_is_empty_not_a_crash_for_a_half_filled_overall_period():
    """`resolve()` raises a bare `ValueError` (not `SpecError`) for an overall
    period with a start and no end yet -- the state the Run step's two
    independent year Selects reach naturally (see `app.state.is_runnable`'s
    docstring). `build_outcome` must treat it exactly like any other
    not-yet-runnable spec."""
    spec = default_spec(periods=replace(DEFAULT_PERIODS, overall=Period(start=2000, end=None)))
    assert build_outcome(spec) == BuildOutcome()


def test_build_outcome_returns_the_real_maps_and_context_for_a_buildable_spec():
    """Not a re-implementation of `build()` -- calls the real thing and checks
    `build_outcome` hands back exactly what it returned."""
    expected_maps, expected_ctx = build(_BUILDABLE_SPEC)
    outcome = build_outcome(_BUILDABLE_SPEC)
    assert outcome.error is None
    assert isinstance(outcome.maps, IndicatorMaps)
    assert list(outcome.maps.layers()) == list(expected_maps.layers())
    assert outcome.ctx == expected_ctx


def test_build_outcome_carries_the_refusal_is_runnable_cannot_see():
    """`default_spec()`'s threshold is unset. `validate()` has no rule for it
    (there is no `threshold` field problem), and `resolve()` itself succeeds --
    only `build_indicator_maps()` refuses. `is_runnable` therefore says True,
    so this is exactly the narrower case `build_outcome`'s own `except` exists
    for, not the `is_runnable` branch above. Anchored against a real call to
    `build()`, not a hardcoded guess at the domain's wording."""
    spec = default_spec()  # threshold=None
    with pytest.raises(Exception) as exc_info:
        build(spec)

    outcome = build_outcome(spec)

    assert outcome.maps is None
    assert outcome.ctx is None
    assert outcome.error == str(exc_info.value)


# -------------------------------------------------------------------- RunStep


@pytest.mark.parametrize(
    ("spec", "outcome", "expected_fields", "expected_alerts"),
    [
        (_BUILDABLE_SPEC, BuildOutcome(maps=_StubMaps(7)), [], []),
        (
            _SPEC_WITH_A_RUN_PROBLEM,
            BuildOutcome(),
            [("error", "The assessment start year must be earlier than the end year.")],
            [],
        ),
        (_SPEC_WITH_ANOTHER_STEPS_PROBLEM, BuildOutcome(), [], []),
        (
            default_spec(),
            BuildOutcome(error="spec.threshold must be resolved before the ee graph can be built"),
            [],
            [("error", "spec.threshold must be resolved before the ee graph can be built")],
        ),
    ],
)
def test_the_step_renders_only_its_own_problems(spec, outcome, expected_fields, expected_alerts):
    """Pins what the step actually shows, in four states: built (nothing to
    report), a fatal problem THIS step owns, a fatal problem belonging to
    ANOTHER step (nothing -- the "only" half of this test's name, guarded
    below against being vacuous), and a refusal `is_runnable` cannot see.

    Read off BOTH routes, because a step now has two. `start_not_before_end`
    is emitted on `periods.overall.start`, so it is drawn by the start-year
    Select itself (`field_messages`); the build refusal owns no field at all
    and still goes to the alert (`alert_texts`). Asserting both, always, is
    what stops a message moving from one to the other unnoticed.

    The "Ready: N layers" and "Fix the problems above" lines this used to
    check are deliberately gone -- informational restatements of what the
    Results tab's own enabled state already says, which is exactly the noise
    the repo owner asked to be rid of ("it should only report
    errors/warnings, not useless info"). The layer count is still proven, by
    `test_build_outcome_returns_the_real_maps_and_context_for_a_buildable_spec`.

    `RunStep` never calls `build_outcome` itself, so each case hands it a
    `BuildOutcome` directly rather than relying on what the real function
    would compute for that spec.
    """
    spec_r = solara.reactive(spec)
    box, rc = solara.render(RunStep(spec=spec_r, outcome=outcome), handle_error=False)
    assert rc is not None
    assert field_messages(box) == expected_fields
    assert alert_texts(box) == expected_alerts


def test_another_steps_fatal_problem_really_exists_and_is_still_not_shown_here():
    """The floor under the third case above: `_SPEC_WITH_ANOTHER_STEPS_PROBLEM`
    renders no alert, which proves nothing unless that spec really does carry
    a fatal problem somewhere. It does -- it just belongs to the AOI step."""
    assert any(p.fatal for p in problems_for("aoi", _SPEC_WITH_ANOTHER_STEPS_PROBLEM))
    assert problems_for("run", _SPEC_WITH_ANOTHER_STEPS_PROBLEM) == ()


def test_the_year_step_says_nothing_about_sensor_coverage():
    """The coverage caption is gone, and this is the guard against it coming back.

    It restated on every render, under the year Selects, what
    ``sensor_period_no_overlap`` already says only when it matters and on the
    control that owns it -- that rule names each sensor with its own range and
    is emitted on ``vi_source.names``, so it draws on the Productivity step's
    Sensors field (``test_step_productivity.py``). A period is chosen HERE,
    but it is the SENSORS that fail to cover it.
    """
    spec_r = solara.reactive(_BUILDABLE_SPEC)
    box, rc = solara.render(RunStep(spec=spec_r, outcome=BuildOutcome()), handle_error=False)
    assert rc is not None

    captions = [
        w
        for w in find_widgets(box, ipyvuetify.Html)
        if w.tag == "div" and "caption" in (w.class_ or "")
    ]
    assert captions == []
    assert alert_texts(box) == []
    assert field_messages(box) == []


def test_the_overlap_error_really_does_carry_the_coverage_it_replaced():
    """The floor under the deletion above: dropping the caption is only safe
    while the error that replaces it actually names the ranges. It does --
    asserted here rather than assumed, because a reworded rule that dropped
    the per-sensor years would leave the user with no coverage information
    anywhere.
    """
    spec = default_spec(vi_source=SensorSelection(names=("Landsat 4", "Landsat 5")))
    spec = spec.evolve(periods=replace(spec.periods, overall=Period(2020, 2024)))

    overlap = [
        p for p in problems_for("productivity", spec) if p.code == "sensor_period_no_overlap"
    ]
    assert len(overlap) == 1
    assert "Landsat 4 (1982-1993)" in overlap[0].message
    assert "Landsat 5 (1984-2012)" in overlap[0].message
    assert overlap[0].field == "vi_source.names"


def test_the_year_selects_show_the_current_overall_period_and_the_legacy_range():
    """component/widget/picker_line.py:13-27's YEAR_RANGE, transcribed:
    `range(sensor_max_year, L4_start - 1, -1)` -- descending, no default. Both
    Selects share it; only their label and current value differ."""
    spec = solara.reactive(default_spec())
    box, rc = solara.render(RunStep(spec=spec, outcome=BuildOutcome()), handle_error=False)
    assert rc is not None

    expected_years = list(range(date.today().year - 1, 1981, -1))
    start_select, end_select = find_widgets(box, ipyvuetify.Select)

    assert start_select.label == msg("run.start_year")
    assert start_select.v_model == 2000
    assert start_select.items == expected_years

    assert end_select.label == msg("run.end_year")
    assert end_select.v_model == 2020
    assert end_select.items == expected_years


def test_selecting_a_start_year_updates_only_that_endpoint():
    """A real change on the rendered widget -- not the extracted `evolve()`
    call -- proves the first Select is wired to `overall.start`, leaves
    `overall.end` and every other field untouched, and does not silently
    swap the two Selects' callbacks."""
    spec = solara.reactive(default_spec())
    box, rc = solara.render(RunStep(spec=spec, outcome=BuildOutcome()), handle_error=False)
    assert rc is not None

    start_select, _end_select = find_widgets(box, ipyvuetify.Select)
    before = spec.value

    start_select.v_model = 1995

    assert spec.value.periods.overall == Period(start=1995, end=2020)
    assert spec.value.evolve(periods=before.periods) == before


def test_the_step_survives_a_half_filled_overall_period_between_the_two_selects():
    """The two year Selects are independent widgets: a real user sets one
    before the other, leaving `overall` with a start and no end (or the
    reverse) for at least one render. `RunStep` itself calls neither
    `resolve()` nor `build_outcome` -- only the total `problems_for` -- so
    nothing here can make it crash; this proves the Selects keep updating
    correctly through that half-filled state regardless. (The half-filled
    period's effect on `build_outcome` itself is pinned separately above.)
    """
    spec = solara.reactive(default_spec(periods=SubPeriods()))
    box, rc = solara.render(RunStep(spec=spec, outcome=BuildOutcome()), handle_error=False)
    assert rc is not None

    start_select, end_select = find_widgets(box, ipyvuetify.Select)

    start_select.v_model = 2000  # start only -- the state that used to crash resolve()
    assert spec.value.periods.overall == Period(start=2000, end=None)

    end_select.v_model = 2020
    assert spec.value.periods.overall == Period(start=2000, end=2020)


def test_selecting_an_end_year_updates_only_that_endpoint():
    spec = solara.reactive(default_spec())
    box, rc = solara.render(RunStep(spec=spec, outcome=BuildOutcome()), handle_error=False)
    assert rc is not None

    _start_select, end_select = find_widgets(box, ipyvuetify.Select)
    before = spec.value

    end_select.v_model = 2010

    assert spec.value.periods.overall == Period(start=2000, end=2010)
    assert spec.value.evolve(periods=before.periods) == before
