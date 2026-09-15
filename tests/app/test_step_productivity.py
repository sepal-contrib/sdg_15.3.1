"""Sensors, index, trajectory, ecological units, lookup, threshold, climate."""

from __future__ import annotations

import re

import ipyvuetify
import pytest
import solara

from app.message import msg
from app.steps.productivity import ProductivityStep, selectable_trajectories
from sdg1531.catalog import DISABLED_TRAJECTORIES, SENSORS
from sdg1531.enums import Lceu, ProductivityLookup, Trajectory, VegetationIndex
from sdg1531.spec import PrecomputedViAsset, RunSpec, SensorSelection
from tests.spec_factory import default_spec

_MARKDOWN_RE = re.compile(r'<div class="solara-markdown[^"]*"[^>]*>(.*?)</div>', re.DOTALL)


def _markdown_texts(node: object) -> list[str]:
    """Every rendered markdown paragraph under ``node``, in tree order.

    See ``tests/app/test_step_aoi.py`` for why this reads ``.template``
    rather than an extracted helper.
    """
    texts = []
    template = getattr(node, "template", None)
    if isinstance(template, str) and "solara-markdown" in template:
        match = _MARKDOWN_RE.search(template)
        if match:
            texts.append(match.group(1).strip())
    for child in getattr(node, "children", None) or ():
        texts.extend(_markdown_texts(child))
    return texts


def _find_widgets(root: object, cls: type) -> list[object]:
    """Every ``cls`` instance in the render tree, in tree order."""
    found = [root] if isinstance(root, cls) else []
    for child in getattr(root, "children", None) or []:
        found.extend(_find_widgets(child, cls))
    return found


def _selects(box: object) -> tuple[object, object, object, object, object]:
    """The step's five ``ipyvuetify.Select`` widgets, in source order:
    sensors (multiple), index, trajectory, lceu, lookup."""
    widgets = _find_widgets(box, ipyvuetify.Select)
    assert len(widgets) == 5
    return tuple(widgets)  # type: ignore[return-value]


def _slider(box: object) -> object:
    sliders = _find_widgets(box, ipyvuetify.Slider)
    assert len(sliders) == 1
    return sliders[0]


def test_the_step_renders():
    spec = solara.reactive(default_spec())
    _box, rc = solara.render(ProductivityStep(spec=spec), handle_error=False)
    assert rc is not None


def test_the_disabled_trajectory_is_not_offered():
    """S_RES_TREND raises in the engine and validate() rejects it, so offering
    it would build a spec the user cannot run."""
    offered = selectable_trajectories()
    assert Trajectory.S_RES_TREND in DISABLED_TRAJECTORIES
    assert Trajectory.S_RES_TREND not in offered
    assert Trajectory.UE_TREND in offered


def test_choosing_an_index_leaves_everything_else_alone():
    spec = solara.reactive(default_spec())
    before = spec.value
    spec.value = spec.value.evolve(vegetation_index=VegetationIndex.EVI)
    assert spec.value.vegetation_index is VegetationIndex.EVI
    assert spec.value.trajectory == before.trajectory
    assert spec.value.aoi == before.aoi


def test_the_widgets_show_the_current_spec_values():
    """Reads the real render tree -- each control's label, current value and
    offered choices -- rather than an extracted helper's return value. The
    disabled trajectory is checked here too: not merely absent from
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
    assert index.items == [v.value for v in VegetationIndex]
    assert index.v_model == VegetationIndex.NDVI.value

    assert trajectory.label == msg("productivity.trajectory")
    assert trajectory.items == [t.value for t in selectable_trajectories()]
    assert Trajectory.S_RES_TREND.value not in trajectory.items
    assert trajectory.v_model == Trajectory.NDVI_TREND.value

    assert lceu.label == msg("productivity.lceu")
    assert lceu.items == [u.value for u in Lceu]
    assert lceu.v_model == Lceu.GAES.value

    assert lookup.label == msg("productivity.lookup")
    assert lookup.items == [p.value for p in ProductivityLookup]
    assert lookup.v_model == ProductivityLookup.GPGV2.value

    slider = _slider(box)
    assert slider.label == msg("productivity.threshold")
    assert slider.min == -1.0
    assert slider.max == 1.0
    assert slider.step == 0.01
    assert slider.v_model == 0.42


def test_an_unset_threshold_defaults_the_slider_to_zero():
    """The legacy slider defaulted to 0 (input_tile.py:31-39); every sensor
    but Terra NPP requires a resolved float threshold (engine/integration.py
    EXPECTED_DIVERGENCES note 1) while ``validate()`` has no rule for it. A
    control that instead defaulted to ``None`` would leave a spec
    ``is_runnable()`` accepts but ``build()`` rejects for every other sensor.
    """
    spec = solara.reactive(default_spec())
    assert spec.value.threshold is None
    box, rc = solara.render(ProductivityStep(spec=spec), handle_error=False)
    assert rc is not None
    assert _slider(box).v_model == 0.0


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

    index.v_model = VegetationIndex.EVI.value

    assert spec.value.vegetation_index is VegetationIndex.EVI
    assert spec.value.evolve(vegetation_index=before.vegetation_index) == before


def test_changing_the_trajectory_updates_only_trajectory():
    spec = solara.reactive(default_spec())
    box, rc = solara.render(ProductivityStep(spec=spec), handle_error=False)
    assert rc is not None
    _sensors, _index, trajectory, _lceu, _lookup = _selects(box)
    before = spec.value

    trajectory.v_model = Trajectory.UE_TREND.value

    assert spec.value.trajectory is Trajectory.UE_TREND
    assert spec.value.evolve(trajectory=before.trajectory) == before


def test_changing_the_lceu_updates_only_lceu():
    spec = solara.reactive(default_spec())
    box, rc = solara.render(ProductivityStep(spec=spec), handle_error=False)
    assert rc is not None
    _sensors, _index, _trajectory, lceu, _lookup = _selects(box)
    before = spec.value

    lceu.v_model = Lceu.AEZ.value

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
    ("spec", "expected_extra"),
    [
        (default_spec(), []),
        (
            RunSpec(),
            ["<p><strong>Select at least one sensor.</strong></p>"],
        ),
        (
            default_spec(trajectory=Trajectory.S_RES_TREND),
            ["<p><strong>The water use efficiency trajectory is not implemented.</strong></p>"],
        ),
        (
            default_spec(aoi=None),
            [],
        ),
    ],
)
def test_the_step_renders_only_its_own_text(spec, expected_extra):
    """Pins what the step actually shows: a fully-configured spec shows only
    the description; a spec with a fatal problem THIS step owns (no sensors,
    or the disabled trajectory) shows that problem's text; and a spec whose
    only fatal problem belongs to ANOTHER step (missing AOI) shows neither --
    the case that actually distinguishes ``problems_for("productivity", ...)``
    from ``validate(...)``."""
    spec_r = solara.reactive(spec)
    box, rc = solara.render(ProductivityStep(spec=spec_r), handle_error=False)
    assert rc is not None
    assert _markdown_texts(box) == [
        "<p>Vegetation index, trend method and ecological units.</p>",
        *expected_extra,
    ]
