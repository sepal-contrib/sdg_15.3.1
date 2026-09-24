"""Productivity configuration.

Renders controls for: vi_source, vegetation_index, trajectory, lceu,
productivity_lookup, threshold. `climate` and the trend / state / performance
period overrides route their validation problems here too (see
`app.state.STEP_PREFIXES`), but neither has a control in this step yet.

The trajectory vocabulary carries a trap. Member NAMES do not match display
labels: ``S_RES_TREND`` is the one labelled "Water use efficiency", it is
disabled upstream and both ``validate()`` and the engine reject it, while
``UE_TREND`` ("Rain use efficiency") is the one that computes. Offering the
disabled member would let a user build a spec that cannot run.
"""

from __future__ import annotations

from collections.abc import Iterable

import solara

from app.message import msg
from app.panels.fields import ProblemRouter, SelectField, SliderField
from app.panels.problems import ProblemsList
from app.state import problems_for
from sdg1531.catalog import DISABLED_TRAJECTORIES, SENSORS
from sdg1531.enums import Lceu, ProductivityLookup, Trajectory, VegetationIndex
from sdg1531.spec import RunSpec, SensorSelection

__all__ = ("ProductivityStep", "selectable_trajectories")


def selectable_trajectories() -> tuple[Trajectory, ...]:
    """Every trajectory the user may pick -- the disabled ones removed."""
    return tuple(t for t in Trajectory if t not in DISABLED_TRAJECTORIES)


def _catalog_labels(prefix: str, values: Iterable[str]) -> dict[str, str]:
    """Map each raw enum value in ``values`` to its translated display label.

    Keyed on the member VALUE, not the name (see the module trap note) --
    ``productivity.{prefix}_value.<value>`` in the catalogue. Rebuilt on every
    render rather than cached: ``msg()`` subscribes to the current locale, so
    a cached copy would not update when the language changes.
    """
    return {value: msg(f"productivity.{prefix}_value.{value}") for value in values}


@solara.component
def ProductivityStep(spec: solara.Reactive[RunSpec]) -> None:
    def _seed_threshold() -> None:
        # The legacy slider's v_model was BOUND to the model (input_tile.py:
        # 31-39), so its 0 default landed in the model at first paint. The
        # SliderFloat below only ever DISPLAYS 0.0 when threshold is None --
        # nothing commits that default to the spec itself -- so an untouched
        # slider left `threshold=None` while `is_runnable()` returned True
        # and every sensor but Terra NPP raised `SpecError` on Build: exactly
        # the gap this control exists to close. Seed it once, on mount, so
        # the stored value can never disagree with what the slider shows.
        if spec.value.threshold is None:
            spec.set(spec.value.evolve(threshold=0.0))

    solara.use_effect(_seed_threshold, [])

    # The title is the PARAMS section header's (`app/panels/params.py`);
    # this step renders only its own controls.

    current = spec.value
    router = ProblemRouter(problems_for("productivity", spec.value))

    SelectField(
        label=msg("productivity.sensors"),
        multiple=True,
        # isinstance, not a truthiness guard: `vi_source` is a union, and the
        # other arm (PrecomputedViAsset) has no `.names` at all -- `asset_id`
        # and `scale` are its only fields, so `.names` is an AttributeError
        # rather than an empty list. This step only ever WRITES the sensor arm,
        # but a spec restored from `to_dict()` can carry the other one.
        value=(
            list(current.vi_source.names) if isinstance(current.vi_source, SensorSelection) else []
        ),
        items=sorted(SENSORS),
        on_value=lambda names: spec.set(
            spec.value.evolve(vi_source=SensorSelection(names=tuple(names)))
        ),
        # The whole `vi_source` subtree, so `missing_sensors` and
        # `sensor_period_no_overlap` (both on `vi_source.names`) land here --
        # the empty-field error that used to sit five controls below this one.
        problems=router.take("vi_source"),
    )

    index_labels = _catalog_labels("index", [v.value for v in VegetationIndex])
    index_by_label = {label: value for value, label in index_labels.items()}
    SelectField(
        label=msg("productivity.index"),
        value=index_labels[current.vegetation_index.value],
        items=list(index_labels.values()),
        on_value=lambda label: spec.set(
            spec.value.evolve(vegetation_index=VegetationIndex(index_by_label[label]))
        ),
        problems=router.take("vegetation_index"),
    )

    trajectory_labels = _catalog_labels("trajectory", [t.value for t in selectable_trajectories()])
    trajectory_by_label = {label: value for value, label in trajectory_labels.items()}
    SelectField(
        label=msg("productivity.trajectory"),
        # `.get(..., raw value)`: a spec restored from disk can hold the
        # disabled trajectory (see the module trap note above), which this
        # step never offers and therefore has no label for.
        value=trajectory_labels.get(current.trajectory.value, current.trajectory.value),
        items=list(trajectory_labels.values()),
        on_value=lambda label: spec.set(
            spec.value.evolve(trajectory=Trajectory(trajectory_by_label[label]))
        ),
        problems=router.take("trajectory"),
    )

    lceu_labels = _catalog_labels("lceu", [u.value for u in Lceu])
    lceu_by_label = {label: value for value, label in lceu_labels.items()}
    SelectField(
        label=msg("productivity.lceu"),
        value=lceu_labels[current.lceu.value],
        items=list(lceu_labels.values()),
        on_value=lambda label: spec.set(spec.value.evolve(lceu=Lceu(lceu_by_label[label]))),
        problems=router.take("lceu"),
    )

    SelectField(
        label=msg("productivity.lookup"),
        # No catalogue table for this one: the legacy's own labels
        # ("GPGv2"/"GPGv1") are identical to `ProductivityLookup`'s enum
        # values, unlike the other three vocabularies above.
        value=current.productivity_lookup.value,
        items=[p.value for p in ProductivityLookup],
        on_value=lambda v: spec.set(spec.value.evolve(productivity_lookup=ProductivityLookup(v))),
        problems=router.take("productivity_lookup"),
    )

    # The VI threshold. Transcribed from the legacy slider (input_tile.py:31-39):
    # min -1, max 1, step 0.01, defaulting to 0. It is NOT optional decoration --
    # every sensor rung except Terra NPP narrows `spec.threshold` with
    # `require_float` and raises `SpecError` when it is None (engine/integration.py
    # EXPECTED_DIVERGENCES note 1), while `validate()` has no rule for it. So with
    # no control here, `is_runnable()` returns True but `build_outcome()` refuses
    # for every sensor but Terra NPP -- exactly the narrower case its own `except`
    # exists for (see `app/steps/run.py`). `_seed_threshold` above is what
    # actually closes that gap; this fallback only keeps the display in sync
    # during the one render before the effect commits it.
    SliderField(
        label=msg("productivity.threshold"),
        value=current.threshold if current.threshold is not None else 0.0,
        min=-1.0,
        max=1.0,
        step=0.01,
        on_value=lambda v: spec.set(spec.value.evolve(threshold=v)),
        problems=router.take("threshold"),
    )

    # `climate.coefficient` and the trend / state / performance period
    # overrides route here (`app.state.STEP_PREFIXES`) and have no control in
    # this step, so the alert is still where their messages appear.
    ProblemsList(problems=router.rest)
