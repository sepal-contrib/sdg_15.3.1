"""Land cover source, transition matrix, water mask, land-cover period."""

from __future__ import annotations

from dataclasses import replace

import ipyvuetify
import pytest
import solara

from app.message import msg
from app.state import problems_for
from app.steps.land_cover import LandCoverStep
from sdg1531.spec import (
    CustomLandCoverSource,
    EsaCciSource,
    JrcSeasonalityMask,
    PeriodOverride,
    PixelValueMask,
)
from tests.app.render_helpers import find_widgets, markdown_texts
from tests.spec_factory import default_spec


def _select(box: object) -> object:
    selects = find_widgets(box, ipyvuetify.Select)
    assert len(selects) == 1
    return selects[0]


def _slider(box: object) -> object:
    sliders = find_widgets(box, ipyvuetify.Slider)
    assert len(sliders) == 1
    return sliders[0]


def test_the_step_renders():
    spec = solara.reactive(default_spec())
    _box, rc = solara.render(LandCoverStep(spec=spec), handle_error=False)
    assert rc is not None


def test_a_collapsing_land_cover_period_is_shown_by_this_step():
    """Both endpoints clamp to 1992, which the domain rejects. If this step
    did not own the problem the user would meet it as a pandas error in the
    charts instead."""
    spec = default_spec().evolve(
        periods=replace(default_spec().periods, land_cover=PeriodOverride(1980, 1985))
    )
    codes = {p.code for p in problems_for("land_cover", spec)}
    assert "land_cover_period_collapses" in codes


def test_the_widgets_show_the_current_spec_values():
    """Reads the real render tree -- each control's label, current value and
    offered choices -- rather than an extracted helper's return value.
    Expected label text is computed through ``msg()`` (the catalogue), not
    hardcoded English, so a translation does not break this."""
    spec = solara.reactive(default_spec())
    box, rc = solara.render(LandCoverStep(spec=spec), handle_error=False)
    assert rc is not None

    source = _select(box)
    assert source.label == msg("land_cover.source")
    assert source.items == [msg("land_cover.esa"), msg("land_cover.custom")]
    assert source.v_model == msg("land_cover.esa")

    # No custom-asset text fields while ESA CCI is selected.
    assert find_widgets(box, ipyvuetify.TextField) == []

    slider = _slider(box)
    assert slider.label == msg("land_cover.water_mask")
    assert slider.min == 1
    assert slider.max == 12
    assert slider.v_model == 6


def test_the_custom_source_shows_asset_text_fields_with_their_current_values():
    spec = solara.reactive(
        default_spec(
            land_cover=CustomLandCoverSource(start_asset="users/x/start", end_asset="users/x/end")
        )
    )
    box, rc = solara.render(LandCoverStep(spec=spec), handle_error=False)
    assert rc is not None

    source = _select(box)
    assert source.v_model == msg("land_cover.custom")

    start_field, end_field = find_widgets(box, ipyvuetify.TextField)
    assert start_field.label == msg("land_cover.start_asset")
    assert start_field.v_model == "users/x/start"
    assert end_field.label == msg("land_cover.end_asset")
    assert end_field.v_model == "users/x/end"


def test_a_non_jrc_water_mask_does_not_crash_the_slider():
    """``water_mask`` is a union; two of its arms (``PixelValueMask``,
    ``AssetBandMask``) have no ``.threshold`` at all. A truthiness guard
    (``if current.water_mask``) would still reach ``.threshold`` and raise
    ``AttributeError`` -- only ``isinstance`` protects this render."""
    spec = solara.reactive(default_spec(water_mask=PixelValueMask(value=5)))
    box, rc = solara.render(LandCoverStep(spec=spec), handle_error=False)
    assert rc is not None
    assert _slider(box).v_model == 6


def test_changing_the_source_to_custom_updates_only_land_cover():
    spec = solara.reactive(default_spec())
    box, rc = solara.render(LandCoverStep(spec=spec), handle_error=False)
    assert rc is not None
    before = spec.value

    _select(box).v_model = msg("land_cover.custom")

    assert spec.value.land_cover == CustomLandCoverSource(start_asset="", end_asset="")
    assert spec.value.evolve(land_cover=before.land_cover) == before


def test_changing_the_source_back_to_esa_updates_only_land_cover():
    spec = solara.reactive(
        default_spec(land_cover=CustomLandCoverSource(start_asset="a", end_asset="b"))
    )
    box, rc = solara.render(LandCoverStep(spec=spec), handle_error=False)
    assert rc is not None
    before = spec.value

    _select(box).v_model = msg("land_cover.esa")

    assert spec.value.land_cover == EsaCciSource()
    assert spec.value.evolve(land_cover=before.land_cover) == before


def test_changing_the_start_asset_updates_only_that_field():
    # water_mask is deliberately NOT default_spec()'s own JrcSeasonalityMask(6):
    # a handler that also (wrongly) resets water_mask to the domain default
    # would otherwise be a no-op against it and this test would not notice.
    spec = solara.reactive(
        default_spec(
            land_cover=CustomLandCoverSource(start_asset="a", end_asset="b"),
            water_mask=JrcSeasonalityMask(threshold=9),
        )
    )
    box, rc = solara.render(LandCoverStep(spec=spec), handle_error=False)
    assert rc is not None
    start_field, _end_field = find_widgets(box, ipyvuetify.TextField)
    before = spec.value

    start_field.v_model = "users/x/new-start"

    assert spec.value.land_cover == CustomLandCoverSource(
        start_asset="users/x/new-start", end_asset="b"
    )
    assert spec.value.evolve(land_cover=before.land_cover) == before


