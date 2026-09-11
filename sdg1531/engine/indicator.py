"""The 15.3.1 indicator and the seven-layer seam.

Transcribed from ``component/scripts/run_15_3_1.py`` -- ``indicator_15_3_1()``
(:373-411) and ``compute_indicator_maps()`` (:164-204). Phase 1 is a
transcription, not a refactor: the 30 ``.where()`` rules and the terminal
``.where(water, 0).uint8()`` reach ``ee`` in the legacy's own order, and the
legacy's weaknesses are preserved and annotated rather than repaired.

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
(run_15_3_1.py:425-450). It is the single seam for the seven IMAGES -- map layers,
export sources and the statistics layer picker all iterate it -- and there is
deliberately no second ``export_layers()``.

The seam is the images, not the vocabulary. :attr:`ClassifiedLayer.band` and
:attr:`ClassifiedLayer.labels` are the MAP AND EXPORT vocabulary. The STATISTICS
vocabulary lives in ``sdg1531.stats``: it carries its own tables and reads
only ``.image`` from here -- ``_STATS_BAND`` in ``sdg1531/stats/requests.py``
and ``_STATS_LABELS`` in ``sdg1531/stats/decode.py``, which stays free of
``ee``. Under them the two vocabularies
deliberately disagree for the trend and state layers -- statistics keep the legacy
5-class bands, export takes the 3-class ones -- so "unifying" them would silently
change the statistics. See EXPECTED_DIVERGENCES note 4, whose narrowing
depends on that split, which the shipped code holds to.

ResolvedSpec fields read here: none directly. :func:`build_indicator_maps` threads
``r`` into the sub-indicator builders and keeps it on
:attr:`IndicatorMaps.resolved`, because the statistics layer decodes class codes
off the run's own vocabulary.

EXPECTED_DIVERGENCES note -- four divergences from the legacy. The parity harness
must carry all four:

1. **Behaviour-changing, and NORMALISED rather than licensed.**
   :func:`build_indicator` ends ``.rename("indicator_15_3_1")``, where
   ``run_15_3_1.py:411`` renames nothing at all, so the legacy band is literally
   called ``constant``. Every scenario's indicator layer carries the same one extra
   ``Image.rename`` node, in the same position.

   The harness does NOT license it. It was licensed once, as
   ``EXPECTED_DIVERGENCES[("*", "indicator_15_3_1")]``, and that entry -- written
   for this one node -- covered the whole layer: the 30-rule collapse, its rule
   order, the water mask and the cast position of the module's headline output
   were compared against nothing, and swapping ``.uint8()`` and
   ``.where(water, 0)`` below left every parity test green. The entry is gone.
   ``tests/parity/canonical.py`` splices the rename node out and requires byte
   equality on everything that remains, so the layer is compared like any other;
   see ``EXPECTED_NORMALISATIONS["indicator_band_rename"]``. The splice is tied to
   this exact chain -- ``Image.uint8`` over ``Image.where`` over
   ``Image.rename(["indicator_15_3_1"])`` -- so moving the cast, the mask or the
   rename stops it firing and fails. ``tests/engine/test_indicator.py``
   re-derives the same equality against a verbatim copy of the legacy chain.
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
   an unrecognised name -- an ``UnboundLocalError`` at its own ``return``. That
   totality is the whole of this entry: it does NOT license a change of band or of
   legend on the statistics path, which ``sdg1531.stats`` ports unchanged.
   See note 4.
4. **No legacy counterpart.** The ``trajectory`` / ``state`` rows of
   :meth:`IndicatorMaps.layers` give the trend and state layers a 3-class export
   band and a 3-class legend, and the legacy has nothing to compare them against:
   ``display_maps`` (run_15_3_1.py:105-158) draws six rasters plus the AOI --
   land-cover start and end, productivity, land-cover degradation, soc and the
   indicator -- and trend, state and performance are never drawn at all. The four
   CLASSIFIED ones among those six are each genuinely 3-class, drawn with
   ``viz_prod`` / ``viz_lc_sub`` / ``viz_soc`` / ``viz_indicator``, all
   ``{"min": 1, "max": 3}`` over a 3-entry legend (parameter/ui.py:49-53, :72-75).
   (The other two, land-cover start and end, use ``viz_lc``, whose min/max come
   from the class code list at run_15_3_1.py:106-110 -- not a 3-class scheme.) So
   the legacy never misapplied a legend; it simply never rendered these two layers.
   The port gives them an export band and a legend for the first time. This is a NEW
   capability, not a changed one -- and in particular it is not intended to change
   the statistics: ``indicator_n_category_label``'s ``trajectory_5_levels`` /
   ``state_5_levels`` branches (:437-442) are ported faithfully, and
   ``_STATS_BAND`` (``stats/requests.py``) and ``_STATS_LABELS``
   (``stats/decode.py``) keep the 5-class band and the 6-entry legend.
   That is a fact about shipped code rather than a
   dependency: a 3-class statistics band for trend or state would make this note
   wrong in the licensing direction and must be revisited. Filing it as
   behaviour-changing instead would hand the harness a licence to wave through a
   real statistics regression.
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
    ``band`` names the classified band inside it, as fixed by
    :meth:`IndicatorMaps.layers`. Consumers select it: ``layer.image.select(layer.band)``.

    ``band`` and ``labels`` are the MAP AND EXPORT vocabulary only. The statistics
    path keeps its own -- ``_STATS_BAND`` in ``sdg1531/stats/requests.py`` and
    ``_STATS_LABELS`` in ``sdg1531/stats/decode.py`` -- and reads only ``.image``
    from here; for trend and state the two deliberately disagree (see the module
    docstring and EXPECTED_DIVERGENCES note 4).

    ``label`` is the layer's snake id -- ``id.value``, e.g. ``"productivity_trend"``
    -- not a human display string. Translated display labels live in the app layer
    -- the name is a near-twin of ``labels``, which is the class legend, so
    the distinction is worth stating.

    ``frozen=True`` synthesises ``__hash__``, but hashing an instance raises
    ``TypeError`` because ``labels`` is a mapping. Nothing hashes these today;
    ``eq=False`` is not used because equality is worth having.
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

    As with :class:`ClassifiedLayer`, ``frozen=True`` synthesises a ``__hash__``
    that raises ``TypeError: unhashable type: 'dict'`` -- here because
    ``resolved`` carries mappings. (``ee.Image`` itself hashes fine; the images
    are not the obstacle.)
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
        """Exactly seven layers, in the canonical table order.

        The bands are the MAP AND EXPORT vocabulary, and it does not repair a legacy
        misapplied legend -- there was none. ``display_maps``
        (run_15_3_1.py:105-158) draws six rasters plus the AOI outline, all four of
        its classified ones are genuinely 3-class, and trend, state and performance
        are never drawn at all. The port gives trend and state a 3-class band and
        legend for the first time; their 5-class bands stay in the images, and remain
        what the statistics path selects. See EXPECTED_DIVERGENCES note 4.

        The ORDER here is ``IndicatorLayer``'s, which follows the trait declaration
        order at indicator_model.py:272-278. Legacy ``download_maps``
        (run_15_3_1.py:39-49) exports the same seven images in a different order --
        ``productivity`` sixth rather than third, performance and state swapped --
        under the comment "they are in correct order don't change it". That is not
        a divergence of this seam: export order is the app layer's business, the
        GEE export tasks are independent, and the legacy discards the dict it
        builds. A consumer that needs the legacy order must impose it itself.
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


