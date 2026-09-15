"""The Run step: the overall period, whole-spec problems, and Build.

Build is SYNCHRONOUS by design. ``resolve()`` and ``build_indicator_maps()``
construct ``ee`` graphs and make no request -- the domain's own suite proves it,
running entirely offline against a mock credential. So this needs no
``use_task``: it either produces maps or raises ``SpecError``.
"""

from __future__ import annotations

import solara
from pysepal.solara.notifications import use_notifications

from app.message import msg
from app.state import is_runnable, problems_for
from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.indicator import IndicatorMaps, build_indicator_maps
from sdg1531.errors import SpecError
from sdg1531.resolve import resolve
from sdg1531.spec import RunSpec

__all__ = ("RunStep", "build")


def build(spec: RunSpec) -> tuple[IndicatorMaps, ExecutionContext]:
    """Resolve the spec and construct every graph. Pure; raises ``SpecError``.

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

    runnable = is_runnable(spec.value)

    def on_build() -> None:
        try:
            maps.value, ctx.value = build(spec.value)
        except SpecError as error:
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
