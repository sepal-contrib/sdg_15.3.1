"""ExecutionContext must reproduce the legacy AOI expressions node for node.

The legacy science reaches into `aoi_model` three different ways:
  `aoi_model.feature_collection`                       integration.py:22,58,73,85
  `aoi_model.feature_collection.geometry()`            productivity.py:143
  `aoi_model.feature_collection.geometry().bounds()`   land_cover.py:10,
                                                       soil_organic_carbon.py:9,21
All three must serialize identically here or every downstream graph diverges.
"""

import dataclasses

import ee
import pytest

from sdg1531.engine.context import ExecutionContext
from sdg1531.errors import SpecError
from sdg1531.spec import AssetAoi, GeoJsonAoi

ASSET = "projects/test/assets/some_aoi"

GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
            },
        }
    ],
}


@pytest.fixture()
def ctx(ee_offline):
    return ExecutionContext(feature_collection=ee.FeatureCollection(ASSET), analysis_scale=300)


def test_feature_collection_is_passed_through_untouched(ctx):
    assert ctx.feature_collection.serialize() == ee.FeatureCollection(ASSET).serialize()


def test_geometry_is_feature_collection_dot_geometry(ctx):
    expected = ee.FeatureCollection(ASSET).geometry()
    assert ctx.geometry.serialize() == expected.serialize()


def test_bounds_is_geometry_dot_bounds(ctx):
    expected = ee.FeatureCollection(ASSET).geometry().bounds()
    assert ctx.bounds.serialize() == expected.serialize()


def test_bounds_is_not_the_feature_collection_bounds(ctx):
    """`fc.bounds()` is a different node from `fc.geometry().bounds()`."""
    assert ctx.bounds.serialize() != ee.FeatureCollection(ASSET).bounds().serialize()


def test_analysis_scale_is_stored(ctx):
    assert ctx.analysis_scale == 300


def test_context_is_frozen(ctx):
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.analysis_scale = 10


def test_from_feature_collection(ee_offline):
    collection = ee.FeatureCollection(ASSET)
    built = ExecutionContext.from_feature_collection(collection, 10)
    assert built.analysis_scale == 10
    assert built.feature_collection.serialize() == collection.serialize()


def test_from_aoi_spec_asset_arm(ee_offline):
    built = ExecutionContext.from_aoi_spec(AssetAoi(ASSET, "some aoi"), 300)
    assert built.analysis_scale == 300
    assert built.feature_collection.serialize() == ee.FeatureCollection(ASSET).serialize()


def test_from_aoi_spec_geojson_arm(ee_offline):
    built = ExecutionContext.from_aoi_spec(GeoJsonAoi(GEOJSON, "drawn"), 100)
    assert built.analysis_scale == 100
    assert built.feature_collection.serialize() == ee.FeatureCollection(GEOJSON).serialize()


def test_from_aoi_spec_rejects_an_unknown_arm(ee_offline):
    class NotAnAoi:
        pass

    with pytest.raises(SpecError, match="unsupported aoi"):
        ExecutionContext.from_aoi_spec(NotAnAoi(), 300)
