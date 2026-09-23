"""Sensors, index, trajectory, ecological units, lookup and the VI threshold."""

from __future__ import annotations

from dataclasses import replace

import ipyvuetify
import pytest
import solara

from app.message import msg
from app.steps.productivity import ProductivityStep, selectable_trajectories
from sdg1531.catalog import DISABLED_TRAJECTORIES, SENSORS
from sdg1531.enums import Lceu, ProductivityLookup, Trajectory, VegetationIndex
from sdg1531.spec import PeriodOverride, PrecomputedViAsset, RunSpec, SensorSelection
from tests.app.render_helpers import alert_texts, field_messages, find_widgets, markdown_texts
from tests.spec_factory import DEFAULT_PERIODS, default_spec

# `Trajectory` has four members and one (`S_RES_TREND`) is disabled -- named
# explicitly rather than derived from `selectable_trajectories()` itself, so a
# regression that narrows the function (e.g. to just `(UE_TREND,)`) has
# something independent to disagree with.
_EXPECTED_SELECTABLE_TRAJECTORIES = (
    Trajectory.NDVI_TREND,
    Trajectory.P_RES_TREND,
    Trajectory.UE_TREND,
)


def _selects(box: object) -> tuple[object, object, object, object, object]:
    """The step's five ``ipyvuetify.Select`` widgets, in source order:
    sensors (multiple), index, trajectory, lceu, lookup."""
    widgets = find_widgets(box, ipyvuetify.Select)
    assert len(widgets) == 5
    return tuple(widgets)  # type: ignore[return-value]


def _slider(box: object) -> object:
    sliders = find_widgets(box, ipyvuetify.Slider)
    assert len(sliders) == 1
    return sliders[0]


def test_the_step_renders():
    spec = solara.reactive(default_spec())
    _box, rc = solara.render(ProductivityStep(spec=spec), handle_error=False)
    assert rc is not None


def test_the_disabled_trajectory_is_not_offered():
    """S_RES_TREND raises in the engine and validate() rejects it, so offering
    it would build a spec the user cannot run. Pinned against the explicit
    membership, not against ``selectable_trajectories()``'s own output --
    comparing the function to itself cannot catch it silently narrowing to,
    say, only ``UE_TREND``."""
    assert set(Trajectory) - set(DISABLED_TRAJECTORIES) == set(_EXPECTED_SELECTABLE_TRAJECTORIES)
    assert selectable_trajectories() == _EXPECTED_SELECTABLE_TRAJECTORIES


def test_choosing_an_index_leaves_everything_else_alone():
    spec = solara.reactive(default_spec())
    before = spec.value
    spec.value = spec.value.evolve(vegetation_index=VegetationIndex.EVI)
    assert spec.value.vegetation_index is VegetationIndex.EVI
    assert spec.value.trajectory == before.trajectory
    assert spec.value.aoi == before.aoi


def test_the_widgets_show_the_current_spec_values():
    """Reads the real render tree -- each control's label, current value and
    offered choices -- rather than an extracted helper's return value.
    Expected label text is computed through ``msg()`` (the catalogue), not
    hardcoded English, so a translation does not break this. The disabled
    trajectory is checked here too: not merely absent from
    ``selectable_trajectories()`` in isolation, but actually missing from the
    rendered Select's own ``items``."""
    spec = solara.reactive(default_spec(threshold=0.42))
    box, rc = solara.render(ProductivityStep(spec=spec), handle_error=False)
    assert rc is not None

    sensors, index, trajectory, lceu, lookup = _selects(box)

    assert sensors.label == msg("productivity.sensors")
    assert sensors.multiple is True
    assert sensors.items == sorted(SENSORS)
    assert sensors.v_model == ["MODIS MOD13Q1"]

    assert index.label == msg("productivity.index")
    assert index.items == [msg(f"productivity.index_value.{v.value}") for v in VegetationIndex]
    assert index.v_model == msg("productivity.index_value.ndvi")

    assert trajectory.label == msg("productivity.trajectory")
    # Exact list equality, not a subset check -- proves the disabled
    # trajectory is missing from the rendered Select's own items, the same
    # way an extra, unexpected item would also fail this. The catalogue key
    # for the disabled trajectory (`s_res_trend`) is gone entirely (Task 25,
    # M6: unreachable through any code path), so there is nothing left to
    # look up and assert absent.
    assert trajectory.items == [
        msg(f"productivity.trajectory_value.{t.value}") for t in _EXPECTED_SELECTABLE_TRAJECTORIES
    ]
    assert trajectory.v_model == msg("productivity.trajectory_value.ndvi_trend")

    assert lceu.label == msg("productivity.lceu")
    assert lceu.items == [msg(f"productivity.lceu_value.{u.value}") for u in Lceu]
    assert lceu.v_model == msg("productivity.lceu_value.gaes")

    assert lookup.label == msg("productivity.lookup")
    assert lookup.items == [p.value for p in ProductivityLookup]
    assert lookup.v_model == ProductivityLookup.GPGV2.value

    slider = _slider(box)
    assert slider.label == msg("productivity.threshold")
    assert slider.min == -1.0
    assert slider.max == 1.0
    assert slider.step == 0.01
    assert slider.v_model == 0.42


