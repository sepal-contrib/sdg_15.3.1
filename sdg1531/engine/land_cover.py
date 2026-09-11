"""Land-cover sub-indicator: the water mask and the degradation stack.

Transcribed from ``component/scripts/land_cover.py`` (legacy ``land_cover()``,
lines 6-111). Phase 1 is a transcription, not a refactor: every node matches the
legacy graph, and the legacy's weaknesses are preserved and annotated rather than
repaired.

Two of those weaknesses are worth naming here, because both look like bugs to a
reader who has not seen the legacy:

* **The four water branches do not read the same image.** The custom-source
  branch tests the REMAPPED end image against the configured pixel value, while
  the ESA branch tests the RAW CCI end image against a hardcoded 210 -- not
  against the configured value (land_cover.py:60 vs :66). That is why
  :func:`build_water_mask` takes both images: handing it the same image twice
  would be wrong on exactly one branch and no shape assertion would notice.
  Branch order matters too -- a custom source with any pixel value takes the
  remapped branch, so custom+70 and ESA+70 build different graphs.
* **``landcover_start`` / ``landcover_end`` are built unconditionally**
  (land_cover.py:17-37), even when a custom source leaves them unused. An
  unreferenced ``ee`` object is never serialized, so with a custom source the
  CCI collection does not appear in the graph at all. The construction is kept
  where the legacy puts it, as is the ordering: the water mask is built BEFORE
  the transition image.

ResolvedSpec fields read here:
    spec.land_cover, spec.water_mask, lc_year_start_esa, lc_year_end_esa,
    lc_class_combinations, trans_matrix_flatten

EXPECTED_DIVERGENCES note -- four divergences from the legacy, spread over four
``raise`` statements and one dropped guard. The parity harness must carry all
four:

1. **No legacy counterpart.** A :class:`~sdg1531.spec.PixelValueMask` over
   :class:`~sdg1531.spec.EsaCciSource` whose value is not the IPCC water code 70
   raises ``SpecError``. land_cover.py:65 tests ``water_mask_pixel == 70``
   exactly, so any other value falls silently through to the JRC seasonality
   branch and builds a mask the user never asked for.
2. **Behaviour-changing, not counterpart-free.** An unset ``spec.water_mask``
   (the field is ``WaterMaskSpec | None``) raises ``SpecError`` where the legacy
   else-branch (land_cover.py:74-81) caught the same case and built a JRC mask
   from ``model.seasonality``. There is no threshold here to fall back on.
   ``sdg1531.validate`` now reports an unset mask as a fatal ``Problem``, so this
   is no longer reachable through the public API; the raise stays as the
   total-dispatch backstop for headless replay and for the parity harness, neither
   of which is obliged to call ``validate()``.
3. **No legacy counterpart.** An unrecognised ``spec.land_cover`` or
   ``spec.water_mask`` arm raises ``SpecError``. Both are closed unions, so
   neither is reachable through the public API; the legacy if/elif/else has no
   equivalent arm at all.
4. **Behaviour-changing, and it changes the graph rather than raising.** Legacy
   branch 1 is guarded by ``model.water_mask_pixel > 9`` (land_cover.py:58)
   against a trait that defaults to ``None``, which would raise ``TypeError`` on
   the comparison. The tagged union carries that decision instead, so the guard
   is gone. ``PixelValueMask.value`` is an unconstrained ``int`` and
   ``validate()`` does not bound it, so a custom source with a value of 9 or less
   is representable and takes branch 1 here where the legacy took branch 4 -- a
   different graph, silently. Pinned by the ``custom + pixel 5`` row of
   ``tests/engine/test_water_mask.py``'s branch table so a future repair cannot
   land unnoticed. Every IPCC code the default scheme emits is 10 or above, so
   the two agree on every value that scheme can produce; the union can hold more
   than the scheme emits.
"""

from __future__ import annotations

from dataclasses import dataclass

import ee

from sdg1531.catalog import ASSETS, INT16_MIN
from sdg1531.engine._typing import as_image
from sdg1531.engine.context import ExecutionContext
from sdg1531.errors import SpecError
from sdg1531.resolve import ResolvedSpec
from sdg1531.spec import (
    AssetBandMask,
    CustomLandCoverSource,
    EsaCciSource,
    JrcSeasonalityMask,
    PixelValueMask,
)
from sdg1531.tables import TRANSLATION_MATRIX

__all__ = ["LandCoverMaps", "build_land_cover", "build_water_mask"]

# The two codes the legacy water branches hard-code (land_cover.py:60, :66).
# 210 is the ESA CCI water class; 70 is the IPCC water code TRANSLATION_MATRIX
# maps it onto.
_CCI_WATER_CLASS = 210
_IPCC_WATER_CODE = 70


@dataclass(frozen=True, slots=True)
class LandCoverMaps:
    """The land-cover sub-indicator stack.

    ``stack`` carries five bands, in this order (land_cover.py:104-109):
    ``degradation``, ``transition``, ``start``, ``end``, ``water``.
    """

    stack: ee.Image

    @property
    def degradation(self) -> ee.Image:
        return as_image(self.stack.select("degradation"))

    @property
    def transition(self) -> ee.Image:
        return as_image(self.stack.select("transition"))

    @property
    def water(self) -> ee.Image:
        return as_image(self.stack.select("water"))