def build_indicator(
    *, productivity: ee.Image, land_cover: LandCoverMaps, soc: ee.Image
) -> ee.Image:
    """Collapse the three sub-indicators into 15.3.1 (run_15_3_1.py:373-411).

    The 30 rules -- the 27 cells of the 3x3x3 grid, then the three rows that test
    ``.lt(1)`` on two of the three operands (:406-408) -- live in
    ``truth_table.INDICATOR_15_3_1``; ``apply_truth_table`` is the emitter, and the
    order it walks the rules in is what keeps the serialized graph identical.

    The three images are KEYWORD-ONLY, for the same reason
    :func:`~sdg1531.engine.productivity.build_productivity`'s are: ``productivity``
    and ``soc`` are both single-band 3-class ``uint8``, ``INDICATOR_15_3_1`` is not
    symmetric in them (compare :385-387 with :394-396), and ``ee`` is lazy -- so a
    positional swap would build a clean graph and misclassify at evaluation time.

    ``.rename("indicator_15_3_1")`` is the one deliberate change; see the module
    docstring's EXPECTED_DIVERGENCES note 1.
    """
    water = land_cover.water  # :374 -- off the stack, BEFORE the degradation band
    landcover = land_cover.degradation  # :375

    indicator = apply_truth_table(
        (productivity, landcover, soc), INDICATOR_15_3_1, INDICATOR_15_3_1.band
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

    indicator = build_indicator(
        productivity=productivity, land_cover=land_cover, soc=soc
    )  # :200-202

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
    """Encode all seven images, keyed by the layer id.

    The parity harness compares these strings old-vs-new, so the values are WHOLE
    images -- the same objects the legacy assigned to its seven output traits
    (run_15_3_1.py:173-202) -- and not band selections.

    Keyed on ``layer.id.value``, which IS the canonical layer id:
    ``IndicatorLayer`` is a ``str`` enum, ``naming.py``'s ``LAYER_BASENAMES`` keys
    on ``.value``, and ``sdg1531.stats`` uses ``layer.value`` for DataFrame columns.
    ``.name.lower()`` agrees today only because every member's identifier happens
    to spell its own value.
    """
    return {
        layer.id.value: str(ee.serializer.toJSON(layer.image)) for layer in maps.layers().values()
    }
