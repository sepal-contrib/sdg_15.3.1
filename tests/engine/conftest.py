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
from sdg1531.spec import (
    Compatibility,
    EsaCciSource,
    JrcSeasonalityMask,
    Period,
    PerPixelClimate,
    SensorSelection,
)
from sdg1531.truth_table import PRODUCTIVITY_GPGV2

# Stand-ins for the two land-cover remap tables. Deliberately short and
# deliberately unlike each other: the real values are a 49-entry transition-code
# list and a 49-entry -1/0/1 matrix, so a builder that swapped the two arguments
# of `landcover_transition.remap(...)` would still emit a plausible graph. These
# make the swap visible. tests/test_resolve.py owns the real derivation.
STUB_CLASS_COMBINATIONS = (1010, 2030, 4070)
STUB_TRANS_MATRIX_FLATTEN = (0, -1, 1)


def make_resolved(**overrides):
    """Build a stand-in ResolvedSpec carrying every attribute the engine reads."""
    spec = SimpleNamespace(
        vi_source=SensorSelection(names=("MODIS MOD13Q1",)),
        vegetation_index=VegetationIndex.NDVI,
        threshold=0.0,
        trajectory=Trajectory.NDVI_TREND,
        lceu=Lceu.GAES,
        land_cover=EsaCciSource(),
        water_mask=JrcSeasonalityMask(threshold=6),
        climate=PerPixelClimate(),
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
        soc_year_start=2001,
        soc_year_end_esa=2015,
        lc_class_combinations=STUB_CLASS_COMBINATIONS,
        trans_matrix_flatten=STUB_TRANS_MATRIX_FLATTEN,
        analysis_scale=250,
        zonal_scale=300,
        productivity_table=PRODUCTIVITY_GPGV2,
    )
    for key, value in overrides.items():
        if key in vars(spec):
            setattr(spec, key, value)
        elif key in vars(resolved):
            setattr(resolved, key, value)
        else:
            # Deliberate override of the plan text (task-10-fixes.md, Minor
            # 7): a typo'd override key used to route silently to `resolved`
            # via `setattr`, leaving the test running against the untouched
            # default instead of failing. This file is shared by Tasks
            # 11-17, so catching that here once is cheaper than debugging a
            # silently-green test six tasks later.
            raise AttributeError(
                f"make_resolved() got an unknown override {key!r}; not an "
                "attribute of the stub's spec or resolved namespace"
            )
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
