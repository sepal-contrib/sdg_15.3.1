"""Shared fixtures for the engine (ee-graph) tests.

The builders under test read only a small, named set of attributes off
ResolvedSpec, so these tests hand them a SimpleNamespace with exactly those
attributes. Real `resolve()` output is covered by tests/test_resolve.py and by
the parity harness; keeping the two apart means a transcription bug here cannot
be hidden by a derivation bug there -- except for the two fields named below,
where the isolation is deliberately given up.

The two exceptions are `vi_processor` and `vi_assets`, which the stub DERIVES
(see `make_resolved`): they are the engine's dispatch key, so a hand-set value
would describe a run `resolve()` cannot produce.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sdg1531.enums import Lceu, Trajectory, VegetationIndex
from sdg1531.resolve import _vi_dispatch
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
    """Build a stand-in ResolvedSpec carrying every attribute the engine reads.

    `vi_processor` and `vi_assets` are DERIVED, by the real `_vi_dispatch`, from
    whatever `vi_source` / `vegetation_index` / `compatibility` this call ends up
    with. `build_vi_collection` dispatches on those two fields, so a stub that
    set them by hand could describe a run `resolve()` cannot produce -- a MODIS
    `vi_source` under the Sentinel 2 rung, say -- and the engine test would then
    be pinning a state that never reaches the engine. Deriving them makes that
    disagreement unrepresentable through the override kwarg rather than merely
    unlikely. (`resolved` is a SimpleNamespace, so a test could still assign the
    attribute directly; none does.)

    The consequence is that a `vi_source` the LADDER refuses (an empty
    selection, an unknown sensor name, MSVI over Derived VI Landsat with
    `derived_vi_msvi_uses_evi_asset` off) now raises from this call rather than
    from `build_vi_collection`. That is where `resolve()` raises it too;
    tests/test_resolve.py owns those cases.
    """
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
    # after the overrides, so the rung matches the vi_source the test asked for
    resolved.vi_processor, resolved.vi_assets = _vi_dispatch(spec)
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
