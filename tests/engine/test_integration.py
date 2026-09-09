"""Graph-shape tests for sdg1531.engine.integration (legacy integration.py)."""

from __future__ import annotations

import json

import ee
import pytest

from sdg1531.engine.integration import (
    _VI_BUILDERS,
    build_climate_collection,
    build_vi_collection,
)
from sdg1531.enums import VegetationIndex
from sdg1531.errors import SpecError
from sdg1531.resolve import resolve
from sdg1531.spec import PrecomputedViAsset, SensorSelection
from tests.engine.conftest import make_resolved
from tests.spec_factory import default_spec

MODIS_MOD = "MODIS/061/MOD13Q1"
MODIS_MYD = "MODIS/061/MYD13Q1"
NPP = "MODIS/006/MOD17A3HGF"
S2 = "COPERNICUS/S2_SR_HARMONIZED"
L8 = "LANDSAT/LC08/C02/T1_L2"
L9 = "LANDSAT/LC09/C02/T1_L2"
DERIVED_NDVI = "LANDSAT/COMPOSITES/C02/T1_L2_32DAY_NDVI"
DERIVED_EVI = "LANDSAT/COMPOSITES/C02/T1_L2_32DAY_EVI"


def encoded(obj) -> str:
    """The serialized graph as one string, for substring assertions."""
    return json.dumps(ee.serializer.encode(obj), sort_keys=True)


def count_calls(obj, function_name: str) -> int:
    """Count DISTINCT nodes invoking `function_name`.

    The ee serializer collapses structurally identical subtrees into a single
    scope entry, so this counts distinct nodes, not textual occurrences.
    """
    graph = ee.serializer.encode(obj)
    total = 0
    stack = [graph]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            call = node.get("functionInvocationValue")
            if isinstance(call, dict) and call.get("functionName") == function_name:
                total += 1
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return total


def test_vi_builders_cover_every_vegetation_index():
    # The reflective globals()[f"calculate_{vi_index}"] of integration.py:165,193
    # became an explicit table; adding an enum member without an entry must fail.
    assert set(_VI_BUILDERS) == set(VegetationIndex)


def test_climate_collection_loads_persiann_over_the_integration_period(resolved, ctx):
    coll = build_climate_collection(resolved, ctx)

    graph = encoded(coll)
    assert "NOAA/PERSIANN-CDR" in graph
    assert '"2001-01-01"' in graph
    assert '"2015-12-31"' in graph
    assert '"clim"' in graph
    assert '"year"' in graph
    assert count_calls(coll, "ImageCollection.load") == 1
    # `.filterBounds()`/`.filterDate()` are Python-side sugar over `.filter()`
    # (ee/collection.py) -- they never emit a node under their own name, so
    # `Collection.filterBounds` is always 0 and this assertion could not pass
    # for any correct transcription. `Filter.intersects` is what filterBounds
    # actually compiles to here, and it goes 1 -> 0 if `.filterBounds()` is
    # removed, which is what makes it load-bearing.
    assert count_calls(coll, "Filter.intersects") == 1
    assert count_calls(coll, "Reducer.mean") == 1


def test_modis_wins_the_ladder_over_landsat(ctx):
    # integration.py:45 tests the MODIS set FIRST, so a mixed selection that
    # sensor_select.py:82-84 does not block still takes the MODIS branch.
    #
    # Three sensors, not the more obvious two: process_modis (integration.py:
    # 106-111) merges ee_asset_list[1] whenever `len(sensor_list) > 1`, with
    # NO check that the second sensor is actually MODIS -- the comment above
    # that line ("merge the collection if both the MODIS sensors are
    # selected") does not match what the code tests. So a genuine two-sensor
    # ("MODIS MOD13Q1", "Landsat 8") selection faithfully pulls L8's asset id
    # into the graph; a correct transcription cannot assert `L8 not in graph`
    # for that input. Putting Landsat 8 in the selection's third slot instead
    # keeps it out of both ee_asset_list[0] and [1] (the only two indices
    # process_modis ever touches), so it proves the same ladder-precedence
    # point -- MODIS wins despite Landsat being present -- without hitting
    # that defect. Do not "simplify" this back to two sensors.
    r = make_resolved(
        vi_source=SensorSelection(names=("MODIS MOD13Q1", "MODIS MYD13Q1", "Landsat 8"))
    )

    graph = encoded(build_vi_collection(r, ctx))

    assert MODIS_MOD in graph
    assert MODIS_MYD in graph
    assert L8 not in graph


