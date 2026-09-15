"""Productivity configuration.

Owns: vi_source, vegetation_index, trajectory, lceu, productivity_lookup,
threshold, climate, and the trend / state / performance periods.

The trajectory vocabulary carries a trap. Member NAMES do not match display
labels: ``S_RES_TREND`` is the one labelled "Water use efficiency", it is
disabled upstream and both ``validate()`` and the engine reject it, while
``UE_TREND`` ("Rain use efficiency") is the one that computes. Offering the
disabled member would let a user build a spec that cannot run.
"""

from __future__ import annotations

import solara

from app.message import msg
from app.state import problems_for
from sdg1531.catalog import DISABLED_TRAJECTORIES, SENSORS
from sdg1531.enums import Lceu, ProductivityLookup, Trajectory, VegetationIndex
from sdg1531.spec import RunSpec, SensorSelection

__all__ = ("ProductivityStep", "selectable_trajectories")


def selectable_trajectories() -> tuple[Trajectory, ...]:
    """Every trajectory the user may pick -- the disabled ones removed."""
    return tuple(t for t in Trajectory if t not in DISABLED_TRAJECTORIES)


@solara.component
def ProductivityStep(spec: solara.Reactive[RunSpec]) -> None:
    solara.Markdown(msg("productivity.description"))

    current = spec.value

    solara.SelectMultiple(
        label=msg("productivity.sensors"),
        # isinstance, not a truthiness guard: `vi_source` is a union, and the
        # other arm (PrecomputedViAsset) has no `.names` at all -- `asset_id`
        # and `scale` are its only fields, so `.names` is an AttributeError
        # rather than an empty list. This step only ever WRITES the sensor arm,
        # but a spec restored from `to_dict()` can carry the other one.
        values=(
            list(current.vi_source.names) if isinstance(current.vi_source, SensorSelection) else []
        ),
        all_values=sorted(SENSORS),
        on_value=lambda names: spec.set(
            spec.value.evolve(vi_source=SensorSelection(names=tuple(names)))
        ),
    )

    solara.Select(
        label=msg("productivity.index"),
        value=current.vegetation_index.value,
        values=[v.value for v in VegetationIndex],
        on_value=lambda v: spec.set(spec.value.evolve(vegetation_index=VegetationIndex(v))),
    )

    solara.Select(
        label=msg("productivity.trajectory"),
        value=current.trajectory.value,
        values=[t.value for t in selectable_trajectories()],
        on_value=lambda v: spec.set(spec.value.evolve(trajectory=Trajectory(v))),
    )

    solara.Select(
        label=msg("productivity.lceu"),
        value=current.lceu.value,
        values=[u.value for u in Lceu],
        on_value=lambda v: spec.set(spec.value.evolve(lceu=Lceu(v))),
    )

    solara.Select(
        label=msg("productivity.lookup"),
        value=current.productivity_lookup.value,
        values=[p.value for p in ProductivityLookup],
        on_value=lambda v: spec.set(spec.value.evolve(productivity_lookup=ProductivityLookup(v))),
    )

    # The VI threshold. Transcribed from the legacy slider (input_tile.py:31-39):
    # min -1, max 1, step 0.01, defaulting to 0. It is NOT optional decoration --
    # every sensor rung except Terra NPP narrows `spec.threshold` with
    # `require_float` and raises `SpecError` when it is None (engine/integration.py
    # EXPECTED_DIVERGENCES note 1), while `validate()` has no rule for it. So with
    # no control here, `is_runnable()` returns True, the Build button is enabled,
    # and pressing it fails for every sensor but Terra NPP. The legacy never hit
    # that because its slider defaulted to 0; this one has to do the same.
    solara.SliderFloat(
        label=msg("productivity.threshold"),
        value=current.threshold if current.threshold is not None else 0.0,
        min=-1.0,
        max=1.0,
        step=0.01,
        on_value=lambda v: spec.set(spec.value.evolve(threshold=v)),
    )

    for problem in problems_for("productivity", spec.value):
        solara.Markdown(f"**{problem.message}**" if problem.fatal else problem.message)
