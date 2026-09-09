"""Shared fixtures for the engine (ee-graph) tests.

The builders under test read only a small, named set of attributes off
ResolvedSpec, so these tests hand them a SimpleNamespace with exactly those
attributes. Real `resolve()` output is covered by tests/test_resolve.py and by
the parity harness; keeping the two apart means a transcription bug here cannot
be hidden by a derivation bug there.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sdg1531.enums import Lceu, Trajectory, VegetationIndex
from sdg1531.spec import Compatibility, Period, SensorSelection
from sdg1531.truth_table import PRODUCTIVITY_GPGV2


def make_resolved(**overrides):
    """Build a stand-in ResolvedSpec carrying every attribute the engine reads."""
    spec = SimpleNamespace(
        vi_source=SensorSelection(names=("MODIS MOD13Q1",)),
        vegetation_index=VegetationIndex.NDVI,
        threshold=0.0,
        trajectory=Trajectory.NDVI_TREND,
        lceu=Lceu.GAES,
        compatibility=Compatibility(),
    )
    resolved = SimpleNamespace(
        spec=spec,
        integration_period=Period(2001, 2015),
        trend=Period(2001, 2015),
        state=Period(2001, 2015),
        performance=Period(2001, 2015),
        land_cover_period=Period(2001, 2015),
        soc_period=Period(2001, 2015),
        lc_year_start_esa=2001,
        lc_year_end_esa=2015,
        analysis_scale=250,
        zonal_scale=300,
        productivity_table=PRODUCTIVITY_GPGV2,
    )
    for key, value in overrides.items():
        if key in vars(spec):
            setattr(spec, key, value)
        else:
            setattr(resolved, key, value)
    return resolved


@pytest.fixture
def resolved():
    return make_resolved()


@pytest.fixture
def ctx():
    import ee

    from sdg1531.engine.context import ExecutionContext

    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle([0, 0, 1, 1]))])
    return ExecutionContext.from_feature_collection(fc, 250)