def test_two_modis_sensors_are_merged(ctx):
    r = make_resolved(vi_source=SensorSelection(names=("MODIS MOD13Q1", "MODIS MYD13Q1")))

    coll = build_vi_collection(r, ctx)
    graph = encoded(coll)

    assert MODIS_MOD in graph
    assert MODIS_MYD in graph
    assert count_calls(coll, "ImageCollection.merge") == 1


def test_modis_ndvi_scales_by_ten_thousandths(ctx):
    r = make_resolved(
        vi_source=SensorSelection(names=("MODIS MOD13Q1",)),
        vegetation_index=VegetationIndex.NDVI,
    )

    graph = encoded(build_vi_collection(r, ctx))

    # integration.py:116-118 selects the UPPERCASE band and rescales by 1e-4.
    assert '"NDVI"' in graph
    assert "0.0001" in graph


def test_modis_msvi_uses_the_surface_reflectance_bands(ctx):
    r = make_resolved(
        vi_source=SensorSelection(names=("MODIS MOD13Q1",)),
        vegetation_index=VegetationIndex.MSVI,
    )

    graph = encoded(build_vi_collection(r, ctx))

    # integration.py:398-407 -- MODIS msvi reads sur_refl_b01/b02, not Red/NIR.
    assert "sur_refl_b01" in graph
    assert "sur_refl_b02" in graph


def test_terra_npp_takes_the_first_image_per_year(ctx):
    r = make_resolved(vi_source=SensorSelection(names=("Terra NPP",)))

    coll = build_vi_collection(r, ctx)
    graph = encoded(coll)

    assert NPP in graph
    assert '"Npp"' in graph
    assert count_calls(coll, "Collection.first") == 1


def test_sentinel2_filters_on_cloudy_pixel_percentage(ctx):
    r = make_resolved(vi_source=SensorSelection(names=("Sentinel 2",)))

    graph = encoded(build_vi_collection(r, ctx))

    assert S2 in graph
    assert "CLOUDY_PIXEL_PERCENTAGE" in graph
    assert "CLOUD_COVER_LAND" not in graph
    assert '"QA60"' in graph


def test_landsat_sensors_are_merged_in_selection_order(ctx):
    r = make_resolved(vi_source=SensorSelection(names=("Landsat 8", "Landsat 9")))

    coll = build_vi_collection(r, ctx)
    graph = encoded(coll)

    assert L8 in graph
    assert L9 in graph
    assert "CLOUD_COVER_LAND" in graph
    # ee.ImageCollection([]) seeded, then one merge per sensor: integration.py:149-162
    assert count_calls(coll, "ImageCollection.merge") == 2


def test_derived_vi_ndvi_uses_the_ndvi_asset(ctx):
    r = make_resolved(
        vi_source=SensorSelection(names=("Derived VI Landsat",)),
        vegetation_index=VegetationIndex.NDVI,
    )

    graph = encoded(build_vi_collection(r, ctx))

    assert DERIVED_NDVI in graph
    assert DERIVED_EVI not in graph


def test_derived_vi_beats_landsat_in_a_mixed_selection(ctx):
    # sensor_select.py:82-84 matches on substrings, so ["Derived VI Landsat",
    # "Landsat 8"] reaches integrate_vi. integration.py:66 is tested before
    # :81, and :67-71 indexes ee_asset_list[0], so only the derived composite
    # is loaded and the Landsat SR branch is never taken.
    r = make_resolved(
        vi_source=SensorSelection(names=("Derived VI Landsat", "Landsat 8")),
        vegetation_index=VegetationIndex.NDVI,
    )

    graph = encoded(build_vi_collection(r, ctx))

    assert DERIVED_NDVI in graph
    assert L8 not in graph
    assert "CLOUD_COVER_LAND" not in graph


def test_derived_vi_msvi_is_served_the_evi_asset_by_default(ctx):
    # Preserved defect, spec 7: integration.py:66-71 sends anything that is not
    # ndvi to assets[1], so MSVI silently reads the EVI composite.
    r = make_resolved(
        vi_source=SensorSelection(names=("Derived VI Landsat",)),
        vegetation_index=VegetationIndex.MSVI,
    )

    graph = encoded(build_vi_collection(r, ctx))

    assert DERIVED_EVI in graph
    assert DERIVED_NDVI not in graph