def test_every_label_and_the_description_route_through_msg(monkeypatch):
    """Every other assertion in this file compares a rendered label against
    ``msg()``'s own English return value, so a hardcoded English literal in
    place of a ``msg()`` call would satisfy all of them by coincidence.
    Substituting a distinguishing stand-in for ``msg`` instead proves each
    rendered string is really that call's OUTPUT, not a literal that happens
    to match it -- including the two catalogue-keyed value labels, which a
    literal could not reproduce for more than one locale anyway.

    The description itself is no longer rendered by this step (task 30: it
    rides on ``ParamsPanel``'s own ``SectionHeader`` now -- see
    ``app/panels/params.py``), so this test's name is now a slight
    overstatement kept for continuity with its own history;
    ``tests/app/test_panel_params.py``'s ``test_each_sections_own_
    description_travels_with_it`` pins the description to
    ``msg("productivity.description")`` instead.
    """

    def _fake_msg(key: str, **_: object) -> str:
        return f"<{key}>"

    monkeypatch.setattr("app.steps.productivity.msg", _fake_msg)

    spec = solara.reactive(default_spec())
    box, rc = solara.render(ProductivityStep(spec=spec), handle_error=False)
    assert rc is not None

    sensors, index, trajectory, lceu, lookup = _selects(box)
    assert sensors.label == "<productivity.sensors>"
    assert index.label == "<productivity.index>"
    assert index.v_model == "<productivity.index_value.ndvi>"
    assert trajectory.label == "<productivity.trajectory>"
    assert trajectory.v_model == "<productivity.trajectory_value.ndvi_trend>"
    assert lceu.label == "<productivity.lceu>"
    assert lceu.v_model == "<productivity.lceu_value.gaes>"
    assert lookup.label == "<productivity.lookup>"

    slider = _slider(box)
    assert slider.label == "<productivity.threshold>"


def test_an_unset_threshold_is_committed_to_the_spec_not_merely_displayed():
    """The legacy slider's ``v_model`` was BOUND to the model
    (input_tile.py:31-39), so its 0 default landed in the model at first
    paint. Every sensor but Terra NPP requires a resolved float threshold
    (engine/integration.py EXPECTED_DIVERGENCES note 1) and ``validate()``
    has no rule for it, so a slider that only DISPLAYS 0.0 while leaving
    ``spec.threshold`` at ``None`` reopens exactly the gap this control
    exists to close: Build stays enabled and then fails with ``SpecError``
    for every sensor but Terra NPP. Assert the spec itself, not just the
    widget's own ``v_model``."""
    spec = solara.reactive(default_spec())
    assert spec.value.threshold is None
    box, rc = solara.render(ProductivityStep(spec=spec), handle_error=False)
    assert rc is not None
    assert _slider(box).v_model == 0.0
    assert spec.value.threshold == 0.0


def test_a_precomputed_vi_asset_does_not_crash_the_sensors_widget():
    """``vi_source`` is a union; the other arm (``PrecomputedViAsset``) has no
    ``.names`` at all. A truthiness guard (``if current.vi_source``) would
    still reach ``.names`` and raise ``AttributeError`` -- only ``isinstance``
    protects this render."""
    spec = solara.reactive(default_spec(vi_source=PrecomputedViAsset(asset_id="x", scale=10)))
    box, rc = solara.render(ProductivityStep(spec=spec), handle_error=False)
    assert rc is not None
    sensors, *_ = _selects(box)
    assert sensors.v_model == []


def test_changing_the_sensors_updates_only_vi_source():
    spec = solara.reactive(default_spec())
    box, rc = solara.render(ProductivityStep(spec=spec), handle_error=False)
    assert rc is not None
    sensors, *_ = _selects(box)
    before = spec.value

    sensors.v_model = ["Sentinel 2", "Landsat 8"]

    assert spec.value.vi_source == SensorSelection(names=("Sentinel 2", "Landsat 8"))
    assert spec.value.evolve(vi_source=before.vi_source) == before


def test_changing_the_index_updates_only_vegetation_index():
    spec = solara.reactive(default_spec())
    box, rc = solara.render(ProductivityStep(spec=spec), handle_error=False)
    assert rc is not None
    _sensors, index, _trajectory, _lceu, _lookup = _selects(box)
    before = spec.value

    index.v_model = msg("productivity.index_value.evi")

    assert spec.value.vegetation_index is VegetationIndex.EVI
    assert spec.value.evolve(vegetation_index=before.vegetation_index) == before


