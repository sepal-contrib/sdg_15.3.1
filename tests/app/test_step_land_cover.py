"""Land cover source, transition matrix, water mask, land-cover period."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

import ipyvuetify
import pytest
import solara

from app.message import msg
from app.state import problems_for
from app.steps.land_cover import LandCoverStep, _scheme_for_pixel_check
from sdg1531.resolve import resolve
from sdg1531.scheme import LandCoverScheme, TransitionMatrix
from sdg1531.spec import (
    AssetBandMask,
    CustomLandCoverSource,
    EsaCciSource,
    JrcSeasonalityMask,
    PeriodOverride,
    PixelValueMask,
)
from tests.app.render_helpers import find_widgets, markdown_texts
from tests.spec_factory import default_spec


class StubGee:
    """Enough of ``GEEInterface`` for the custom arm's mount-time asset
    listing (``get_folder_async``/``get_assets_async``), for the per-selection
    type check a real pick runs (``get_asset_async``), and for this step's own
    pixel-value pre-flight (``get_info_async``). ``pixel_responses`` is
    consumed in call order, one entry per ``fetch_distinct_pixel_values``
    call -- start asset first, then end asset, mirroring ``FakeFetcher`` in
    ``tests/helpers_stats.py``.
    """

    def __init__(self, pixel_responses: list[Any] | None = None) -> None:
        self._pixel_responses = list(pixel_responses or [])

    async def get_folder_async(self) -> str:
        return "users/stub"

    async def get_assets_async(self, folder: str) -> list[dict[str, str]]:
        return [
            {"id": "users/x/new-start", "type": "IMAGE"},
            {"id": "users/x/new-end", "type": "IMAGE"},
        ]

    async def get_asset_async(self, asset_id: str) -> dict[str, str]:
        return {"type": "IMAGE"}

    async def get_info_async(self, ee_object: Any = None, tag: Any = None) -> Any:
        return self._pixel_responses.pop(0) if self._pixel_responses else []


async def _wait_for(predicate: Any, timeout: float = 2.0) -> bool:
    """Give a scheduled ``use_task`` coroutine a chance to run on the live loop."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            return False
        await asyncio.sleep(0.01)
    return True


def _select(box: object) -> object:
    selects = find_widgets(box, ipyvuetify.Select)
    assert len(selects) == 1
    return selects[0]


def _slider(box: object) -> object:
    sliders = find_widgets(box, ipyvuetify.Slider)
    assert len(sliders) == 1
    return sliders[0]


def _render(spec: solara.Reactive[Any], gee_interface: Any = None) -> tuple[object, object]:
    """Render on a running loop -- the custom arm's picker schedules its own
    asset-listing task at mount, which needs one even when a test never
    touches the picker itself."""

    async def main() -> tuple[object, object]:
        return solara.render(
            LandCoverStep(spec=spec, gee_interface=gee_interface), handle_error=False
        )

    return asyncio.run(main())


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

    # No asset pickers while ESA CCI is selected.
    assert find_widgets(box, ipyvuetify.Combobox) == []

    slider = _slider(box)
    assert slider.label == msg("land_cover.water_mask")
    assert slider.min == 1
    assert slider.max == 12
    assert slider.v_model == 6


def test_the_slider_reads_the_spec_s_own_threshold_not_a_constant():
    """``default_spec()``'s own threshold (6) happens to collide with what an
    earlier version of this step hardcoded as a display fallback, so that
    fixture alone cannot tell "reads the spec" from "always shows 6" apart.
    A second, distinct value closes that gap: replacing the read with any
    single constant cannot satisfy both this and the test above at once."""
    spec = solara.reactive(default_spec(water_mask=JrcSeasonalityMask(threshold=11)))
    box, rc = solara.render(LandCoverStep(spec=spec), handle_error=False)
    assert rc is not None
    assert _slider(box).v_model == 11


