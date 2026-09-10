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

The ``.getInfo()`` below is deliberate and legal. The Tier-0 hygiene guard walks
``sdg1531/`` and ``app/`` only (``iter_domain_sources()``); it never looks under
``tests/``.
"""

from __future__ import annotations

import os
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
            overall=Period(2014, 2015),
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


def build_histogram_request() -> tuple[ee.Dictionary, str]:
    """The whole pipeline, stopping one call short of the round trip.

    Everything here is client-side graph construction, so it runs offline against
    the captured algorithm table exactly as it runs against the live API.
    """
    spec = _spec()
    resolved = resolve(spec)
    ctx = ExecutionContext.from_aoi_spec(spec.aoi, resolved.analysis_scale)
    maps = build_indicator_maps(resolved, ctx)

    layer = maps.layers()[IndicatorLayer.INDICATOR_15_3_1]
    request = layer.image.select(layer.band).reduceRegion(
        reducer=ee.Reducer.frequencyHistogram(),
        geometry=ctx.bounds,
        scale=250,
        maxPixels=1e13,
        bestEffort=True,
    )
    return request, layer.band


@pytest.mark.network
def test_the_indicator_computes_over_a_10km_box() -> None:
    _initialize()

    request, band = build_histogram_request()
    histogram = request.getInfo()

    counts = histogram[band]
    assert counts, "Earth Engine returned an empty histogram for the indicator band"
    assert set(counts) <= {"0", "1", "2", "3"}, counts


def test_the_request_builds_offline() -> None:
    """Everything the Tier-6 test does except the round trip, on the PR gate.

    A test that only ever runs at 03:17 UTC is a test whose Python nobody checks.
    This one fails on the PR that breaks the spec, the resolve, the indicator graph
    or the reducer call; only a server-side answer can still surprise the nightly.
    """
    request, band = build_histogram_request()

    assert band == IndicatorLayer.INDICATOR_15_3_1.value
    assert isinstance(request, ee.Dictionary)


def test_a_missing_credential_fails_loudly_rather_than_skipping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The nightly must go red when the secret goes missing, not green and quiet."""
    monkeypatch.delenv("EARTHENGINE_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    with pytest.raises(RuntimeError, match="EARTHENGINE_TOKEN"):
        _initialize()
