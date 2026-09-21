"""Soil organic carbon sub-indicator: the year loop and the transition multiplier.

Transcribed from ``component/scripts/soil_organic_carbon.py`` (legacy
``soil_organic_carbon()``, lines 6-178). Phase 1 is a transcription, not a refactor:
every node matches the legacy graph, and the legacy's weaknesses are preserved and
annotated rather than repaired. The two stock-change blocks below are near-duplicates
of each other because the legacy spells them out twice; factoring
them into one helper would read better and is deliberately NOT done, so this file
stays diffable against the legacy line by line.

Three things a reader will want to change here and must not, in phase 1:

* **The year-two-onward transition scale is 10, and it should be 100.** The
  first year pair is encoded ``lc0 * 100 + lc1`` (:50) and every later pair
  ``lc0 * 10 + lc1`` (:114). After ``TRANSLATION_MATRIX`` the class codes are
  ``{10,20,...,70}``, so scale 100 produces exactly the 49 four-digit codes of
  ``IPCC_TRANSITION_CODES`` while scale 10 produces ``110..770`` -- a set that
  shares nothing with it. ``Image.remap`` without a ``defaultValue`` MASKS
  unmatched pixels, so from the second pair onward every pixel whose land cover
  CHANGED gets masked stock-change factors, a masked ``organic_carbon_change`` and
  a masked ``soc_final``. ``:115`` is what confines the damage to changed pixels:
  unchanged ones keep the correct four-digit code from the first pair. The
  legacy's own comments show a typo rather than a decision -- ``:49`` says "1st
  two digit ... 2nd two digits", ``:112`` says "1st digit ... 2nd". It is
  preserved behind :attr:`~sdg1531.spec.Compatibility.soc_subsequent_transition_scale`
  (default 10) so the eventual repair is one argument, and
  :func:`soc_transition_code` is the ONLY place the multiplier is spelled.
* **The per-year ``for`` loop stays a python loop.** An ``ee.List.iterate`` would
  rewrite every node above it; the legacy's own commented-out sketch at ``:92-93``
  is not an invitation.
* **Both +-10 boundaries of the final ladder are open** (:169-176). At a percent
  change of exactly 10 or exactly -10 no branch fires and the pixel keeps the seed
  value 0, which the band's own comment calls nodata rather than a class. Tidying
  ``lt(10)`` into ``lte(10)`` would close a hole the published results have.

ResolvedSpec fields read here:
    soc_year_start (unclamped BY DEFAULT -- :16 passes the raw period start into
    ``calendarRange`` while :12-14 clamps only the end. The asymmetry is ``resolve``'s to
    apply, and ``resolve()`` gates it on
    :attr:`~sdg1531.spec.Compatibility.clamp_soc_start_year`, default ``False``; with
    that flag set the start is clamped like the end and this module is none the
    wiser), soc_year_end_esa, spec.climate,
    spec.compatibility.soc_subsequent_transition_scale

EXPECTED_DIVERGENCES note -- two divergences from the legacy, both in the climate
dispatch. The parity harness must carry both:

1. **No legacy counterpart.** An unrecognised ``spec.climate`` arm raises
   ``SpecError``. ``Climate`` is a closed union, so this is not reachable through
   the public API; the legacy's ``if not model.conversion_coef: ... else: ...``
   (:19-27) has no equivalent arm at all. It is the total-dispatch backstop for
   headless replay and for the parity harness.
2. **Behaviour-changing, and it changes the graph rather than raising.**
   ``soil_organic_carbon.py:19`` tests ``if not model.conversion_coef``, i.e.
   truthiness, so a coefficient of ``0.0`` took the PER-PIXEL branch there. The
   tagged union sends ``FixedClimate(coefficient=0.0)`` to the fixed branch here,
   which builds ``ee.Image(1).divide(0.0)`` instead of the IPCC climate-zone
   remap -- a different graph, silently. None of the five coefficients the UI can
   produce (parameter/ui.py:41-47: 0.80, 0.69, 0.58, 0.48, 0.64) is 0.0, so no
   scenario reachable from the legacy widget is affected; ``FixedClimate`` itself
   is unconstrained and ``validate()`` does not bound it, so the value is
   representable.
"""

from __future__ import annotations

import ee

from sdg1531.catalog import ASSETS, INT16_MIN
from sdg1531.engine._typing import as_image
from sdg1531.engine.context import ExecutionContext
from sdg1531.errors import SpecError
from sdg1531.resolve import ResolvedSpec
from sdg1531.spec import FixedClimate, PerPixelClimate
from sdg1531.tables import (
    C_CONVERSION_FACTOR,
    CLIMATE_CONVERSION_MATRIX,
    INPUT_FACTOR,
    IPCC_TRANSITION_CODES,
    MANAGEMENT_FACTOR,
    TRANSLATION_MATRIX,
)