def test_the_custom_source_shows_asset_pickers_with_their_current_values():
    spec = solara.reactive(
        default_spec(
            land_cover=CustomLandCoverSource(start_asset="users/x/start", end_asset="users/x/end")
        )
    )
    box, rc = _render(spec, gee_interface=StubGee())
    assert rc is not None

    source = _select(box)
    assert source.v_model == msg("land_cover.custom")

    start_picker, end_picker = find_widgets(box, ipyvuetify.Combobox)
    assert start_picker.v_model == "users/x/start"
    assert end_picker.v_model == "users/x/end"


@pytest.mark.parametrize(
    "other_mask", [PixelValueMask(value=5), AssetBandMask(asset_id="x", band="y")]
)
def test_a_non_jrc_water_mask_shows_an_honest_note_instead_of_a_fabricated_threshold(other_mask):
    """``water_mask`` is a union; two of its arms (``PixelValueMask``,
    ``AssetBandMask``) have no ``.threshold`` at all -- and, more to the
    point, no JRC seasonality threshold really exists to show for either.
    Showing a slider anyway (fixed at some fallback number) would let a
    single accidental nudge silently discard the configured arm; the note
    is what stands in for a threshold this control cannot represent."""
    spec = solara.reactive(default_spec(water_mask=other_mask))
    box, rc = solara.render(LandCoverStep(spec=spec), handle_error=False)
    assert rc is not None
    assert find_widgets(box, ipyvuetify.Slider) == []
    assert spec.value.water_mask == other_mask  # untouched
    assert f"<p>{msg('land_cover.water_mask_other_arm')}</p>" in markdown_texts(box)


def test_an_unset_water_mask_is_seeded_to_the_domain_default():
    """``water_mask=None`` is ``missing_water_mask`` (fatal) -- genuinely
    unset, unlike the other two arms above, so this is the one case the step
    may commit a default for, mirroring productivity.py's ``_seed_threshold``.
    Seeded to ``RunSpec.water_mask``'s own default (8), not the unexplained 6
    an earlier version of this step hardcoded as a display-only fallback."""
    spec = solara.reactive(default_spec(water_mask=None))
    box, rc = solara.render(LandCoverStep(spec=spec), handle_error=False)
    assert rc is not None
    assert spec.value.water_mask == JrcSeasonalityMask(threshold=8)
    assert _slider(box).v_model == 8


def test_changing_the_source_to_custom_updates_only_land_cover():
    spec = solara.reactive(default_spec())
    before = spec.value

    async def main() -> None:
        box, rc = solara.render(
            LandCoverStep(spec=spec, gee_interface=StubGee()), handle_error=False
        )
        assert rc is not None
        _select(box).v_model = msg("land_cover.custom")

    asyncio.run(main())

    assert spec.value.land_cover == CustomLandCoverSource(start_asset="", end_asset="")
    assert spec.value.evolve(land_cover=before.land_cover) == before


def test_changing_the_source_back_to_esa_updates_only_land_cover():
    spec = solara.reactive(
        default_spec(land_cover=CustomLandCoverSource(start_asset="a", end_asset="b"))
    )
    before = spec.value

    async def main() -> None:
        box, rc = solara.render(
            LandCoverStep(spec=spec, gee_interface=StubGee()), handle_error=False
        )
        assert rc is not None
        _select(box).v_model = msg("land_cover.esa")

    asyncio.run(main())

    assert spec.value.land_cover == EsaCciSource()
    assert spec.value.evolve(land_cover=before.land_cover) == before


def test_choosing_the_start_asset_writes_only_that_field():
    # water_mask is deliberately NOT default_spec()'s own JrcSeasonalityMask(6):
    # a handler that also (wrongly) resets water_mask to the domain default
    # would otherwise be a no-op against it and this test would not notice.
    spec = solara.reactive(
        default_spec(
            land_cover=CustomLandCoverSource(start_asset="a", end_asset="b"),
            water_mask=JrcSeasonalityMask(threshold=9),
        )
    )
    before = spec.value

    async def main() -> None:
        box, rc = solara.render(
            LandCoverStep(spec=spec, gee_interface=StubGee()), handle_error=False
        )
        assert rc is not None
        start_picker, _end_picker = find_widgets(box, ipyvuetify.Combobox)

        start_picker.v_model = "users/x/new-start"

        assert await _wait_for(lambda: spec.value.land_cover.start_asset == "users/x/new-start"), (
            "the picker never published the chosen asset"
        )

    asyncio.run(main())

    assert spec.value.land_cover == CustomLandCoverSource(
        start_asset="users/x/new-start", end_asset="b"
    )
    assert spec.value.evolve(land_cover=before.land_cover) == before


