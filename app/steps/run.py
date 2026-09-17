"""The Run step: the overall period, and what the current spec derives.

Deriving the maps and the context is pure ``ee`` graph construction -- no
network, no task, no spinner. ``resolve()`` and ``build_indicator_maps()``
make no request; the domain's own suite proves it, running entirely offline
against a mock credential (``tests/app/test_step_run.py``'s
``test_build_touches_no_network``). ``build_outcome`` below runs this on
every render (``app/page.py`` wraps it in ``use_memo``, keyed on the spec)
rather than behind a button: a button guarding a 19ms pure function guards
nothing, and a stored copy behind a reactive is exactly what let a stale
build survive a later spec edit -- the whole reason this step no longer
takes writable ``maps``/``ctx`` reactives at all.

``build_outcome`` is total: it never raises, for any spec. ``is_runnable`` is
asked first so an ordinary half-filled form produces a plain empty outcome
rather than an error message the user cannot act on -- this step already
renders ``problems_for("run", ...)`` and ``msg("run.blocked")`` for that
state. The ``except`` in ``build_outcome`` is for the narrower case
``is_runnable`` cannot see: ``resolve()`` succeeds and
``build_indicator_maps()`` still refuses (``spec.threshold`` unresolved is
the standing example -- ``validate()`` has no rule for it). That refusal used
to surface as an error toast from the Build button's handler; it must stay
visible now that there is no handler to catch it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

import solara

from app.message import msg
from app.state import is_runnable, render_problems
from sdg1531.catalog import L4_START, SENSORS
from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.indicator import IndicatorMaps, build_indicator_maps
from sdg1531.resolve import resolve
from sdg1531.spec import Period, RunSpec, SensorSelection

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


def _sensor_coverage_hint(spec: RunSpec) -> str | None:
    """What the currently selected sensors can actually deliver, or ``None``
    when no recognised sensor is selected yet.

    Informational only -- ``sdg1531.validate``'s ``sensor_period_no_overlap`` is
    what actually blocks a run (see that module's docstring, note 5); this just
    shows the constraint next to the two year Selects so a user sees it before
    hitting that refusal. Deliberately does NOT truncate or rewrite either
    Select's own range: a user who picks a period and then changes sensor must
    not have that period silently rewritten out from under them.
    """
    source = spec.vi_source
    if not isinstance(source, SensorSelection) or not source.names:
        return None
    known = [SENSORS[name] for name in source.names if name in SENSORS]
    if not known:
        return None

    first = min(info.first_year for info in known)
    last_years = [info.last_year for info in known if info.last_year is not None]
    if len(last_years) < len(known):  # at least one selected sensor is still active
        return str(msg("run.sensor_coverage_open", start=first))
    return str(msg("run.sensor_coverage_bounded", start=first, end=max(last_years)))


@solara.component
def RunStep(spec: solara.Reactive[RunSpec], outcome: BuildOutcome) -> None:
    # The description used to render here; it now lives in this step's own
    # PARAMS section header (`app/panels/params.py`), the same move task 28
    # made for the five output panels (`app/panels/outputs.py`'s module
    # docstring).

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

    coverage_hint = _sensor_coverage_hint(spec.value)
    if coverage_hint is not None:
        solara.Markdown(coverage_hint)

    render_problems("run", spec.value)

    if outcome.error is not None:
        solara.Markdown(f"**{outcome.error}**")
    elif outcome.maps is not None:
        solara.Markdown(msg("run.ready", count=len(outcome.maps.layers())))
    else:
        solara.Markdown(msg("run.blocked"))
