"""Soil organic carbon configuration.

Owns the SOC period only; every stock-change factor is fixed in the domain.

The clamp is asymmetric on purpose: the legacy bounds only the END year to the
CCI range and passes the start raw. The domain preserves that and reports the
shift as a non-fatal problem. Do not clamp in the UI -- that would hide a
difference the user should see, since the shifted year reaches the results.

The period control itself is ``app/steps/period_override.py``'s
``PeriodOverrideControl``, shared with ``land_cover.py``'s identical
override -- see that module's docstring for why a control collapsed behind a
checkbox, not two always-visible Selects, is what makes ``periods.soc``'s
optionality visible rather than making the app look like it needs a third
required date range.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import solara

from app.message import msg
from app.state import render_problems
from app.steps.period_override import PeriodOverrideControl
from sdg1531.catalog import L4_START
from sdg1531.spec import PeriodOverride, RunSpec

__all__ = ("SocStep",)


@solara.component
def SocStep(spec: solara.Reactive[RunSpec]) -> None:
    solara.Markdown(msg("soc.description"))

    def set_override(new: PeriodOverride) -> None:
        # dataclasses.replace, not .evolve: RunSpec has evolve(), SubPeriods
        # does NOT -- it is a plain frozen dataclass.
        spec.value = spec.value.evolve(periods=replace(spec.value.periods, soc=new))

    # Same range the legacy's PickerLineSOC offered
    # (component/widget/picker_line_soc.py:8): `range(sensor_max_year,
    # L4_start - 1, -1)`. `L4_START` (1982), not a repeated literal:
    # `sdg1531.catalog` already owns this constant; `date.today().year - 1`
    # has no equivalent to import since the domain has no notion of "this
    # year".
    years = list(range(date.today().year - 1, L4_START - 1, -1))

    PeriodOverrideControl(
        override=spec.value.periods.soc,
        overall=spec.value.periods.overall,
        years=years,
        start_label=msg("soc.start"),
        end_label=msg("soc.end"),
        on_change=set_override,
    )

    render_problems("soc", spec.value)