def test_choosing_the_end_asset_writes_only_that_field():
    spec = solara.reactive(
        default_spec(
            land_cover=CustomLandCoverSource(start_asset="a", end_asset="b"),
            water_mask=JrcSeasonalityMask(threshold=9),
        )
    )
    before = spec.value

    async def main() -> None:
        box, rc = solara.render(
            LandCoverStep(spec=spec, gee_interface=StubGee()), handle_error=False
        )
        assert rc is not None
        _start_picker, end_picker = find_widgets(box, ipyvuetify.Combobox)

        end_picker.v_model = "users/x/new-end"

        assert await _wait_for(lambda: spec.value.land_cover.end_asset == "users/x/new-end"), (
            "the picker never published the chosen asset"
        )

    asyncio.run(main())

    assert spec.value.land_cover == CustomLandCoverSource(
        start_asset="a", end_asset="users/x/new-end"
    )
    assert spec.value.evolve(land_cover=before.land_cover) == before


def test_choosing_either_asset_preserves_an_existing_scheme():
    """``dataclasses.replace(custom_source, ...)`` is what makes ``scheme``
    survive an edit -- rebuilding a fresh ``CustomLandCoverSource(start_asset=
    ..., end_asset=...)`` instead would silently drop it back to ``None``,
    downgrading a spec carrying a real transition-matrix vocabulary to the
    non-fatal ``half_custom_land_cover`` (remapped through the default IPCC
    one instead)."""
    scheme = LandCoverScheme.default()
    spec = solara.reactive(
        default_spec(
            land_cover=CustomLandCoverSource(start_asset="a", end_asset="b", scheme=scheme),
            water_mask=JrcSeasonalityMask(threshold=9),
        )
    )

    async def main() -> None:
        box, rc = solara.render(
            LandCoverStep(spec=spec, gee_interface=StubGee()), handle_error=False
        )
        assert rc is not None
        start_picker, end_picker = find_widgets(box, ipyvuetify.Combobox)

        start_picker.v_model = "users/x/new-start"
        assert await _wait_for(lambda: spec.value.land_cover.start_asset == "users/x/new-start")
        assert spec.value.land_cover.scheme == scheme

        end_picker.v_model = "users/x/new-end"
        assert await _wait_for(lambda: spec.value.land_cover.end_asset == "users/x/new-end")

    asyncio.run(main())

    assert spec.value.land_cover == CustomLandCoverSource(
        start_asset="users/x/new-start", end_asset="users/x/new-end", scheme=scheme
    )


def test_the_pixel_check_scheme_fallback_matches_resolve():
    """``_scheme_for_pixel_check`` re-derives ``sdg1531.resolve._scheme()``'s
    own fallback locally (that function is private, and ``resolve()`` needs a
    fully populated spec) -- so nothing enforces the two staying in sync
    except this test. A half-custom source (both assets set, ``scheme=None``)
    is exactly the case where the two could disagree: this step falls back to
    the default vocabulary, carrying the run's own (possibly edited)
    transition matrix, the same way the domain's own resolution does. The
    matrix is deliberately NOT ``TransitionMatrix.default()`` -- a fallback
    that silently ignored ``spec.transition_matrix`` and always returned the
    stock default would satisfy the assertion anyway if the two happened to
    already match."""
    edited_matrix = TransitionMatrix.default().with_cell(0, 0, 5)
    spec = default_spec(
        land_cover=CustomLandCoverSource(start_asset="a", end_asset="b", scheme=None),
        transition_matrix=edited_matrix,
    )
    assert _scheme_for_pixel_check(spec.land_cover, spec) == resolve(spec).scheme


