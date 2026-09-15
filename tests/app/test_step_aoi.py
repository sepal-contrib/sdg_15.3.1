"""The AOI step writes the domain's AoiSpec and shows only its own problems."""

from __future__ import annotations

import re
from typing import Any

import pytest
import solara
from pysepal.solara.components.aoi.aoi_result import AoiResult
from pysepal.solara.components.aoi.aoi_spec import AoiSpec as PysepalAoiSpec

from app.state import problems_for
from app.steps.aoi import AoiStep, apply_selection
from sdg1531.spec import AdminAoi, AssetAoi, RunSpec

_MARKDOWN_RE = re.compile(r'<div class="solara-markdown[^"]*"[^>]*>(.*?)</div>', re.DOTALL)


def _markdown_texts(node: object) -> list[str]:
    """Every rendered markdown paragraph under ``node``, in tree order.

    Reads the real render tree (each ``solara.Markdown`` becomes a
    ``VuetifyTemplate`` whose ``template`` embeds the rendered HTML), so this
    sees exactly what a user would: not just that the component "did not
    raise", but which text -- the description, a selection, a validation
    problem -- actually appears.
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
        captured.update(value=value, on_value=on_value, loading=loading, methods=methods, map_=map_, gee=gee)

    monkeypatch.setattr("app.steps.aoi.AoiView", _spy_aoi_view)

    spec = solara.reactive(RunSpec())
    sentinel_map = object()
    solara.render(AoiStep(spec=spec, map_=sentinel_map), handle_error=False)

    assert captured["methods"] == ["-SHAPE", "-POINTS"]
    assert captured["map_"] is sentinel_map
    assert callable(captured["on_value"])

    captured["on_value"](_asset_selection())
    assert spec.value.aoi == AssetAoi(asset_id="users/x/aoi", name="aoi")


@pytest.mark.parametrize(
    ("aoi", "expected"),
    [
        (
            None,
            [
                "<p>Choose the area the indicator is computed over.</p>",
                "<p><strong>Select an area of interest.</strong></p>",
            ],
        ),
        (
            AssetAoi(asset_id="users/x/aoi", name="aoi"),
            [
                "<p>Choose the area the indicator is computed over.</p>",
                "<p>Selected: aoi</p>",
            ],
        ),
    ],
)
def test_the_step_renders_only_its_own_text(aoi, expected):
    """Pins what the step actually shows, in both states, so that renaming the
    step passed to ``problems_for`` (which shows nothing for ``RunSpec()``'s
    other steps), deleting the problems loop, or dropping the exclusion
    rendered by ``AoiView`` cannot pass unnoticed."""
    spec = solara.reactive(RunSpec().evolve(aoi=aoi))
    box, rc = solara.render(AoiStep(spec=spec, map_=None), handle_error=False)
    assert rc is not None
    assert _markdown_texts(box) == expected
