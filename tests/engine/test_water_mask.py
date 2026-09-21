"""build_water_mask is a four-branch table over land-cover source x water-mask arm.

Legacy: component/scripts/land_cover.py:57-81.

The point of every test here is WHICH image a branch reads and WHAT it compares it
to, because the four branches disagree about both and no shape assertion notices:
the custom-source branch tests the REMAPPED end image against the configured pixel
value, while the ESA branch tests the RAW CCI end image against a hardcoded 210
(land_cover.py:60 vs :66). So `cci_raw` and `cci_remapped` are handed in as two
DIFFERENT loadable assets, and the branch table below asserts set equality on the
asset ids that actually reached the graph. Passing the same image for both would
look right and be wrong on exactly one branch.
"""

from __future__ import annotations

import ee
import pytest

from sdg1531.engine.land_cover import build_water_mask
from sdg1531.errors import SpecError
from sdg1531.spec import (
    AssetBandMask,
    CustomLandCoverSource,
    EsaCciSource,
    JrcSeasonalityMask,
    PixelValueMask,
)
from tests.engine.conftest import make_resolved
from tests.engine.graph import (
    _call,
    _image_constant,
    _image_constants,
    _loaded_asset_ids,
    _root,
    _selected_bands,
    _string_list_arg,
    _walk,
    count_calls,
)

JRC = "JRC/GSW1_3/GlobalSurfaceWater"
RAW = "users/test/cci_raw"
REMAPPED = "users/test/cci_remapped"
WATER_ASSET = "users/test/water_asset"

# The ESA CCI water class the legacy hardcodes (land_cover.py:66) and the IPCC
# code TRANSLATION_MATRIX maps it onto (:65).
CCI_WATER_CLASS = 210
IPCC_WATER_CODE = 70

# Plain frozen dataclasses -- no ee call -- so parametrize may reference them at
# module scope. `ee` objects may not: the autouse fixture in tests/conftest.py
# runs after this module is imported.
ESA = EsaCciSource()
CUSTOM = CustomLandCoverSource(
    start_asset="users/test/custom_start", end_asset="users/test/custom_end"
)
ASSET_MASK = AssetBandMask(asset_id=WATER_ASSET, band="occurrence")


def water_for(source, mask):
    """The `water` band for one (land-cover source, water-mask arm) pair.

    `cci_raw` and `cci_remapped` are two distinguishable assets, and each carries
    the band name the legacy gives it, so a branch reading the wrong one shows up
    both as an asset id and as a rename on its operand spine.
    """
    r = make_resolved(land_cover=source, water_mask=mask)
    return build_water_mask(
        r,
        cci_raw=ee.Image(RAW).rename("landcover_end"),
        cci_remapped=ee.Image(REMAPPED).rename("end"),
    )


# --- graph helpers ------------------------------------------------------------

_COMPARISONS = (
    "Image.eq",
    "Image.neq",
    "Image.gt",
    "Image.gte",
    "Image.lt",
    "Image.lte",
)


def comparisons(obj):
    """`{(operator, right-hand constant)}` for every scalar comparison in the graph.

    Records the OPERATOR alongside the threshold. A helper that returned only the
    constant would let `.gte(6)` -> `.gt(6)` ship green, which moves the JRC mask
    off every pixel whose seasonality is exactly the threshold.
    """
    deref, graph, root = _root(obj)
    found = set()
    for node in _walk(root, deref, graph):
        call = _call(node)
        if call is None or call.get("functionName") not in _COMPARISONS:
            continue
        right = _image_constant(deref(call.get("arguments", {}).get("image2", {})), deref)
        found.add((call["functionName"], right))
    return found


def outer_rename(obj):
    """The band names of the OUTERMOST node, which must be an `Image.rename`.

    Not `_renamed_bands`: the `cci_raw` stand-in is itself renamed, so the set of
    every rename in the graph cannot say what the RESULT is called.
    """
    deref, _graph, root = _root(obj)
    call = _call(root)
    if call is None or call.get("functionName") != "Image.rename":
        raise AssertionError(
            f"the graph head is {call.get('functionName') if call else type(root).__name__!r}, "
            "not Image.rename"
        )
    return _string_list_arg(deref(call["arguments"]["names"]), deref)


# --- the branch table ---------------------------------------------------------

BRANCHES = [
    # land_cover.py:65-66 -- the ESA branch reads the RAW image.
    ("branch 2: esa + pixel 70", ESA, PixelValueMask(IPCC_WATER_CODE), {RAW}),
    # :67-73
    ("branch 3: esa + asset band", ESA, ASSET_MASK, {WATER_ASSET}),
    # :74-81
    ("branch 4: esa + jrc", ESA, JrcSeasonalityMask(6), {JRC}),
    # :58-63 -- a custom source reads the REMAPPED image, at ANY pixel value, so
    # custom+70 must NOT fall through to branch 2.
    ("branch 1: custom + pixel 70", CUSTOM, PixelValueMask(IPCC_WATER_CODE), {REMAPPED}),
    ("branch 1: custom + pixel 33", CUSTOM, PixelValueMask(33), {REMAPPED}),
    # The dropped `water_mask_pixel > 9` guard (module note, divergence 4). The
    # legacy sent this to branch 4; the union sends it to branch 1. Pinned so a
    # future repair -- reinstating the guard, or bounding PixelValueMask.value --
    # cannot land silently.
    ("branch 1: custom + pixel 5", CUSTOM, PixelValueMask(5), {REMAPPED}),
    ("branch 3: custom + asset band", CUSTOM, ASSET_MASK, {WATER_ASSET}),
    ("branch 4: custom + jrc", CUSTOM, JrcSeasonalityMask(6), {JRC}),
]


