"""The AOI step writes the domain's AoiSpec and shows only its own problems."""

from __future__ import annotations

from typing import Any

import pytest
import solara
from pysepal.solara.components.aoi.aoi_result import AoiResult
from pysepal.solara.components.aoi.aoi_spec import AoiSpec as PysepalAoiSpec

from app.state import problems_for
from app.steps.aoi import AoiStep, apply_selection
from sdg1531.spec import AdminAoi, AssetAoi, RunSpec
from tests.app.render_helpers import alert_texts, markdown_texts


def _asset_selection(asset_id: str = "users/x/aoi", name: str = "aoi") -> AoiResult:
    # AoiView.on_value hands the step an AoiResult, never a bare mapping --
    # pysepal's own AoiSpec is what an ASSET result carries its asset_id in.
    return AoiResult(
        method="ASSET",
        name=name,
        spec=PysepalAoiSpec(method="ASSET", asset_id=asset_id),
    )


def _admin_selection(admin_code: str = "170", name: str = "Colombia") -> AoiResult:
    return AoiResult(
        method="ADMIN0",
        name=name,
        admin=admin_code,
        gee=True,
        spec=PysepalAoiSpec(method="ADMIN0", admin_codes=(admin_code,)),
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


def test_selecting_an_admin_area_writes_the_domain_arm_and_clears_the_problem():
    """The composition Task 16 unblocks: an ADMIN ``AoiResult`` -> ``AdminAoi``
    -> the step's own fatal problem clears. Covered at the adapter layer in
    isolation (``test_adapters.py``) and here as the thing the step actually
    does with it."""
    spec = solara.reactive(RunSpec())
    assert any(p.fatal for p in problems_for("aoi", spec.value))

    apply_selection(spec, _admin_selection())

    assert spec.value.aoi == AdminAoi(admin_code="170", name="Colombia")
    assert problems_for("aoi", spec.value) == ()


def test_the_view_is_wired_to_apply_the_selection_and_excludes_local_methods(monkeypatch):
    """Pins three things a passing suite could otherwise miss entirely:
    ``AoiView.on_value`` is really wired to ``apply_selection`` (not merely
    defined and unused), ``map_`` is passed through rather than dropped, and
    the local-only methods are really excluded -- by substituting a spy for
    ``AoiView`` and reading what the component actually calls it with,
    instead of asserting only on the extracted ``apply_selection`` helper.
    """
    captured: dict[str, Any] = {}

    @solara.component
    def _spy_aoi_view(
        *,
        value: Any = None,
        on_value: Any = None,
        loading: Any = None,
        methods: Any = None,
        map_: Any = None,
        gee: Any = None,
    ) -> None:
        captured.update(
            value=value, on_value=on_value, loading=loading, methods=methods, map_=map_, gee=gee
        )

    monkeypatch.setattr("app.steps.aoi.AoiView", _spy_aoi_view)

    spec = solara.reactive(RunSpec())
    sentinel_map = object()
    solara.render(AoiStep(spec=spec, map_=sentinel_map), handle_error=False)

    assert captured["methods"] == ["-SHAPE", "-POINTS"]
    assert captured["map_"] is sentinel_map
    assert callable(captured["on_value"])

    captured["on_value"](_asset_selection())
    assert spec.value.aoi == AssetAoi(asset_id="users/x/aoi", name="aoi")


@pytest.mark.parametrize("aoi", [None, AssetAoi(asset_id="users/x/aoi", name="aoi")])
def test_the_step_shows_its_description_and_nothing_else(aoi):
    """Pins what the step actually shows, in both states: its description, and
    no status or validation text at all.

    Two lines were removed, one request apart. "Selected: {name}" restated
    what ``AoiView``'s own controls already display two rows above it. The
    ``ProblemsAlert`` went next: this step owns exactly one rule
    (``missing_aoi``, "Select an area of interest"), rendered on the tab whose
    entire content is the area picker, under a heading that already says
    "Choose the area the indicator is computed over". The consequence it was
    really reporting is now shown by the tab strip instead -- PARAMS and
    Results are visibly locked until an AOI exists (see
    ``tests/app/test_tabs.py``).

    Both parameters are checked so that "shows nothing" cannot pass merely
    because the state under test happens to have no problem to show.
    """
    spec = solara.reactive(RunSpec().evolve(aoi=aoi))
    box, rc = solara.render(AoiStep(spec=spec, map_=None), handle_error=False)
    assert rc is not None
    assert alert_texts(box) == []
    assert markdown_texts(box) == ["<p>Choose the area the indicator is computed over.</p>"]


def test_the_aoi_step_still_owns_exactly_the_one_rule_its_silence_assumes():
    """The floor under the test above.

    Dropping the step's ``ProblemsAlert`` is only safe while ``missing_aoi``
    is the ONLY rule the AOI step owns -- a second one would have nowhere to
    appear, and no test anywhere would notice, because "the step renders no
    alert" is exactly what the test above asserts.

    So this walks every spec shape the AOI field can take and asserts the set
    of codes the step can ever own is that one. A new domain rule under the
    ``aoi`` prefix fails here, naming itself, which is the signal to give this
    step its alert back.
    """
    shapes = [
        RunSpec(),
        RunSpec().evolve(aoi=None),
        RunSpec().evolve(aoi=AssetAoi(asset_id="users/x/aoi", name="aoi")),
        RunSpec().evolve(aoi=AssetAoi(asset_id="", name="")),
    ]
    found = {problem.code for shape in shapes for problem in problems_for("aoi", shape)}
    assert found == {"missing_aoi"}, (
        f"the AOI step owns rules its silent step cannot show: {sorted(found - {'missing_aoi'})}"
    )
