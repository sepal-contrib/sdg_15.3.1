"""The AOI step writes the domain's AoiSpec and shows only its own problems."""

from __future__ import annotations

import solara
from pysepal.solara.components.aoi.aoi_result import AoiResult
from pysepal.solara.components.aoi.aoi_spec import AoiSpec as PysepalAoiSpec

from app.steps.aoi import AoiStep, apply_selection
from sdg1531.spec import AssetAoi, RunSpec


def _asset_selection(asset_id: str = "users/x/aoi", name: str = "aoi") -> AoiResult:
    # AoiView.on_value hands the step an AoiResult, never a bare mapping --
    # pysepal's own AoiSpec is what an ASSET result carries its asset_id in.
    return AoiResult(
        method="ASSET",
        name=name,
        spec=PysepalAoiSpec(method="ASSET", asset_id=asset_id),
    )


def test_the_step_renders_with_an_empty_spec():
    """The step is shown before the user has chosen anything."""
    spec = solara.reactive(RunSpec())
    _box, rc = solara.render(AoiStep(spec=spec, map_=None), handle_error=False)
    assert rc is not None


def test_selecting_an_asset_writes_the_domain_arm():
    """The step's job is to put a domain AoiSpec on the RunSpec -- not
    pysepal's same-named type, which is a different thing."""
    spec = solara.reactive(RunSpec())

    apply_selection(spec, _asset_selection())
    assert spec.value.aoi == AssetAoi(asset_id="users/x/aoi", name="aoi")


def test_applying_a_selection_changes_nothing_else():
    """evolve() returns a new RunSpec; every other field must survive."""
    before = RunSpec()
    spec = solara.reactive(before)

    apply_selection(spec, _asset_selection())
    after = spec.value
    assert after.vegetation_index == before.vegetation_index
    assert after.trajectory == before.trajectory
    assert after.periods == before.periods
