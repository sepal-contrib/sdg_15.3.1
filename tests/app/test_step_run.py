"""Build is pure graph construction: no network, no task, no spinner.

The step is the LAST trigger before a run leaves pure Python: it shows only
the whole-spec and overall-period problems it owns, disables Build while any
fatal problem stands anywhere in the spec, and on a real click either fills
``maps``/``ctx`` and reports success, or -- for a spec ``resolve()`` itself
refuses -- notifies the error and leaves both reactives untouched.
"""

from __future__ import annotations

from datetime import date

import ipyvuetify
import pytest
import solara

from app.message import msg
from app.steps.run import RunStep, build
from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.indicator import IndicatorMaps
from sdg1531.spec import Period, PeriodOverride, RunSpec, SubPeriods
from tests.app.render_helpers import find_widget, find_widgets, markdown_texts
from tests.spec_factory import default_spec

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
# case that actually distinguishes `problems_for("run", ...)` from `validate(...)`,
# and `is_runnable` from `not problems_for("run", ...)`. Both mutations pass
# every OTHER parametrization in this file, since those only ever use a spec
# whose problems Run owns or a spec with none at all.
_SPEC_WITH_ANOTHER_STEPS_PROBLEM = default_spec(aoi=None)


class _FakeNotifier:
    """A spy standing in for ``use_notifications()``'s real bus-backed notifier."""

    def __init__(self) -> None:
        self.successes: list[str] = []
        self.errors: list[str] = []

    def success(self, message: str) -> None:
        self.successes.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)


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


@pytest.mark.parametrize(
    ("spec", "expected_extra"),
    [
        (default_spec(), []),
        (
            _SPEC_WITH_A_RUN_PROBLEM,
            [
                "<p><strong>The assessment start year must be earlier than the "
                "end year.</strong></p>",
                "<p>Fix the problems above before building.</p>",
            ],
        ),
        (
            _SPEC_WITH_ANOTHER_STEPS_PROBLEM,
            ["<p>Fix the problems above before building.</p>"],
        ),
    ],
)
def test_the_step_renders_only_its_own_text(spec, expected_extra):
    """Pins what the step actually shows, in three states: a runnable spec
    shows only the description; a spec with a fatal problem THIS step owns
    shows that problem's text and the blocked notice; and a spec whose only
    fatal problem belongs to ANOTHER step (missing AOI) shows the blocked
    notice but NOT that other step's problem text -- the "only" half of this
    test's name, which nothing else here exercises."""
    spec_r = solara.reactive(spec)
    maps = solara.reactive(None)
    ctx = solara.reactive(None)
    box, rc = solara.render(RunStep(spec=spec_r, maps=maps, ctx=ctx), handle_error=False)
    assert rc is not None
    assert markdown_texts(box) == [
        "<p>Build the indicator from the configuration above.</p>",
        *expected_extra,
    ]


def test_the_year_selects_show_the_current_overall_period_and_the_legacy_range():
    """component/widget/picker_line.py:13-27's YEAR_RANGE, transcribed:
    `range(sensor_max_year, L4_start - 1, -1)` -- descending, no default. Both
    Selects share it; only their label and current value differ."""
    spec = solara.reactive(default_spec())
    maps = solara.reactive(None)
    ctx = solara.reactive(None)
    box, rc = solara.render(RunStep(spec=spec, maps=maps, ctx=ctx), handle_error=False)
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
    maps = solara.reactive(None)
    ctx = solara.reactive(None)
    box, rc = solara.render(RunStep(spec=spec, maps=maps, ctx=ctx), handle_error=False)
    assert rc is not None

    start_select, _end_select = find_widgets(box, ipyvuetify.Select)
    before = spec.value

    start_select.v_model = 1995

    assert spec.value.periods.overall == Period(start=1995, end=2020)
    assert spec.value.evolve(periods=before.periods) == before


def test_the_step_survives_a_half_filled_overall_period_between_the_two_selects():
    """The two year Selects are independent widgets: a real user sets one
    before the other, leaving `overall` with a start and no end (or the
    reverse) for at least one render. `resolve()` raises a bare `ValueError`
    for that state, not `SpecError` (see `app.state.is_runnable`'s
    docstring) -- this proves the step does not crash then, and correctly
    keeps Build disabled until both endpoints are set.
    """
    spec = solara.reactive(default_spec(periods=SubPeriods()))
    maps = solara.reactive(None)
    ctx = solara.reactive(None)
    box, rc = solara.render(RunStep(spec=spec, maps=maps, ctx=ctx), handle_error=False)
    assert rc is not None

    start_select, end_select = find_widgets(box, ipyvuetify.Select)
    button = find_widget(box, ipyvuetify.Btn)
    assert button.disabled is True  # neither endpoint set yet

    start_select.v_model = 2000  # start only -- the state that used to crash

    assert spec.value.periods.overall == Period(start=2000, end=None)
    assert button.disabled is True  # still not runnable, and no crash

    end_select.v_model = 2020

    assert spec.value.periods.overall == Period(start=2000, end=2020)
    assert button.disabled is False


