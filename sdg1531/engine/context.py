"""Where a run is computed: the AOI collection and the analysis scale.

Replaces the legacy `aoi_model` reach-through. The three expressions below are
the only AOI shapes the legacy science uses, and they must stay node-identical:

    feature_collection                      integration.py:22, :58, :73, :85
    feature_collection.geometry()           productivity.py:143
    feature_collection.geometry().bounds()  land_cover.py:10,
                                            soil_organic_carbon.py:9, :21

No EXPECTED_DIVERGENCES: the AOI is an INPUT to both trees rather than a thing under
test, and ``tools/to_legacy_model.py`` builds it the same way on the legacy side.
That makes it ``HELD_CONSTANT["aoi_leaf"]`` -- something the harness does not
compare -- which is recorded, but is not a divergence: nothing differs.
"""

from __future__ import annotations

from dataclasses import dataclass

import ee

from sdg1531.errors import SpecError
from sdg1531.spec import AdminAoi, AssetAoi, GeoJsonAoi

__all__ = ["ExecutionContext"]


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """The AOI and the scale every engine function computes against."""

    feature_collection: ee.FeatureCollection
    analysis_scale: int

    @property
    def geometry(self) -> ee.Geometry:
        # transcribed from productivity.py:143
        return self.feature_collection.geometry()

    @property
    def bounds(self) -> ee.Geometry:
        # transcribed from land_cover.py:10 / soil_organic_carbon.py:9
        return self.feature_collection.geometry().bounds()

    @classmethod
    def from_feature_collection(
        cls, feature_collection: ee.FeatureCollection, analysis_scale: int
    ) -> ExecutionContext:
        """Build from a live collection — the phase-1 app path."""
        return cls(feature_collection=feature_collection, analysis_scale=analysis_scale)

    @classmethod
    def from_aoi_spec(cls, aoi: object, analysis_scale: int) -> ExecutionContext:
        """Build from a serialized AOI — headless replay and tests."""
        if isinstance(aoi, AssetAoi):
            collection = ee.FeatureCollection(aoi.asset_id)
        elif isinstance(aoi, GeoJsonAoi):
            collection = ee.FeatureCollection(aoi.geojson)
        elif isinstance(aoi, AdminAoi):
            import pygaul

            # The same call pysepal's GEE admin branch makes (admin.py:283), so a
            # restored run reduces over the identical collection the picker produced.
            collection = pygaul.Items(admin=aoi.admin_code)
        else:
            raise SpecError(f"unsupported aoi arm: {type(aoi).__name__}")
        return cls(feature_collection=collection, analysis_scale=analysis_scale)