def test_derived_vi_msvi_raises_when_the_compatibility_flag_is_off(ctx):
    from sdg1531.spec import Compatibility

    r = make_resolved(
        vi_source=SensorSelection(names=("Derived VI Landsat",)),
        vegetation_index=VegetationIndex.MSVI,
        compatibility=Compatibility(derived_vi_msvi_uses_evi_asset=False),
    )

    with pytest.raises(SpecError):
        build_vi_collection(r, ctx)


def test_precomputed_vi_asset_is_rejected(ctx):
    # integration.py:79-80's "GEE Asset" branch is dropped; the replacement arm
    # is not wired in phase 1.
    r = make_resolved(vi_source=PrecomputedViAsset("users/x/vi", 30))

    with pytest.raises(SpecError):
        build_vi_collection(r, ctx)


def test_empty_sensor_selection_raises(ctx):
    r = make_resolved(vi_source=SensorSelection(names=()))

    with pytest.raises(SpecError):
        build_vi_collection(r, ctx)


def _asset_ref(asset_id: str) -> str:
    """The exact JSON fragment ee emits when `asset_id` is loaded as the `id`
    argument of `ImageCollection.load` or `Image.load`.

    Plain substring containment is too weak here: resolve.py's preserved
    single-character defect (see below) makes a naive `"L" in graph` check
    pass trivially against almost any graph. Anchoring on the argument shape
    is what makes the cross-check below meaningful rather than vacuous.
    """
    return '"id": {"constantValue": ' + json.dumps(asset_id) + "}"


def _flatten_vi_assets(vi_assets):
    """Flatten ResolvedSpec.vi_assets's `str | tuple[str, str]` shape.

    A mixed selection passes the Derived-VI-Landsat (ndvi, evi) pair through
    NESTED (resolve.py's `ViAsset` type, integration.py:41-43) -- this pulls
    both ids out so every one of them can be checked for individually.
    """
    flat: list[str] = []
    for asset in vi_assets:
        if isinstance(asset, tuple):
            flat.extend(asset)
        else:
            flat.append(asset)
    return flat


@pytest.mark.parametrize(
    "sensor_names",
    [
        ("MODIS MOD13Q1",),
        ("MODIS MYD13Q1",),
        ("MODIS MOD13Q1", "MODIS MYD13Q1"),
        ("Terra NPP",),
        ("Sentinel 2",),
        ("Derived VI Landsat",),
        ("Landsat 4",),
        ("Landsat 8", "Landsat 9"),
        # Widget-unreachable (sensor_select.py:82-84 DOES block mixing MODIS
        # and Landsat, unlike the Derived-VI-Landsat case), but SensorSelection
        # itself does not prevent constructing it, and Task 5
        # (test_resolve.py:284) pins this EXACT order as the ladder's
        # precedence proof: ee_asset_list[0] is Landsat 8's id, a plain
        # string, so the legacy defect at integration.py:67-71 indexes a
        # single CHARACTER of it ("L").
        ("Landsat 8", "Derived VI Landsat"),
        ("Derived VI Landsat", "Landsat 8"),
        # A non-derived rung winning while "Derived VI Landsat" rides along in
        # the same selection: resolve.py's ViAsset passes the (ndvi, evi)
        # pair through NESTED, and integration.py:41-43 hands that exact
        # nested list to process_modis.
        ("MODIS MOD13Q1", "Derived VI Landsat"),
    ],
)
def test_ladder_agrees_with_resolve_s_independent_derivation(sensor_names, ctx):
    # Every other test in this file hands build_vi_collection the
    # make_resolved() stub. This one alone uses the REAL resolve(), because it
    # exists specifically to compare TWO independently written ladders --
    # this module's, and resolve.py's _vi_dispatch -- and a stub standing in
    # for one of them would make the comparison vacuous.
    spec = default_spec(vi_source=SensorSelection(names=sensor_names), threshold=0.0)
    r = resolve(spec)

    graph = encoded(build_vi_collection(r, ctx))

    for asset_id in _flatten_vi_assets(r.vi_assets):
        assert _asset_ref(asset_id) in graph, (
            f"resolve() derived asset {asset_id!r} for sensors {sensor_names}, "
            "but engine.integration's own ladder never referenced it -- the "
            "two independent derivations have diverged"
        )