def test_changing_the_trajectory_updates_only_trajectory():
    spec = solara.reactive(default_spec())
    box, rc = solara.render(ProductivityStep(spec=spec), handle_error=False)
    assert rc is not None
    _sensors, _index, trajectory, _lceu, _lookup = _selects(box)
    before = spec.value

    trajectory.v_model = msg("productivity.trajectory_value.ue_trend")

    assert spec.value.trajectory is Trajectory.UE_TREND
    assert spec.value.evolve(trajectory=before.trajectory) == before


def test_changing_the_lceu_updates_only_lceu():
    spec = solara.reactive(default_spec())
    box, rc = solara.render(ProductivityStep(spec=spec), handle_error=False)
    assert rc is not None
    _sensors, _index, _trajectory, lceu, _lookup = _selects(box)
    before = spec.value

    lceu.v_model = msg("productivity.lceu_value.aez")

    assert spec.value.lceu is Lceu.AEZ
    assert spec.value.evolve(lceu=before.lceu) == before


def test_changing_the_lookup_updates_only_productivity_lookup():
    spec = solara.reactive(default_spec())
    box, rc = solara.render(ProductivityStep(spec=spec), handle_error=False)
    assert rc is not None
    _sensors, _index, _trajectory, _lceu, lookup = _selects(box)
    before = spec.value

    lookup.v_model = ProductivityLookup.GPGV1.value

    assert spec.value.productivity_lookup is ProductivityLookup.GPGV1
    assert spec.value.evolve(productivity_lookup=before.productivity_lookup) == before


def test_moving_the_threshold_slider_updates_only_threshold():
    spec = solara.reactive(default_spec())
    box, rc = solara.render(ProductivityStep(spec=spec), handle_error=False)
    assert rc is not None
    slider = _slider(box)
    before = spec.value

    slider.v_model = -0.35

    assert spec.value.threshold == pytest.approx(-0.35)
    assert spec.value.evolve(threshold=before.threshold) == before


@pytest.mark.parametrize(
    ("spec", "expected_fields", "expected_alerts"),
    [
        (default_spec(), [], []),
        (RunSpec(), [("error", "Select at least one sensor.")], []),
        (
            default_spec(trajectory=Trajectory.S_RES_TREND),
            [("error", "The water use efficiency trajectory is not implemented.")],
            [],
        ),
        (default_spec(aoi=None), [], []),
        (
            # `periods.state` under four years. This USED to be this file's
            # one `warning` case; it is now fatal, because the empty baseline
            # it describes is a server-side refusal rather than a masked layer
            # (`sdg1531/validate.py`'s note 6). Kept as an `error` case rather
            # than deleted: it is the specific configuration the repo owner
            # actually hit, so it is worth pinning that the step now shows it
            # as blocking.
            default_spec(periods=replace(DEFAULT_PERIODS, state=PeriodOverride(2018, 2020))),
            [],
            [
                (
                    "error",
                    "The productivity state period needs at least four years: its "
                    "baseline is measured over everything up to the last three, so "
                    "a shorter window leaves nothing to compare the recent years "
                    "against and Earth Engine refuses the productivity layer.",
                )
            ],
        ),
    ],
)
def test_the_step_renders_only_its_own_problems(spec, expected_fields, expected_alerts):
    """Pins what the step actually shows: a fully-configured spec renders
    nothing (task 30 moved the description into ``ParamsPanel``'s own
    ``SectionHeader`` -- see ``app/panels/params.py``); a spec with a fatal
    problem THIS step owns (no sensors, the disabled trajectory, or a state
    period under four years) shows it as an ``error``; and a spec whose only
    fatal problem belongs to ANOTHER step (missing AOI) shows nothing -- the
    case that actually distinguishes ``problems_for("productivity", ...)``
    from ``validate(...)``.

    Every problem THIS step owns is now fatal, so nothing here exercises the
    ``warning`` alert any more (the state-period case did, until it turned out
    to be a server-side refusal -- ``sdg1531/validate.py``'s note 6).
    ``tests/app/test_step_land_cover.py`` and ``tests/app/test_step_soc.py``
    each still carry a genuine warning case, so the two-severity rendering is
    not left unproven anywhere -- it is just not provable here.

    Read off BOTH routes. ``missing_sensors`` and ``unsupported_trajectory``
    name fields this step has controls for, so they are drawn by the Sensors
    and Trend method Selects themselves; ``state_period_too_short`` names
    ``periods.state``, which has no control here at all, so it still reaches
    the alert. Splitting the expectation that way is what pins WHICH route
    each message takes, not merely that it appears somewhere.
    """
    spec_r = solara.reactive(spec)
    box, rc = solara.render(ProductivityStep(spec=spec_r), handle_error=False)
    assert rc is not None
    assert field_messages(box) == expected_fields
    assert alert_texts(box) == expected_alerts
    assert markdown_texts(box) == []