def test_selecting_an_end_year_updates_only_that_endpoint():
    spec = solara.reactive(default_spec())
    maps = solara.reactive(None)
    ctx = solara.reactive(None)
    box, rc = solara.render(RunStep(spec=spec, maps=maps, ctx=ctx), handle_error=False)
    assert rc is not None

    _start_select, end_select = find_widgets(box, ipyvuetify.Select)
    before = spec.value

    end_select.v_model = 2010

    assert spec.value.periods.overall == Period(start=2000, end=2010)
    assert spec.value.evolve(periods=before.periods) == before


@pytest.mark.parametrize(
    ("spec", "expected_disabled"),
    [
        (default_spec(), False),
        (_SPEC_WITH_A_RUN_PROBLEM, True),
        (_SPEC_WITH_ANOTHER_STEPS_PROBLEM, True),
    ],
)
def test_the_build_button_is_disabled_exactly_when_not_runnable(spec, expected_disabled):
    """``is_runnable`` -- not a length check on ``problems_for("run", ...)``
    -- gates the button, so a problem some OTHER step owns still disables it
    here (the third case: missing AOI, a problem Run's own loop never shows)."""
    spec_r = solara.reactive(spec)
    maps = solara.reactive(None)
    ctx = solara.reactive(None)
    box, rc = solara.render(RunStep(spec=spec_r, maps=maps, ctx=ctx), handle_error=False)
    assert rc is not None

    button = find_widget(box, ipyvuetify.Btn)
    assert button is not None
    assert button.disabled is expected_disabled
    assert button.color == "primary"
    assert button.children == [msg("run.build")]


def test_clicking_build_fills_the_reactives_and_reports_success(monkeypatch):
    """A real click on the rendered widget -- not a captured spy -- proves
    the button is wired to ``build()``, that BOTH reactives it hands back are
    written, and that the toast and the context are the real ones.

    The expected count (7) and scale (250, MODIS MOD13Q1's -- see
    ``sdg1531.catalog.SENSORS``) are literals computed independently of
    ``maps``/``ctx``, not read back off the very objects the click just
    wrote: a build that quietly handed back the wrong context (a mismatched
    scale for the zonal stats and export region -- see ``build()``'s
    docstring) would still pass an ``isinstance``-only check.
    """
    fake = _FakeNotifier()
    monkeypatch.setattr("app.steps.run.use_notifications", lambda: fake)

    spec = solara.reactive(_BUILDABLE_SPEC)
    maps = solara.reactive(None)
    ctx = solara.reactive(None)
    box, rc = solara.render(RunStep(spec=spec, maps=maps, ctx=ctx), handle_error=False)
    assert rc is not None

    button = find_widget(box, ipyvuetify.Btn)
    assert button is not None
    assert button.disabled is False

    button.click()

    assert isinstance(maps.value, IndicatorMaps)
    assert isinstance(ctx.value, ExecutionContext)
    assert ctx.value.analysis_scale == 250
    assert fake.successes == [msg("run.built", count=7)]
    assert fake.errors == []


def test_clicking_build_on_a_spec_resolve_refuses_notifies_the_error_and_writes_nothing(
    monkeypatch,
):
    """``build()`` can still raise ``SpecError`` for a spec ``validate()`` never
    flagged (e.g. no vi_source at all) -- the tuple assignment must not run
    half-way, and the error the user sees must be the domain's own message."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.steps.run.use_notifications", lambda: fake)

    spec = solara.reactive(RunSpec())
    maps = solara.reactive(None)
    ctx = solara.reactive(None)
    box, rc = solara.render(RunStep(spec=spec, maps=maps, ctx=ctx), handle_error=False)
    assert rc is not None

    button = find_widget(box, ipyvuetify.Btn)
    assert button is not None

    button.click()  # a programmatic click bypasses the `disabled` UI hint

    assert maps.value is None
    assert ctx.value is None
    assert fake.errors == ["vi_source is not set"]
    assert fake.successes == []