__all__ = ["build_soil_organic_carbon", "climate_coefficient", "soc_transition_code"]

# The first year pair's multiplier (:50), named so the contrast with the loop's
# `subsequent_scale` is visible at both call sites. See the module docstring.
_FIRST_PAIR_TRANSITION_SCALE = 100


def soc_transition_code(lc0: ee.Image, lc1: ee.Image, scale: int) -> ee.Image:
    """Encode a land-cover pair as one transition code: ``lc0 * scale + lc1``.

    The ONLY place the SOC transition multiplier appears. The legacy spells it twice
    with different values -- ``multiply(100)`` for the first year pair
    (soil_organic_carbon.py:50) and ``multiply(10)`` for every later pair (:114) --
    which is the defect the module docstring describes. Which image carries the
    leading digits is as load-bearing as the scale itself: exchanging the operands
    builds an equally plausible node that decodes every transition backwards.
    """
    return as_image(lc0.multiply(scale).add(lc1))


def climate_coefficient(r: ResolvedSpec, ctx: ExecutionContext) -> ee.Image | float:
    """The IPCC climate conversion coefficient (soil_organic_carbon.py:19-27).

    Returns a per-pixel image for :class:`~sdg1531.spec.PerPixelClimate` and a plain
    float for :class:`~sdg1531.spec.FixedClimate`. Both are valid second arguments
    to ``Image.where``, which is how the legacy uses the value (:60-65).

    See the module docstring's EXPECTED_DIVERGENCES for the two ways this dispatch
    differs from the legacy truthiness test at :19.
    """
    climate = r.spec.climate
    if isinstance(climate, PerPixelClimate):
        # :20-25 -- clipped to the AOI's BOUNDING BOX, as the soc grid is at :9.
        ipcc_climate_zones = ee.Image(ASSETS["ipcc_climate_zones"]).clip(ctx.bounds)
        return as_image(
            ipcc_climate_zones.remap(
                list(CLIMATE_CONVERSION_MATRIX[0]), list(CLIMATE_CONVERSION_MATRIX[1])
            )
        )
    if isinstance(climate, FixedClimate):
        return climate.coefficient  # :27
    raise SpecError(f"unsupported climate regime: {climate!r}")


