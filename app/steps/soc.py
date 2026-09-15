"""Soil organic carbon configuration.

Owns the SOC period only; every stock-change factor is fixed in the domain.

The clamp is asymmetric on purpose: the legacy bounds only the END year to the
CCI range and passes the start raw. The domain preserves that and reports the
shift as a non-fatal problem. Do not clamp in the UI -- that would hide a
difference the user should see, since the shifted year reaches the results.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import solara

from app.message import msg
from app.state import problems_for
from sdg1531.catalog import L4_START
from sdg1531.spec import PeriodOverride, RunSpec

__all__ = ("SocStep",)


@solara.component
def SocStep(spec: solara.Reactive[RunSpec]) -> None:
    solara.Markdown(msg("soc.description"))

    current = spec.value.periods.soc

    def set_bounds(start: int | None, end: int | None) -> None:
        # dataclasses.replace, not .evolve: RunSpec has evolve(), SubPeriods
        # does NOT -- it is a plain frozen dataclass.
        spec.value = spec.value.evolve(
            periods=replace(spec.value.periods, soc=PeriodOverride(start, end))
        )

    # Year Selects over the same range as the overall period, NOT InputInt, and
    # with NO invented default -- both transcribed from the legacy's PickerLineSOC
    # (component/widget/picker_line_soc.py:8,16-26): `items=YEAR_RANGE`,
    # `v_model=None`.
    #
    # `value=current.start or 2000` would be actively misleading. `periods.soc` is
    # an OPTIONAL override: leaving it unset is correct, and `resolve()` then
    # derives the SOC window from `periods.overall`. I measured it — with the user's
    # overall period set to 2001-2015 the run uses soc_period 2001-2015, so a
    # control showing "2000" would state a start year the run does not use. An
    # empty control says "not overridden", which is the truth.
    #
    # `L4_START` (1982), not a repeated literal: `sdg1531.catalog` already
    # owns this constant (it is the legacy's own `L4_start`, per
    # picker_line_soc.py's `YEAR_RANGE`); `date.today().year - 1` has no
    # equivalent to import since the domain has no notion of "this year".
    years = list(range(date.today().year - 1, L4_START - 1, -1))

    solara.Select(
        label=msg("soc.start"),
        value=current.start,
        values=years,
        on_value=lambda v: set_bounds(v, spec.value.periods.soc.end),
    )
    solara.Select(
        label=msg("soc.end"),
        value=current.end,
        values=years,
        on_value=lambda v: set_bounds(spec.value.periods.soc.start, v),
    )

    for problem in problems_for("soc", spec.value):
        solara.Markdown(f"**{problem.message}**" if problem.fatal else problem.message)