def build_water_mask(
    r: ResolvedSpec,
    *,
    cci_raw: ee.Image,
    cci_remapped: ee.Image,
) -> ee.Image:
    """Build the ``water`` band (land_cover.py:57-81).

    Reads ``r.spec.water_mask`` and ``r.spec.land_cover``. Takes no
    :class:`ExecutionContext`: none of the four branches clips, and the legacy
    passes no geometry into any of them (land_cover.py:58-81).

    Needs both CCI images because the branches disagree about which one they test:
    the custom-source branch tests the *remapped* end image, the ESA branch tests
    the *raw* one (land_cover.py:60 vs :66).
    """
    water_mask = r.spec.water_mask
    source = r.spec.land_cover

    if isinstance(water_mask, PixelValueMask):
        if isinstance(source, CustomLandCoverSource):
            # :58-63. The `int()` is the legacy's own coercion of a trait that
            # was not necessarily an int; kept so a later widening of
            # PixelValueMask.value cannot change the node under us.
            return as_image(cci_remapped.eq(int(water_mask.value)).selfMask().rename("water"))
        if isinstance(source, EsaCciSource):
            if water_mask.value == _IPCC_WATER_CODE:
                # :65-66 -- the RAW image and a hardcoded 210, NOT the configured
                # value. See the module docstring.
                return as_image(cci_raw.eq(_CCI_WATER_CLASS).selfMask().rename("water"))
            raise SpecError(
                "a pixel-value water mask over ESA CCI land cover is only defined "
                f"for the IPCC water code {_IPCC_WATER_CODE}, got {water_mask.value}"
            )
        raise SpecError(f"unsupported land cover source: {source!r}")

    if isinstance(water_mask, AssetBandMask):
        # :67-73
        return as_image(
            ee.Image(water_mask.asset_id).select(water_mask.band).selfMask().rename("water")
        )

    if isinstance(water_mask, JrcSeasonalityMask):
        # :74-81
        return as_image(
            ee.Image(ASSETS["jrc_water"])
            .select("seasonality")
            .gte(int(water_mask.threshold))
            .selfMask()
            .rename("water")
        )

    raise SpecError(f"unsupported water mask: {water_mask!r}")


def build_land_cover(r: ResolvedSpec, ctx: ExecutionContext) -> LandCoverMaps:
    """Build the land-cover sub-indicator stack (land_cover.py:6-111).

    Reads ``r.lc_year_start_esa``, ``r.lc_year_end_esa``, ``r.lc_class_combinations``,
    ``r.trans_matrix_flatten``, ``r.spec.land_cover`` and (through
    :func:`build_water_mask`) ``r.spec.water_mask``.
    """
    geom = ctx.bounds  # :10

    landcover = ee.ImageCollection(ASSETS["land_cover_ic"])  # :13

    # :17-37 -- built unconditionally, dead under a custom source. See the
    # module docstring.
    landcover_start = (
        landcover.filter(ee.Filter.calendarRange(r.lc_year_start_esa, r.lc_year_start_esa, "year"))
        .first()
        .clip(geom)
        .rename("landcover_start")
    )

    landcover_end = (
        landcover.filter(ee.Filter.calendarRange(r.lc_year_end_esa, r.lc_year_end_esa, "year"))
        .first()
        .clip(geom)
        .rename("landcover_end")
    )

    source = r.spec.land_cover
    if isinstance(source, CustomLandCoverSource):
        # :40-43 -- user assets are used RAW. They are not put through
        # TRANSLATION_MATRIX, so their pixel codes must already be the codes the
        # scheme's combination list expects.
        landcover_start_remapped = ee.Image(source.start_asset).clip(geom).rename("start")
        landcover_end_remapped = ee.Image(source.end_asset).clip(geom).rename("end")
    elif isinstance(source, EsaCciSource):
        landcover_start_remapped = landcover_start.remap(
            list(TRANSLATION_MATRIX[0]), list(TRANSLATION_MATRIX[1])
        ).rename("start")  # :48-50
        landcover_end_remapped = landcover_end.remap(
            list(TRANSLATION_MATRIX[0]), list(TRANSLATION_MATRIX[1])
        ).rename("end")  # :53-55
    else:
        raise SpecError(f"unsupported land cover source: {source!r}")

    # :57-81 -- built here, before the transition image, as in the legacy order.
    water_body = build_water_mask(r, cci_raw=landcover_end, cci_remapped=landcover_end_remapped)

    # :84-88 -- the START map carries the leading two digits.
    landcover_transition = (
        landcover_start_remapped.multiply(100).add(landcover_end_remapped).rename("transition")
    )

    # :92-94
    landcover_degredation = landcover_transition.remap(
        list(r.lc_class_combinations), list(r.trans_matrix_flatten)
    )

    # :98-102 -- byte convention 1 degraded / 2 stable / 3 improved. The
    # INT16_MIN -> 0 entry is unreachable: the remap above has no defaultValue,
    # so unmatched pixels are masked rather than set to INT16_MIN. Transcribed as
    # found rather than pruned, so the graph stays byte-identical.
    landcover_degredation = (
        landcover_degredation.remap([1, 0, -1, INT16_MIN], [3, 2, 1, 0])
        .uint16()
        .rename("degradation")
    )

    # :104-109
    stack = (
        landcover_degredation.addBands(landcover_transition.uint16())
        .addBands(landcover_start_remapped.uint16())
        .addBands(landcover_end_remapped.uint16())
        .addBands(water_body.uint16())
    )

    return LandCoverMaps(stack=as_image(stack))