@pytest.mark.parametrize(
    ("source", "mask", "expected_assets"),
    [pytest.param(*case[1:], id=case[0]) for case in BRANCHES],
)
def test_each_branch_reads_exactly_one_image(source, mask, expected_assets):
    """Set equality, not membership: it fails both when a branch reads the wrong
    image and when it reads an extra one it should have left alone."""
    assert _loaded_asset_ids(water_for(source, mask)) == expected_assets


@pytest.mark.parametrize(
    ("source", "mask", "_assets"),
    [pytest.param(*case[1:], id=case[0]) for case in BRANCHES],
)
def test_every_branch_names_its_result_water(source, mask, _assets):
    assert outer_rename(water_for(source, mask)) == ["water"]


@pytest.mark.parametrize(
    ("source", "mask", "_assets"),
    [pytest.param(*case[1:], id=case[0]) for case in BRANCHES],
)
def test_every_branch_self_masks_exactly_once(source, mask, _assets):
    """One `.selfMask()` per branch (land_cover.py:61, :66, :71, :79) and none in
    the stand-ins, so the distinct-node count is exactly 1 on every branch."""
    assert count_calls(water_for(source, mask), "Image.selfMask") == 1


def test_the_esa_pixel_branch_tests_the_raw_image_against_a_hardcoded_210():
    """land_cover.py:65-66. The configured pixel value (70) reaches NOTHING: the
    legacy uses it only as the branch condition and compares against 210."""
    water = water_for(ESA, PixelValueMask(IPCC_WATER_CODE))

    assert comparisons(water) == {("Image.eq", CCI_WATER_CLASS)}
    assert IPCC_WATER_CODE not in _image_constants(water)


@pytest.mark.parametrize("pixel", [IPCC_WATER_CODE, 33, 5])
def test_the_custom_pixel_branch_tests_the_remapped_image_against_the_configured_value(pixel):
    """land_cover.py:58-63, and the precedence that goes with it: a custom source
    takes this branch even at pixel 70, so 210 never appears.

    Pixel 5 is the dropped `water_mask_pixel > 9` guard (module note, divergence
    4): the legacy compared it and fell through to the JRC branch, so `Image.eq`
    against 5 is the divergence made visible."""
    water = water_for(CUSTOM, PixelValueMask(pixel))

    assert comparisons(water) == {("Image.eq", pixel)}
    assert CCI_WATER_CLASS not in _image_constants(water)


@pytest.mark.parametrize("threshold", [6, 8])
def test_the_jrc_branch_keeps_seasonality_at_or_above_the_threshold(threshold):
    """land_cover.py:74-81. Two thresholds, so the value is read rather than
    hardcoded, and the operator is pinned with it: `.gte` -> `.gt` would drop
    every pixel sitting exactly on the threshold."""
    water = water_for(ESA, JrcSeasonalityMask(threshold))

    assert comparisons(water) == {("Image.gte", threshold)}
    assert _selected_bands(water) == {"seasonality"}


def test_the_asset_branch_selects_the_named_band_and_compares_nothing():
    """land_cover.py:67-73 -- `.select(band).selfMask()`, with no threshold at all."""
    water = water_for(ESA, AssetBandMask(asset_id=WATER_ASSET, band="occurrence"))

    assert _selected_bands(water) == {"occurrence"}
    assert comparisons(water) == set()


# --- the port-only raises (module docstring EXPECTED_DIVERGENCES 1 and 2) ------


@pytest.mark.parametrize("pixel", [33, 10, 71])
def test_a_pixel_value_mask_over_esa_cci_rejects_a_non_water_code(pixel):
    """land_cover.py:65 tests `== 70` exactly, so every other value fell silently
    through to the JRC branch and built a mask the user never asked for. A
    non-exhaustive dispatch must now raise."""
    with pytest.raises(SpecError, match="IPCC water code"):
        water_for(ESA, PixelValueMask(pixel))


def test_an_unset_water_mask_is_rejected():
    """`RunSpec.water_mask` is `WaterMaskSpec | None`. The legacy else-branch
    swallowed the unset case and reached for `model.seasonality`; here there is no
    threshold to reach for."""
    with pytest.raises(SpecError, match="unsupported water mask"):
        water_for(ESA, None)


def test_an_unrecognised_land_cover_source_is_rejected():
    """The OTHER half of land_cover.py's note 3, which claims an unrecognised
    `spec.land_cover` *or* `spec.water_mask` arm raises.

    Only the water-mask half was pinned, and the parity register cited the
    water-mask test for both -- so `land_cover.py:151`, the source arm of the
    pixel-value branch, was reached by nothing in the suite. `LandCoverSource` is a
    closed union, so no `RunSpec` gets here; a stand-in arm is the only way in, and
    an unreachable branch that raises the wrong thing is still worth knowing about.
    """

    class UnknownSource:
        pass

    with pytest.raises(SpecError, match="unsupported land cover source"):
        water_for(UnknownSource(), PixelValueMask(70))
