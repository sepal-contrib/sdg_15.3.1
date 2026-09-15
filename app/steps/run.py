"""The Run step: the overall period, whole-spec problems, and Build.

Build is SYNCHRONOUS by design. ``resolve()`` and ``build_indicator_maps()``
construct ``ee`` graphs and make no request -- the domain's own suite proves it,
running entirely offline against a mock credential. So this needs no
``use_task``: it produces maps, or it raises -- ``SpecError`` for most refusals,
but not only that: an overall period with a start and no end yet (a state the
two year Selects below reach naturally, one endpoint at a time) makes
``resolve()`` raise a bare ``ValueError`` instead (see ``app.state.is_runnable``'s
docstring). ``on_build`` below and ``is_runnable`` both treat any exception from
``resolve()`` as a build that cannot proceed, rather than trusting ``SpecError``
to be the only shape it takes.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import solara
from pysepal.solara.notifications import use_notifications

from app.message import msg
from app.state import is_runnable, problems_for
from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.indicator import IndicatorMaps, build_indicator_maps
from sdg1531.resolve import resolve
from sdg1531.spec import Period, RunSpec

__all__ = ("RunStep", "build")


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


@solara.component
def RunStep(
    spec: solara.Reactive[RunSpec],
    maps: solara.Reactive[IndicatorMaps | None],
    ctx: solara.Reactive[ExecutionContext | None],
) -> None:
    notifications = use_notifications()

    solara.Markdown(msg("run.description"))

    for problem in problems_for("run", spec.value):
        solara.Markdown(f"**{problem.message}**" if problem.fatal else problem.message)

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
    years = list(range(date.today().year - 1, 1981, -1))
    overall = spec.value.periods.overall

    solara.Select(
        label=msg("run.start_year"),
        value=overall.start,
        values=years,
        on_value=lambda y: spec.set(
            spec.value.evolve(periods=replace(spec.value.periods, overall=Period(y, overall.end)))
        ),
    )
    solara.Select(
        label=msg("run.end_year"),
        value=overall.end,
        values=years,
        on_value=lambda y: spec.set(
            spec.value.evolve(periods=replace(spec.value.periods, overall=Period(overall.start, y)))
        ),
    )

    runnable = is_runnable(spec.value)

    def on_build() -> None:
        # Not `except SpecError`: `disabled=not runnable` above keeps a normal
        # click from ever reaching an unresolvable spec, but the guard here
        # still has to be as total as `is_runnable` is -- resolve() can raise
        # a bare ValueError, not just SpecError (see this module's docstring).
        try:
            maps.value, ctx.value = build(spec.value)
        except Exception as error:
            notifications.error(str(error))
            return
        notifications.success(msg("run.built", count=len(maps.value.layers())))

    solara.Button(
        label=msg("run.build"),
        on_click=on_build,
        disabled=not runnable,
        color="primary",
    )

    if not runnable:
        solara.Markdown(msg("run.blocked"))
