"""The 15.3.1 indicator and the seven-layer seam.

Transcribed from ``component/scripts/run_15_3_1.py`` -- ``indicator_15_3_1()``
(:373-411) and ``compute_indicator_maps()`` (:164-204). Phase 1 is a
transcription, not a refactor (spec D9): the 30 ``.where()`` rules and the
terminal ``.where(water, 0).uint8()`` reach ``ee`` in the legacy's own order, and
the legacy's weaknesses are preserved and annotated rather than repaired.

One of those weaknesses is worth naming here, because the port's shape is what
removes it. ``run_15_3_1.py:374-375`` reads ``water`` off the land-cover image and
only THEN rebinds ``landcover`` to ``landcover.select("degradation")``::

    water = landcover.select("water")
    landcover = landcover.select("degradation")

Swap those two lines into "logical" order and the ``water`` select runs against an
image that no longer carries that band -- and ``ee`` is lazy enough to build it
anyway, failing only on a live evaluation. :func:`build_indicator` takes a
:class:`~sdg1531.engine.land_cover.LandCoverMaps` and reads BOTH bands off its
stack, so there is no rebinding left to get wrong; threading a pre-selected image
in would put the hazard straight back.

:meth:`IndicatorMaps.layers` replaces ``indicator_n_category_label``
(run_15_3_1.py:425-450). It is the single seam -- map layers, export sources and
the statistics layer picker all iterate it -- and there is deliberately no second
``export_layers()``.

ResolvedSpec fields read here: none directly. :func:`build_indicator_maps` threads
``r`` into the sub-indicator builders and keeps it on
:attr:`IndicatorMaps.resolved`, because the statistics layer decodes class codes
off the run's own vocabulary.

EXPECTED_DIVERGENCES note -- three divergences from the legacy. Task 17's parity
harness must carry all three:

1. **Behaviour-changing, and CORPUS-WIDE rather than per-scenario.**
   :func:`build_indicator` ends ``.rename("indicator_15_3_1")``, where
   ``run_15_3_1.py:411`` renames nothing at all, so the legacy band is literally
   called ``constant`` (spec §7). Every scenario's indicator layer carries the
   same one extra ``Image.rename`` node, so the harness entry belongs on the
   corpus and not on any single scenario. With the rename put back the two graphs
   are byte-identical; ``tests/engine/test_indicator.py`` re-derives that against
   a verbatim copy of the legacy chain rather than asserting it.
2. **Behaviour-changing.** :func:`build_indicator_maps` drops
   ``run_15_3_1.py:165-167``'s ``if not (model.start < model.end): raise``. That
   check now belongs to :func:`sdg1531.validate.validate` (validate.py:61-70,
   which cites the same legacy lines) and the caller runs it before building
   anything, so a caller that skips ``validate()`` gets a graph where the legacy
   raised.
3. **Behaviour-changing.** :meth:`IndicatorMaps.layers` is a total mapping over
   the seven :class:`~sdg1531.enums.IndicatorLayer` members, where
   ``indicator_n_category_label``'s seven-branch ``if``/``elif`` chain
   (run_15_3_1.py:427-448) had no ``else`` and left both of its locals unbound for
   an unrecognised name -- an ``UnboundLocalError`` at its own ``return``. The
   trend and state entries also change WHICH band and WHICH legend they name: the
   legacy selected ``trajectory_5_levels`` / ``state_5_levels`` with
   ``pm.prod_trend_5_class`` / ``pm.prod_state_5_class`` (:437-441), while the
   spec §8 export table names the 3-class ``trajectory`` / ``state`` bands with
   ``DEGRADATION_LABELS``. The 5-class bands stay in the images and gain their own
   viz slot when D8 lands.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import ee

from sdg1531.engine._typing import as_image
from sdg1531.engine.apply import apply_truth_table
from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.integration import build_climate_collection, build_vi_collection
from sdg1531.engine.land_cover import LandCoverMaps, build_land_cover
from sdg1531.engine.productivity import (
    build_performance,
    build_productivity,
    build_state,
    build_trajectory,
)
from sdg1531.engine.soc import build_soil_organic_carbon
from sdg1531.enums import IndicatorLayer
from sdg1531.resolve import ResolvedSpec
from sdg1531.tables import DEGRADATION_LABELS, PROD_PERFORMANCE_LABELS
from sdg1531.truth_table import INDICATOR_15_3_1

__all__ = [
    "ClassifiedLayer",
    "IndicatorMaps",
    "build_indicator",
    "build_indicator_maps",
    "serialize_maps",
]


@dataclass(frozen=True, slots=True)
class ClassifiedLayer:
    """One of the seven outputs.

    ``image`` is the source image, which may carry more than one band -- the
    productivity trend and state images also hold their 5-level bands -- and
    ``band`` names the classified band inside it, per the spec §8 export table.
    Consumers select it: ``layer.image.select(layer.band)``.
    """

    id: IndicatorLayer
    label: str
    image: ee.Image
    band: str
    labels: Mapping[int, str]


@dataclass(frozen=True, slots=True)
class IndicatorMaps:
    """The seven output images of one run.

    Replaces the seven mutable output traits of ``IndicatorModel``
    (indicator_model.py:272-278). ``resolved`` rides alongside them because the
    statistics layer decodes class codes off the run's own vocabulary:
    ``fetch_transition_areas`` and ``fetch_areas_by_land_cover`` read
    ``maps.resolved``. It is the first field and is never an ``ee`` object.
    """

    resolved: ResolvedSpec
    land_cover: LandCoverMaps
    soc: ee.Image
    productivity: ee.Image
    productivity_trend: ee.Image
    productivity_state: ee.Image
    productivity_performance: ee.Image
    indicator: ee.Image

    def layers(self) -> Mapping[IndicatorLayer, ClassifiedLayer]:
        """Exactly seven layers, in spec §8 table order.

        Bands follow the §8 export table, which corrects a legacy defect: the old
        map path wrote the 3-entry degradation legend onto band 1 of all seven
        images, but band 1 of the trend and state images is the 5-class
        ``trajectory_5_levels`` / ``state_5_levels`` band, so classes 4 and 5 were
        never coloured. Here the 3-class band is named explicitly; see the module
        docstring's EXPECTED_DIVERGENCES note 3 for what that changes.
        """
        return {
            layer.id: layer
            for layer in (
                ClassifiedLayer(
                    id=IndicatorLayer.LAND_COVER,
                    label=IndicatorLayer.LAND_COVER.value,
                    image=self.land_cover.stack,
                    band="degradation",
                    labels=DEGRADATION_LABELS,
                ),
                ClassifiedLayer(
                    id=IndicatorLayer.SOC,
                    label=IndicatorLayer.SOC.value,
                    image=self.soc,
                    band="soc",
                    labels=DEGRADATION_LABELS,
                ),
                ClassifiedLayer(
                    id=IndicatorLayer.PRODUCTIVITY,
                    label=IndicatorLayer.PRODUCTIVITY.value,
                    image=self.productivity,
                    band="productivity",
                    labels=DEGRADATION_LABELS,
                ),
                ClassifiedLayer(
                    id=IndicatorLayer.PRODUCTIVITY_TREND,
                    label=IndicatorLayer.PRODUCTIVITY_TREND.value,
                    image=self.productivity_trend,
                    band="trajectory",
                    labels=DEGRADATION_LABELS,
                ),
                ClassifiedLayer(
                    id=IndicatorLayer.PRODUCTIVITY_STATE,
                    label=IndicatorLayer.PRODUCTIVITY_STATE.value,
                    image=self.productivity_state,
                    band="state",
                    labels=DEGRADATION_LABELS,
                ),
                ClassifiedLayer(
                    id=IndicatorLayer.PRODUCTIVITY_PERFORMANCE,
                    label=IndicatorLayer.PRODUCTIVITY_PERFORMANCE.value,
                    image=self.productivity_performance,
                    band="performance",
                    labels=PROD_PERFORMANCE_LABELS,
                ),
                ClassifiedLayer(
                    id=IndicatorLayer.INDICATOR_15_3_1,
                    label=IndicatorLayer.INDICATOR_15_3_1.value,
                    image=self.indicator,
                    band="indicator_15_3_1",
                    labels=DEGRADATION_LABELS,
                ),
            )
        }


def build_indicator(productivity: ee.Image, land_cover: LandCoverMaps, soc: ee.Image) -> ee.Image:
    """Collapse the three sub-indicators into 15.3.1 (run_15_3_1.py:373-411).

    The 30 rules -- the 27 cells of the 3x3x3 grid, then the three rows that test
    ``.lt(1)`` on two of the three operands (:406-408) -- live in
    ``truth_table.INDICATOR_15_3_1``; ``apply_truth_table`` is the emitter, and the
    order it walks the rules in is what keeps the serialized graph identical.

    ``.rename("indicator_15_3_1")`` is the one deliberate change; see the module
    docstring's EXPECTED_DIVERGENCES note 1.
    """
    water = land_cover.water  # :374 -- off the stack, BEFORE the degradation band
    landcover = land_cover.degradation  # :375

    indicator = apply_truth_table(
        (productivity, landcover, soc), INDICATOR_15_3_1, "indicator_15_3_1"
    )  # :377-409

    # :411 -- the mask is applied AFTER the collapse, with the water image as its
    # own test, and the cast sits outside the `.where()`.
    return as_image(indicator.where(water, 0).uint8())


def build_indicator_maps(r: ResolvedSpec, ctx: ExecutionContext) -> IndicatorMaps:
    """Build all seven outputs (run_15_3_1.py:164-204), in the legacy's own order.

    The legacy ``if not (model.start < model.end): raise`` at :165-167 is gone; see
    the module docstring's EXPECTED_DIVERGENCES note 2.
    """
    climate = build_climate_collection(r, ctx)  # :171
    vi = build_vi_collection(r, ctx)  # :172

    trajectory = build_trajectory(r, vi, climate)  # :173-175
    performance = build_performance(r, ctx, vi)  # :176-178
    state = build_state(r, vi)  # :179

    land_cover = build_land_cover(r, ctx)  # :182
    soc = build_soil_organic_carbon(r, ctx)  # :183

    # :184-197 -- the GPGv2/GPGv1 branch is now a resolved TruthTable that
    # build_productivity reads off `r`. Keywords, not positions: the legacy call
    # site is (trajectory, PERFORMANCE, STATE) and the port's rule order is
    # (trajectory, STATE, PERFORMANCE), so a positional call would silently
    # misclassify rather than fail.
    productivity = build_productivity(
        r, trajectory=trajectory, state=state, performance=performance
    )

    indicator = build_indicator(productivity, land_cover, soc)  # :200-202

    return IndicatorMaps(
        resolved=r,
        land_cover=land_cover,
        soc=soc,
        productivity=productivity,
        productivity_trend=trajectory,
        productivity_state=state,
        productivity_performance=performance,
        indicator=indicator,
    )


def serialize_maps(maps: IndicatorMaps) -> dict[str, str]:
    """Encode all seven images, keyed by the spec §8 layer id.

    The parity harness (§12 Tier 4) compares these strings old-vs-new, so the
    values are WHOLE images -- the same objects the legacy assigned to its seven
    output traits (run_15_3_1.py:173-202) -- and not band selections.
    """
    return {
        layer.id.name.lower(): str(ee.serializer.toJSON(layer.image))
        for layer in maps.layers().values()
    }
