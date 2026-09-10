"""Tier 6: one live end-to-end run against Earth Engine (spec §12).

Marked ``network``, so the PR gate (``pytest -m "not network"``) never selects it
and the nightly workflow is the only thing that runs it. It catches server-side
errors that graph-shape tests structurally cannot see: a remap whose two lists
have different lengths, a band that does not exist on the real collection, a
reducer arity mismatch.

**The half that does not need credentials runs on every PR.** A test only the
nightly executes is a test nobody watches, so everything up to the round trip --
resolve, the AOI, the whole indicator graph and the reducer -- is built by
:func:`build_histogram_request`, which :func:`test_the_request_builds_offline`
calls under the offline ``ee``. That leaves exactly one thing unproven until the
nightly runs: the server's answer. The brief's version of this file passed
``threshold=None``, which raises ``SpecError`` in ``_process_modis`` before any
request is sent; the offline test is what found it.

**So is the ASSERTION.** The live test used to make one claim,
``set(counts) <= {"0", "1", "2", "3"}``, which ``{"0": N}`` satisfies -- so a green
nightly was compatible with "every pixel is NoData" over an AOI whose whole purpose
is to have data. :func:`histogram_problems` is that judgement, lifted out of the
round trip into a pure function over the payload, and
:func:`test_a_degenerate_histogram_is_caught` runs it on the PR gate against the
degenerate answers it has to reject. Only the server's reply is unwatched now; what
the test makes of it is not.

The ``.getInfo()`` below is deliberate and legal. The Tier-0 hygiene guard walks
``sdg1531/`` and ``app/`` only (``iter_domain_sources()``); it never looks under
``tests/``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import ee
import pytest

from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.indicator import build_indicator_maps
from sdg1531.enums import (
    IndicatorLayer,
    Lceu,
    ProductivityLookup,
    Trajectory,
    VegetationIndex,
)
from sdg1531.resolve import resolve
from sdg1531.scheme import TransitionMatrix
from sdg1531.spec import (
    Compatibility,
    EsaCciSource,
    GeoJsonAoi,
    JrcSeasonalityMask,
    Period,
    PeriodOverride,
    PerPixelClimate,
    RunSpec,
    SensorSelection,
    SubPeriods,
)
from sdg1531.tables import DEGRADATION_LABELS
from sdg1531.validate import validate

# ~10 km box in Senegal - the same AOI tools/scenarios.py uses for the corpus
AOI_GEOJSON: dict[str, Any] = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"name": "tier-6-box"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-15.60, 14.60],
                        [-15.50, 14.60],
                        [-15.50, 14.70],
                        [-15.60, 14.70],
                        [-15.60, 14.60],
                    ]
                ],
            },
        }
    ],
}


def _initialize() -> None:
    """ee.Initialize from the ambient credential.

    The nightly workflow exports EARTHENGINE_TOKEN, which holds the JSON body of
    the Earth Engine credentials file; materialise it when the file is not there.

    A missing credential RAISES rather than skipping. A skip here would be
    indistinguishable from a pass in the only job that runs this test, so the
    secret going missing would silently retire Tier 6 instead of failing.
    """
    token = os.environ.get("EARTHENGINE_TOKEN")
    credentials = Path.home() / ".config" / "earthengine" / "credentials"
    if token and not credentials.exists():
        credentials.parent.mkdir(parents=True, exist_ok=True)
        credentials.write_text(token)
    if not token and not credentials.exists():
        raise RuntimeError(
            "no Earth Engine credential: set the EARTHENGINE_TOKEN repository secret, "
            f"or write {credentials}. Tier 6 fails rather than skipping, because the "
            "nightly job is the only thing that runs it."
        )
    ee.Initialize()


def _spec() -> RunSpec:
    no_override = PeriodOverride(None, None)
    return RunSpec(
        periods=SubPeriods(
            # Six years, not the two this started with. Every sub-period falls back
            # to `overall`, so a two-year window made the state period two years,
            # and `build_state` (engine/productivity.py:469) then filters the
            # baseline on `rangeContains("year", 2014, 2011)` -- an EMPTY range.
            # `previous_vi_mu` reduces an empty ImageCollection, which has no bands,
            # and `.rename(["vi"])` against zero bands is a server-side error; on the
            # graphs that survive it, `state` is 0 everywhere, which unfires 27 of
            # INDICATOR_15_3_1's 30 rules. `sdg1531.validate` says so up front --
            # `state_period_too_short`, pinned by
            # `test_the_smoke_specs_period_satisfies_the_ports_own_validator` below --
            # and the corpus's own windows are 10 to 20 years wide.
            overall=Period(2010, 2015),
            trend=no_override,
            state=no_override,
            performance=no_override,
            land_cover=no_override,
            soc=no_override,
        ),
        vi_source=SensorSelection(names=("MODIS MOD13Q1",)),
        vegetation_index=VegetationIndex.NDVI,
        # `_process_modis` puts this through `require_float`, so None is refused
        # before a request is ever built (integration.py:453). 0.0 is the corpus's
        # own "zero" threshold (tools/scenarios.py:186).
        threshold=0.0,
        trajectory=Trajectory.NDVI_TREND,
        lceu=Lceu.GAES,
        productivity_lookup=ProductivityLookup.GPGV2,
        transition_matrix=TransitionMatrix.default(),
        land_cover=EsaCciSource(),
        water_mask=JrcSeasonalityMask(threshold=6),
        climate=PerPixelClimate(),
        aoi=GeoJsonAoi(geojson=AOI_GEOJSON, name="tier 6 box"),
        compatibility=Compatibility(),
    )


# The three layers the live run counts. The indicator alone is not enough: it is
# the collapse of the three sub-indicators, so `productivity` going constant-zero
# takes the indicator down with it and both read as "an answer". `productivity`
# and `state` are the two the short window degraded, so they are the two that say
# whether it is fixed.
_COUNTED_LAYERS = (
    IndicatorLayer.INDICATOR_15_3_1,
    IndicatorLayer.PRODUCTIVITY,
    IndicatorLayer.PRODUCTIVITY_STATE,
)

# The export band of each counted layer (spec §8), written out rather than read off
# the ClassifiedLayer the assertion checks -- a band read from the same object it is
# compared with would agree with itself whatever it said.
BANDS: Mapping[IndicatorLayer, str] = {
    IndicatorLayer.INDICATOR_15_3_1: "indicator_15_3_1",
    IndicatorLayer.PRODUCTIVITY: "productivity",
    IndicatorLayer.PRODUCTIVITY_STATE: "state",
}


def build_histogram_request(
    layer_id: IndicatorLayer,
) -> tuple[ee.Dictionary, str, Mapping[int, str]]:
    """The whole pipeline, stopping one call short of the round trip.

    Everything here is client-side graph construction, so it runs offline against
    the captured algorithm table exactly as it runs against the live API. The
    layer's own ``labels`` come back with it so the caller never has to retype the
    class codes it is allowed to see.
    """
    spec = _spec()
    resolved = resolve(spec)
    ctx = ExecutionContext.from_aoi_spec(spec.aoi, resolved.analysis_scale)
    maps = build_indicator_maps(resolved, ctx)

    layer = maps.layers()[layer_id]
    request = layer.image.select(layer.band).reduceRegion(
        reducer=ee.Reducer.frequencyHistogram(),
        geometry=ctx.bounds,
        scale=250,
        maxPixels=1e13,
        bestEffort=True,
    )
    return request, layer.band, layer.labels


def histogram_problems(
    counts: Mapping[str, Any] | None, *, band: str, labels: Mapping[int, str]
) -> list[str]:
    """What is wrong with one layer's frequency histogram, as a list of reasons.

    A pure function over the payload, so the PR gate can run it on the answers the
    nightly must reject. The judgement it makes is the part of the Tier-6 test that
    used to be unwatched AND unfalsifiable at once.

    ``labels`` is the layer's own legend (``ClassifiedLayer.labels``), so the legal
    class codes are derived from the vocabulary the layer is built with rather than
    retyped here -- a layer given a different legend brings its own answer along.
    """
    if not counts:
        return [f"Earth Engine returned an empty histogram for {band}"]

    problems = []
    legal = {str(code) for code in labels}
    if not set(counts) <= legal:
        problems.append(f"{band} holds classes outside its legend {sorted(legal)}: {counts}")

    # `set(counts) <= legal` alone is satisfied by {"0": N} -- every pixel NoData --
    # which is exactly the answer the two-year window produced and the answer this
    # AOI cannot honestly give. Both checks below reject it; they are separate
    # because they fail for different reasons and the message should say which.
    if len(counts) < 2:
        problems.append(f"{band} has a single class over the whole AOI: {counts}")
    if not set(counts) - {"0"}:
        problems.append(f"{band} classified no pixel at all; every one is NoData: {counts}")
    return problems


@pytest.mark.network
def test_the_indicator_computes_over_a_10km_box() -> None:
    _initialize()

    for layer_id in _COUNTED_LAYERS:
        request, band, labels = build_histogram_request(layer_id)
        histogram = request.getInfo()

        problems = histogram_problems(histogram.get(band), band=band, labels=labels)
        assert problems == [], f"{layer_id.value}: " + "; ".join(problems)


@pytest.mark.parametrize("layer_id", _COUNTED_LAYERS, ids=lambda layer: layer.value)
def test_the_request_builds_offline(layer_id: IndicatorLayer) -> None:
    """Everything the Tier-6 test does except the round trip, on the PR gate.

    A test that only ever runs at 03:17 UTC is a test whose Python nobody checks.
    This one fails on the PR that breaks the spec, the resolve, the indicator graph
    or the reducer call; only a server-side answer can still surprise the nightly.
    """
    request, band, labels = build_histogram_request(layer_id)

    assert isinstance(request, ee.Dictionary)
    assert band == BANDS[layer_id]
    assert labels, f"{layer_id.value} carries no legend to check its classes against"


def test_the_smoke_specs_period_satisfies_the_ports_own_validator() -> None:
    """The window this file runs on, held to the rules the port ships.

    `overall=Period(2014, 2015)` was a two-year window, and `state_period_too_short`
    says what that costs: an empty baseline filter, a band-less reduction and a
    state layer that is 0 everywhere. Nothing checked the smoke spec against
    `validate()`, and the one test that would have noticed is the one nobody runs.
    """
    problems = validate(_spec())

    assert [problem.code for problem in problems] == [], problems


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ({"0": 1024.0}, "every one is NoData"),
        ({"2": 1024.0}, "a single class"),
        ({}, "empty histogram"),
        (None, "empty histogram"),
        ({"0": 1.0, "9": 2.0}, "outside its legend"),
    ],
)
def test_a_degenerate_histogram_is_caught(counts: dict[str, float] | None, expected: str) -> None:
    """The answers a green nightly must NOT accept, checked where they can be seen.

    ``{"0": N}`` is the one that matters: it is what the old two-year window
    computed, and the old assertion -- a subset test -- passed on it.
    """
    problems = histogram_problems(counts, band="indicator_15_3_1", labels=DEGRADATION_LABELS)

    assert any(expected in problem for problem in problems), problems


def test_a_healthy_histogram_raises_nothing() -> None:
    """The other direction: a checker that rejected everything would pass the test
    above and fail every nightly."""
    counts = {"0": 12.0, "1": 340.0, "2": 900.0, "3": 44.0}

    assert histogram_problems(counts, band="indicator_15_3_1", labels=DEGRADATION_LABELS) == []


def test_a_missing_credential_fails_loudly_rather_than_skipping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The nightly must go red when the secret goes missing, not green and quiet."""
    monkeypatch.delenv("EARTHENGINE_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    with pytest.raises(RuntimeError, match="EARTHENGINE_TOKEN"):
        _initialize()