def test_changing_the_end_asset_updates_only_that_field():
    spec = solara.reactive(
        default_spec(
            land_cover=CustomLandCoverSource(start_asset="a", end_asset="b"),
            water_mask=JrcSeasonalityMask(threshold=9),
        )
    )
    box, rc = solara.render(LandCoverStep(spec=spec), handle_error=False)
    assert rc is not None
    _start_field, end_field = find_widgets(box, ipyvuetify.TextField)
    before = spec.value

    end_field.v_model = "users/x/new-end"

    assert spec.value.land_cover == CustomLandCoverSource(
        start_asset="a", end_asset="users/x/new-end"
    )
    assert spec.value.evolve(land_cover=before.land_cover) == before


def test_changing_the_water_mask_threshold_updates_only_water_mask():
    # land_cover is a CustomLandCoverSource here, not default_spec()'s own
    # EsaCciSource() -- a handler that also (wrongly) resets land_cover back
    # to EsaCciSource() would be a no-op against the default and pass anyway.
    spec = solara.reactive(
        default_spec(land_cover=CustomLandCoverSource(start_asset="a", end_asset="b"))
    )
    box, rc = solara.render(LandCoverStep(spec=spec), handle_error=False)
    assert rc is not None
    before = spec.value

    _slider(box).v_model = 9

    assert spec.value.water_mask == JrcSeasonalityMask(threshold=9)
    assert spec.value.evolve(water_mask=before.water_mask) == before


def test_every_label_and_the_description_route_through_msg(monkeypatch):
    """Every other assertion in this file compares a rendered label against
    ``msg()``'s own English return value, so a hardcoded English literal in
    place of a ``msg()`` call would satisfy all of them by coincidence.
    Substituting a distinguishing stand-in for ``msg`` instead proves each
    rendered string is really that call's OUTPUT, not a literal that happens
    to match it."""

    def _fake_msg(key: str, **_: object) -> str:
        return f"<{key}>"

    monkeypatch.setattr("app.steps.land_cover.msg", _fake_msg)

    spec = solara.reactive(
        default_spec(land_cover=CustomLandCoverSource(start_asset="a", end_asset="b"))
    )
    box, rc = solara.render(LandCoverStep(spec=spec), handle_error=False)
    assert rc is not None

    assert markdown_texts(box)[0] == "<p><land_cover.description></p>"

    source = _select(box)
    assert source.label == "<land_cover.source>"
    assert source.v_model == "<land_cover.custom>"

    start_field, end_field = find_widgets(box, ipyvuetify.TextField)
    assert start_field.label == "<land_cover.start_asset>"
    assert end_field.label == "<land_cover.end_asset>"

    slider = _slider(box)
    assert slider.label == "<land_cover.water_mask>"


@pytest.mark.parametrize(
    ("spec", "expected_extra"),
    [
        (default_spec(), []),
        (
            default_spec(land_cover=CustomLandCoverSource(start_asset="", end_asset="")),
            [
                "<p><strong>Select the start land cover asset.</strong></p>",
                "<p><strong>Select the end land cover asset.</strong></p>",
            ],
        ),
        (
            # A non-fatal problem this step owns: two different custom assets
            # with no transition matrix file fall back to the default IPCC
            # vocabulary. The only case here that exercises the non-bold
            # `else` arm of the problems loop.
            default_spec(land_cover=CustomLandCoverSource(start_asset="a", end_asset="b")),
            [
                "<p>Custom land cover assets are set without a transition matrix "
                "file, so their pixel codes are remapped through the default "
                "IPCC vocabulary.</p>"
            ],
        ),
        (
            default_spec(
                periods=replace(
                    default_spec().periods, land_cover=PeriodOverride(start=1980, end=1985)
                )
            ),
            [
                "<p><strong>The land cover period lies outside the CCI land "
                "cover record (1992-2022), so both of its years clamp to the "
                "same one and there is no transition to measure.</strong></p>",
                "<p>The land cover period starts before the CCI land cover "
                "record (1992), so the transition is measured from 1992 "
                "instead, and that is the year the chart will be labelled "
                "with.</p>",
            ],
        ),
        (
            # A fatal problem belonging to ANOTHER step (missing AOI) --
            # the case that actually distinguishes `problems_for("land_cover",
            # ...)` from `validate(...)`.
            default_spec(aoi=None),
            [],
        ),
    ],
)
def test_the_step_renders_only_its_own_text(spec, expected_extra):
    spec_r = solara.reactive(spec)
    box, rc = solara.render(LandCoverStep(spec=spec_r), handle_error=False)
    assert rc is not None
    assert markdown_texts(box) == [
        "<p>Land cover source, transitions and the water mask.</p>",
        *expected_extra,
    ]
