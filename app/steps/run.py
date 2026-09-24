"""The Run step: the overall period, and what the current spec derives.

Deriving the maps and the context is pure ``ee`` graph construction -- no
network, no task, no spinner (pinned by
``test_step_run.py::test_build_touches_no_network``). ``build_outcome`` runs
on every render, wrapped in ``use_memo`` by ``app/page.py``, rather than
behind a button: a button guarding a 19ms pure function guards nothing, and
storing the result behind a reactive is exactly what let a stale build
survive a later spec edit.

``build_outcome`` is total -- it never raises, for any spec. ``is_runnable``
is asked first so an ordinary half-filled form produces no error, and the
refusal ``build()`` alone can see is caught and carried as a problem.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

import solara

from app.message import msg
from app.panels.fields import ProblemRouter, SelectField
from app.panels.problems import ProblemsList
from app.state import is_runnable, problems_for
from sdg1531.catalog import L4_START
from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.indicator import IndicatorMaps, build_indicator_maps
from sdg1531.resolve import resolve
from sdg1531.spec import Period, RunSpec
from sdg1531.validate import Problem

__all__ = ("BuildOutcome", "RunStep", "build", "build_outcome")


def build(spec: RunSpec) -> tuple[IndicatorMaps, ExecutionContext]:
    """Resolve the spec and construct every graph. Pure; raises on refusal.

    Returns the context as well as the maps. Both statistics calls need it --
    ``fetch_areas_by_land_cover`` takes it directly, and ``fetch_zonal_areas``
    needs ``ctx.feature_collection`` as its zones, which is what the legacy
    reduced over (``compute_zonal_analysis`` uses the AOI's own features).
    Rebuilding it in each panel would duplicate the scale derivation.
    """
    resolved = resolve(spec)
    ctx = ExecutionContext.from_aoi_spec(spec.aoi, resolved.analysis_scale)
    return build_indicator_maps(resolved, ctx), ctx


@dataclass(frozen=True, slots=True)
class BuildOutcome:
    """What the spec currently derives: maps and context, or the reason it does not.

    Carries the error text rather than raising, because this is computed during
    render now, not inside a button handler that could catch and toast. A spec
    the user is halfway through editing is the normal case, not an exception.
    """

    maps: IndicatorMaps | None = None
    ctx: ExecutionContext | None = None
    error: str | None = None


def build_outcome(spec: RunSpec) -> BuildOutcome:
    """Derive the whole run from the spec. Total: never raises, for any spec.

    ``is_runnable`` is asked first so an ordinary half-filled form produces a
    plain empty outcome rather than an error message the user cannot act on --
    the Run step already renders ``problems_for("run", ...)`` and
    ``msg("run.blocked")`` for that state. The ``except`` below is for the
    narrower case ``is_runnable`` cannot see: ``resolve()`` succeeds and
    ``build_indicator_maps()`` still refuses. That path used to surface as an
    error toast from the Build button's handler; it must stay visible.
    """
    if not is_runnable(spec):
        return BuildOutcome()
    try:
        maps, ctx = build(spec)
    except Exception as error:  # see `is_runnable`'s own catch-all
        return BuildOutcome(error=str(error))
    return BuildOutcome(maps=maps, ctx=ctx)


@solara.component
def RunStep(spec: solara.Reactive[RunSpec], outcome: BuildOutcome) -> None:
    # The title is the PARAMS section header's (`app/panels/params.py`);
    # this step renders only its own controls.

    # The overall period. Transcribed from the legacy's PickerLine
    # (component/widget/picker_line.py:13-27): two year Selects over
    # `range(sensor_max_year, L4_start - 1, -1)` -- descending, 1982 up to last
    # year -- with NO default, because the legacy made the user choose.
    #
    # Not decoration. `RunSpec().periods.overall` is `Period(None, None)`;
    # `resolve()` derives every other sub-period from it and raises
    # `SpecError: soc.start must be set before a run can be resolved` when it is
    # unset, while `validate()` has no rule for it. Without this control a user
    # who has set an AOI, sensors and the threshold still cannot complete a run.
    years = list(range(date.today().year - 1, L4_START - 1, -1))
    overall = spec.value.periods.overall

    # `start_not_before_end` is emitted on `periods.overall.start`, so it draws
    # on the first Select. The end year claims its own subtree anyway: no rule
    # writes `periods.overall.end` today, and a control that silently dropped
    # one added later is exactly what `ProblemRouter` exists to prevent.
    router = ProblemRouter(problems_for("run", spec.value))

    SelectField(
        label=msg("run.start_year"),
        value=overall.start,
        items=years,
        on_value=lambda y: spec.set(
            spec.value.evolve(periods=replace(spec.value.periods, overall=Period(y, overall.end)))
        ),
        problems=router.take("periods.overall.start"),
    )
    SelectField(
        label=msg("run.end_year"),
        value=overall.end,
        items=years,
        on_value=lambda y: spec.set(
            spec.value.evolve(periods=replace(spec.value.periods, overall=Period(overall.start, y)))
        ),
        problems=router.take("periods.overall.end"),
    )

    # No sensor-coverage caption here any more. It restated, on every render
    # and under the wrong control, what `sensor_period_no_overlap` already
    # says only when it matters and on the control that owns it: that rule is
    # emitted on `vi_source.names` and names each sensor with its own range
    # ("None of the selected sensors has data in 2020-2024: Landsat 4
    # (1982-1993), ..."), so it draws on the Productivity step's Sensors
    # field. A period is chosen here, but it is the SENSORS that fail to
    # cover it.

    # Whatever the two Selects did not claim -- `internal_error`, on the empty
    # field this step also owns -- plus the build refusal, which is a real
    # error with no `Problem` behind it and so is wrapped in one to reach the
    # same styling.
    refusal = (
        (Problem(field="", code="build_refused", message=outcome.error, fatal=True),)
        if outcome.error is not None
        else ()
    )
    ProblemsList(problems=router.rest + refusal)