def build_soil_organic_carbon(r: ResolvedSpec, ctx: ExecutionContext) -> ee.Image:
    """Build the SOC sub-indicator (soil_organic_carbon.py:6-178).

    Returns a single ``soc`` band, uint8, carrying the byte convention
    ``1 degraded / 2 stable / 3 improved`` over a seed of 0.
    """
    soc = ee.Image(ASSETS["soc"]).clip(ctx.bounds)  # :9
    soc = soc.updateMask(soc.neq(INT16_MIN))  # :10

    soc_year_start = r.soc_year_start  # :16 -- raw unless clamp_soc_start_year
    lc_year_end = r.soc_year_end_esa  # :12-14 -- clamped to the CCI range
    subsequent_scale = r.spec.compatibility.soc_subsequent_transition_scale

    landcover = ee.ImageCollection(ASSETS["land_cover_ic"]).filter(
        ee.Filter.calendarRange(soc_year_start, lc_year_end, "year")
    )  # :15-17

    climate_conversion_coef = climate_coefficient(r, ctx)  # :19-27

    # --- the first two years, at scale 100 (:29-89) ---------------------------

    lc_time0 = (
        landcover.filter(ee.Filter.calendarRange(soc_year_start, soc_year_start, "year"))
        .first()
        .remap(list(TRANSLATION_MATRIX[0]), list(TRANSLATION_MATRIX[1]))
    )  # :31-37

    lc_time1 = (
        landcover.filter(ee.Filter.calendarRange(soc_year_start + 1, soc_year_start + 1, "year"))
        .first()
        .remap(list(TRANSLATION_MATRIX[0]), list(TRANSLATION_MATRIX[1]))
    )  # :39-47

    lc_transition = soc_transition_code(lc_time0, lc_time1, _FIRST_PAIR_TRANSITION_SCALE)  # :50

    # :53 -- years since the last transition; 1 where the pair changed, else 2.
    lc_transition_time = ee.Image(2).where(lc_time0.neq(lc_time1), 1)

    # :57-65 -- the 333 / -333 sentinels of C_CONVERSION_FACTOR are recoded with the
    # run's climate coefficient, and the NEGATIVE sentinel takes its RECIPROCAL.
    lc_transition_climate_coef_tmp = lc_transition.remap(
        list(IPCC_TRANSITION_CODES), list(C_CONVERSION_FACTOR)
    )
    lc_transition_climate_coef = lc_transition_climate_coef_tmp.where(
        lc_transition_climate_coef_tmp.eq(333), climate_conversion_coef
    ).where(
        lc_transition_climate_coef_tmp.eq(-333),
        ee.Image(1).divide(climate_conversion_coef),
    )

    lc_transition_management_factor = lc_transition.remap(
        list(IPCC_TRANSITION_CODES), list(MANAGEMENT_FACTOR)
    )  # :68-70

    lc_transition_organic_factor = lc_transition.remap(
        list(IPCC_TRANSITION_CODES), list(INPUT_FACTOR)
    )  # :73-75

    organic_carbon_change = soc.subtract(
        soc.multiply(lc_transition_climate_coef)
        .multiply(lc_transition_management_factor)
        .multiply(lc_transition_organic_factor)
    ).divide(20)  # :77-81

    soc_time1 = soc.subtract(organic_carbon_change)  # :84

    # :87 -- accumulated and never read, here as in the legacy (:155 too). Kept so
    # the parity diff stays empty; the deletion is phase 2's.
    lc_images = ee.Image(lc_time0).addBands(lc_time1)

    soc_images = ee.Image(soc).addBands(soc_time1)  # :89

    # --- every later year, at the compatibility scale (:95-157) ---------------

    for year in range(soc_year_start + 1, lc_year_end):
        lc_time0 = (
            landcover.filter(ee.Filter.calendarRange(year, year, "year"))
            .first()
            .remap(list(TRANSLATION_MATRIX[0]), list(TRANSLATION_MATRIX[1]))
        )  # :96-100

        lc_time1 = (
            landcover.filter(ee.Filter.calendarRange(year + 1, year + 1, "year"))
            .first()
            .remap(list(TRANSLATION_MATRIX[0]), list(TRANSLATION_MATRIX[1]))
        )  # :102-106

        # :108-110 -- order is load-bearing: the counter is incremented where the
        # pair is unchanged and then RESET to 1 where it changed.
        lc_transition_time = lc_transition_time.where(
            lc_time0.eq(lc_time1), lc_transition_time.add(ee.Image(1))
        ).where(lc_time0.neq(lc_time1), ee.Image(1))

        # :114 -- the wrong transition scale, preserved (see the module docstring).
        # :115 confines it to changed pixels.
        lc_transition_temp = soc_transition_code(lc_time0, lc_time1, subsequent_scale)
        lc_transition = lc_transition.where(lc_time0.neq(lc_time1), lc_transition_temp)

        # :119-127
        lc_transition_climate_coef_tmp = lc_transition.remap(
            list(IPCC_TRANSITION_CODES), list(C_CONVERSION_FACTOR)
        )
        lc_transition_climate_coef = lc_transition_climate_coef_tmp.where(
            lc_transition_climate_coef_tmp.eq(333), climate_conversion_coef
        ).where(
            lc_transition_climate_coef_tmp.eq(-333),
            ee.Image(1).divide(climate_conversion_coef),
        )

        lc_transition_management_factor = lc_transition.remap(
            list(IPCC_TRANSITION_CODES), list(MANAGEMENT_FACTOR)
        )  # :130-132

        lc_transition_organic_factor = lc_transition.remap(
            list(IPCC_TRANSITION_CODES), list(INPUT_FACTOR)
        )  # :135-137

        year_index = year - soc_year_start  # :139

        # :141-151 -- an accumulator: `organic_carbon_change` is the PREVIOUS
        # iteration's image, updated only where this year's pair changed, then
        # zeroed wherever the twenty-year transition has run out.
        organic_carbon_change = organic_carbon_change.where(
            lc_time0.neq(lc_time1),
            soc_images.select(year_index)
            .subtract(
                soc_images.select(year_index)
                .multiply(lc_transition_climate_coef)
                .multiply(lc_transition_management_factor)
                .multiply(lc_transition_organic_factor)
            )
            .divide(20),
        ).where(lc_transition_time.gt(20), 0)

        soc_final = soc_images.select(year_index).subtract(organic_carbon_change)  # :153

        lc_images = lc_images.addBands(lc_time1)  # :155 -- still never read

        soc_images = soc_images.addBands(soc_final)  # :157

    # --- percent change and the byte convention (:159-176) --------------------

    soc_percent_change = (
        soc_images.select(lc_year_end - soc_year_start)
        .subtract(soc_images.select(0))
        .divide(soc_images.select(0))
        .multiply(100)
    )  # :160-165

    # :169-176 -- 1 degraded / 2 stable / 3 improved over a seed of 0. Both +-10
    # boundaries are open; see the module docstring.
    return as_image(
        ee.Image(0)
        .where(soc_percent_change.gt(10), 3)
        .where(soc_percent_change.lt(10).And(soc_percent_change.gt(-10)), 2)
        .where(soc_percent_change.lt(-10), 1)
        .rename("soc")
        .uint8()
    )
