"""The SOC period, and the asymmetric clamp the domain warns about."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import ipyvuetify
import pytest
import solara

from app.message import msg
from app.state import problems_for
from app.steps.soc import SocStep
from sdg1531.spec import PeriodOverride
from tests.app.render_helpers import find_widgets, markdown_texts
from tests.spec_factory import default_spec

# Same range the legacy's PickerLineSOC offers (component/widget/picker_line_soc.py:8):
# `range(sensor_max_year, L4_start - 1, -1)`, i.e. last year down to 1982.
_YEARS = list(range(date.today().year - 1, 1981, -1))


def _selects(box: object) -> tuple[object, object]:
    """The step's two ``ipyvuetify.Select`` widgets, in source order: start, end."""
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


def test_the_widgets_show_no_default_when_the_override_is_unset():
    """``periods.soc`` is an OPTIONAL override -- ``default_spec()`` leaves it
    ``PeriodOverride(None, None)``, and ``resolve()`` derives the SOC window
    from ``periods.overall`` instead. A control that invented a default year
    here would name a year the run does not use; the legacy's own
    ``PickerLineSOC`` (picker_line_soc.py:16-26) leaves both Selects
    ``v_model=None`` for exactly this reason -- pinned against the real
    render tree, not just the spec, so a control that fabricates a default
    only in the widget (leaving the spec alone) cannot pass this by
    coincidence."""
    spec = solara.reactive(default_spec())
    assert spec.value.periods.soc == PeriodOverride(None, None)

    box, rc = solara.render(SocStep(spec=spec), handle_error=False)
    assert rc is not None

    start, end = _selects(box)
    assert start.label == msg("soc.start")
    assert start.items == _YEARS
    assert start.v_model is None

    assert end.label == msg("soc.end")
    assert end.items == _YEARS
    assert end.v_model is None


def test_the_widgets_show_the_current_override_when_set():
    spec = solara.reactive(
        default_spec(periods=replace(default_spec().periods, soc=PeriodOverride(1995, 2010)))
    )
    box, rc = solara.render(SocStep(spec=spec), handle_error=False)
    assert rc is not None

    start, end = _selects(box)
    assert start.v_model == 1995
    assert end.v_model == 2010


def test_changing_the_start_year_updates_only_that_field():
    spec = solara.reactive(default_spec())
    box, rc = solara.render(SocStep(spec=spec), handle_error=False)
    assert rc is not None
    start, _end = _selects(box)
    before = spec.value

    start.v_model = 1995

    assert spec.value.periods.soc.start == 1995
    reverted = spec.value.evolve(
        periods=replace(
            spec.value.periods,
            soc=replace(spec.value.periods.soc, start=before.periods.soc.start),
        )
    )
    assert reverted == before


def test_changing_the_end_year_updates_only_that_field():
    spec = solara.reactive(default_spec())
    box, rc = solara.render(SocStep(spec=spec), handle_error=False)
    assert rc is not None
    _start, end = _selects(box)
    before = spec.value

    end.v_model = 2010

    assert spec.value.periods.soc.end == 2010
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


def test_every_label_and_the_description_route_through_msg(monkeypatch):
    """Every other assertion in this file compares a rendered label against
    ``msg()``'s own English return value, so a hardcoded English literal in
    place of a ``msg()`` call would satisfy all of them by coincidence.
    Substituting a distinguishing stand-in for ``msg`` instead proves each
    rendered string is really that call's OUTPUT, not a literal that happens
    to match it."""

    def _fake_msg(key: str, **_: object) -> str:
        return f"<{key}>"

    monkeypatch.setattr("app.steps.soc.msg", _fake_msg)

    spec = solara.reactive(default_spec())
    box, rc = solara.render(SocStep(spec=spec), handle_error=False)
    assert rc is not None

    assert markdown_texts(box)[0] == "<p><soc.description></p>"

    start, end = _selects(box)
    assert start.label == "<soc.start>"
    assert end.label == "<soc.end>"


@pytest.mark.parametrize(
    ("spec", "expected_extra"),
    [
        (default_spec(), []),
        (
            default_spec(periods=replace(default_spec().periods, soc=PeriodOverride(1980, 2015))),
            [
                "<p>The soil organic carbon period starts before the CCI land "
                "cover record (1992); the years before it contribute no land "
                "cover transition.</p>"
            ],
        ),
        (
            # Entirely after the CCI record (soil_organic_carbon.py:161 -- a
            # negative band index): fatal, unlike the warning case above.
            default_spec(periods=replace(default_spec().periods, soc=PeriodOverride(2023, 2024))),
            [
                "<p><strong>The soil organic carbon period lies entirely after "
                "the end of the CCI land cover record (2022), so it collapses "
                "to nothing.</strong></p>"
            ],
        ),
        (
            # A fatal problem belonging to ANOTHER step (missing AOI) -- the
            # case that actually distinguishes `problems_for("soc", ...)`
            # from `validate(...)`.
            default_spec(aoi=None),
            [],
        ),
    ],
)
def test_the_step_renders_only_its_own_text(spec, expected_extra):
    spec_r = solara.reactive(spec)
    box, rc = solara.render(SocStep(spec=spec_r), handle_error=False)
    assert rc is not None
    assert markdown_texts(box) == [
        "<p>The period soil organic carbon change is measured over.</p>",
        *expected_extra,
    ]