def test_choosing_both_assets_reports_a_pixel_mismatch_as_a_notification(monkeypatch):
    """``validate()`` cannot run this check itself -- it needs a GEE round
    trip -- so a custom asset outside the classification is reported through
    a notification instead of a ``Problem`` in ``problems_for``. 99 is
    outside ``DEFAULT_LC_CODES`` (10-70), so the end asset's subset check
    fails; the start asset's values are all in range, so it stays quiet."""
    errors: list[str] = []

    class _FakeNotifier:
        def error(self, message: str) -> None:
            errors.append(message)

    monkeypatch.setattr("app.steps.land_cover.use_notifications", lambda: _FakeNotifier())

    spec = solara.reactive(
        default_spec(land_cover=CustomLandCoverSource(start_asset="", end_asset=""))
    )
    gee = StubGee(pixel_responses=[["10", "20"], ["99"]])

    async def main() -> None:
        box, rc = solara.render(LandCoverStep(spec=spec, gee_interface=gee), handle_error=False)
        assert rc is not None
        start_picker, end_picker = find_widgets(box, ipyvuetify.Combobox)

        start_picker.v_model = "users/x/new-start"
        assert await _wait_for(lambda: spec.value.land_cover.start_asset == "users/x/new-start")

        end_picker.v_model = "users/x/new-end"
        assert await _wait_for(lambda: spec.value.land_cover.end_asset == "users/x/new-end")

        assert await _wait_for(lambda: errors), "the pixel-value check never ran"

    asyncio.run(main())

    assert errors == [
        "The asset contains pixel values that the transition matrix does not define: [99]."
    ]


def test_changing_the_water_mask_threshold_updates_only_water_mask():
    # land_cover is a CustomLandCoverSource here, not default_spec()'s own
    # EsaCciSource() -- a handler that also (wrongly) resets land_cover back
    # to EsaCciSource() would be a no-op against the default and pass anyway.
    spec = solara.reactive(
        default_spec(land_cover=CustomLandCoverSource(start_asset="a", end_asset="b"))
    )
    before = spec.value

    async def main() -> None:
        box, rc = solara.render(
            LandCoverStep(spec=spec, gee_interface=StubGee()), handle_error=False
        )
        assert rc is not None
        _slider(box).v_model = 9

    asyncio.run(main())

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
    box, rc = _render(spec, gee_interface=StubGee())
    assert rc is not None

    texts = markdown_texts(box)
    assert texts[0] == "<p><land_cover.description></p>"
    # AssetSelectComponent's own label is pysepal's, not this step's -- the
    # picker gets its label from the catalogue via a caption above it instead.
    assert "<p><land_cover.start_asset></p>" in texts
    assert "<p><land_cover.end_asset></p>" in texts

    source = _select(box)
    assert source.label == "<land_cover.source>"
    assert source.v_model == "<land_cover.custom>"

    slider = _slider(box)
    assert slider.label == "<land_cover.water_mask>"


def test_the_other_arm_note_routes_through_msg(monkeypatch):
    def _fake_msg(key: str, **_: object) -> str:
        return f"<{key}>"

    monkeypatch.setattr("app.steps.land_cover.msg", _fake_msg)

    spec = solara.reactive(default_spec(water_mask=PixelValueMask(value=5)))
    box, rc = solara.render(LandCoverStep(spec=spec), handle_error=False)
    assert rc is not None
    assert "<p><land_cover.water_mask_other_arm></p>" in markdown_texts(box)


@pytest.mark.parametrize(
    ("spec", "expected_extra"),
    [
        (default_spec(), []),
        (
            default_spec(land_cover=CustomLandCoverSource(start_asset="", end_asset="")),
            [
                "<p>Start land cover asset</p>",
                "<p>End land cover asset</p>",
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
                "<p>Start land cover asset</p>",
                "<p>End land cover asset</p>",
                "<p>Custom land cover assets are set without a transition matrix "
                "file, so their pixel codes are remapped through the default "
                "IPCC vocabulary.</p>",
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
    box, rc = _render(spec_r, gee_interface=StubGee())
    assert rc is not None
    assert markdown_texts(box) == [
        "<p>Land cover source and the water mask.</p>",
        *expected_extra,
    ]
