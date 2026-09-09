"""Builders for domain specs used across the test suite. Imports no ee."""

from __future__ import annotations

from typing import Any

from sdg1531.enums import Lceu, ProductivityLookup, Trajectory, VegetationIndex
from sdg1531.scheme import TransitionMatrix
from sdg1531.spec import (
    AssetAoi,
    Compatibility,
    EsaCciSource,
    JrcSeasonalityMask,
    Period,
    PeriodOverride,
    PerPixelClimate,
    RunSpec,
    SensorSelection,
    SubPeriods,
)

__all__ = ["DEFAULT_PERIODS", "default_spec"]

DEFAULT_PERIODS = SubPeriods(
    overall=Period(start=2000, end=2020),
    trend=PeriodOverride(None, None),
    state=PeriodOverride(None, None),
    performance=PeriodOverride(None, None),
    land_cover=PeriodOverride(None, None),
    soc=PeriodOverride(None, None),
)


def default_spec(**changes: Any) -> RunSpec:
    """A fully populated, deterministic RunSpec; `changes` go through evolve()."""
    spec = RunSpec(
        periods=DEFAULT_PERIODS,
        vi_source=SensorSelection(names=("MODIS MOD13Q1",)),
        vegetation_index=VegetationIndex.NDVI,
        trajectory=Trajectory.NDVI_TREND,
        lceu=Lceu.GAES,
        productivity_lookup=ProductivityLookup.GPGV2,
        transition_matrix=TransitionMatrix.default(),
        land_cover=EsaCciSource(),
        water_mask=JrcSeasonalityMask(threshold=6),
        climate=PerPixelClimate(),
        aoi=AssetAoi(asset_id="users/test/aoi", name="test-aoi"),
        threshold=None,
        compatibility=Compatibility(),
    )
    return spec.evolve(**changes) if changes else spec
