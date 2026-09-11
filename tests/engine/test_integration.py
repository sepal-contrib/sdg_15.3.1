"""Graph-shape tests for sdg1531.engine.integration (legacy integration.py)."""

from __future__ import annotations

import re

import pytest

from sdg1531.engine.integration import (
    _VI_BUILDERS,
    build_climate_collection,
    build_vi_collection,
)
from sdg1531.enums import VegetationIndex
from sdg1531.errors import SpecError
from sdg1531.resolve import ViProcessor, resolve
from sdg1531.spec import PrecomputedViAsset, SensorSelection
from tests.engine.conftest import make_resolved
from tests.engine.graph import (
    _call,
    _deref_for,
    _loaded_asset_ids,
    _renamed_bands,
    _root,
    _select_bands_of,
    _string_list_arg,
    _walk,
    count_calls,
    encoded,
)
from tests.spec_factory import default_spec

MODIS_MOD = "MODIS/061/MOD13Q1"
MODIS_MYD = "MODIS/061/MYD13Q1"
NPP = "MODIS/006/MOD17A3HGF"
S2 = "COPERNICUS/S2_SR_HARMONIZED"
L4 = "LANDSAT/LT04/C02/T1_L2"
L8 = "LANDSAT/LC08/C02/T1_L2"
L9 = "LANDSAT/LC09/C02/T1_L2"
DERIVED_NDVI = "LANDSAT/COMPOSITES/C02/T1_L2_32DAY_NDVI"
DERIVED_EVI = "LANDSAT/COMPOSITES/C02/T1_L2_32DAY_EVI"

# integration.py:387 and :401, character for character. Both legacy MSVI builders
# spell the same expression; only the two bands they bind it over differ, which is
# why the two tests below share this constant.
MSVI_EXPRESSION = "(2 * nir + 1 - sqrt(pow((2 * nir + 1), 2) - 8 * (nir - red)) ) / 2"


def _vi_expressions(obj) -> list[tuple[str, dict[str, str]]]:
    """Every `Image.expression` in the graph, as (expression text, {var: band}).

    `ee` compiles `img.expression(text, vars)` into TWO nodes: an
    `Image.parseExpression` holding the text and the variable names, and an
    invocation of that node whose arguments bind each name to the image it was
    handed. Neither half alone is the claim -- the text without the bindings does
    not say which band is `nir`, and the bindings without the text do not say what
    was computed -- so this reads them together.

    The first entry of `vars` is the expression's own image argument
    (`DEFAULT_EXPRESSION_IMAGE`), which is bound to the whole input rather than to a
    band; it is named by `argName` and dropped here rather than guessed at.
    """
    deref, graph, root = _root(obj)
    values = graph.get("values", {})
    found: list[tuple[str, dict[str, str]]] = []
    for current in _walk(root, deref, graph):
        call = _call(current)
        if call is None or "functionReference" not in call:
            continue
        target = _call(deref(values.get(call["functionReference"], {})))
        if target is None or target.get("functionName") != "Image.parseExpression":
            continue
        arguments = target["arguments"]
        text = deref(arguments["expression"]).get("constantValue")
        image_arg = deref(arguments["argName"]).get("constantValue")
        bands = {}
        for name in _string_list_arg(deref(arguments["vars"]), deref):
            if name == image_arg:
                continue
            selected = _select_bands_of(deref(call["arguments"][name]), deref)
            bands[name] = selected[0] if selected and len(selected) == 1 else selected
        found.append((text, bands))
    return found


def _merged_asset_order(obj) -> list[str]:
    """The order `_process_landsat_sensors` merged sensors in, first to last.

    `a.merge(b).merge(c)` nests as `merge(merge(a, b), c)` -- `collection1` is
    the receiver, `collection2` the newly merged-in side (verified against a
    hand-built `ee.ImageCollection([]).merge(a).merge(b)`).
    """
    deref, graph = _deref_for(obj)

    def call_name(node):
        call = _call(deref(node))
        return call.get("functionName") if call is not None else None

    def first_loaded_id(node):
        for current in _walk(node, deref, graph):
            call = _call(current)
            if call is not None and call.get("functionName") in (
                "ImageCollection.load",
                "Image.load",
            ):
                id_arg = deref(call.get("arguments", {}).get("id", {}))
                constant = id_arg.get("constantValue") if isinstance(id_arg, dict) else None
                if isinstance(constant, str):
                    return constant
        return None

    def find_merge_chain(node):
        order = []
        current = deref(node)
        while call_name(current) == "ImageCollection.merge":
            args = current["functionInvocationValue"]["arguments"]
            order.append(first_loaded_id(args["collection2"]))
            current = deref(args["collection1"])
        return order  # outermost (last merged) first

    def find_first_merge(node):
        for current in _walk(node, deref, graph):
            if call_name(current) == "ImageCollection.merge":
                return current
        return None

    merge_root = find_first_merge({"valueReference": graph["result"]})
    if merge_root is None:
        return []
    return list(reversed(find_merge_chain(merge_root)))


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
    # Not a bare `'"year"' in graph` check: `ee.Filter.calendarRange(year,
    # field="year")` and `.set("year", year)` both put "year" in the graph
    # too, so that would still pass with the `.rename("year")` constant-band
    # rename deleted -- which is the thing this line means to test.
    assert "year" in _renamed_bands(coll)
    assert count_calls(coll, "ImageCollection.load") == 1
    # `.filterBounds()`/`.filterDate()` are Python-side sugar over `.filter()`
    # (ee/collection.py) -- they never emit a node under their own name, so
    # `Collection.filterBounds` is always 0 and this assertion could not pass
    # for any correct transcription. `Filter.intersects` is what filterBounds
    # actually compiles to here. This is presence-only, not exact: it goes
    # 1 -> 0 if `.filterBounds()` is removed (which is what makes it
    # load-bearing), but a duplicated `.filterBounds()` call also yields 1,
    # since both calls serialize to the same node.
    assert count_calls(coll, "Filter.intersects") == 1


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

    coll = build_vi_collection(r, ctx)

    # integration.py:398-407 -- MODIS msvi reads sur_refl_b01/b02, not Red/NIR.
    # Equality on the whole extraction, not two substring hits: `"sur_refl_b01" in
    # graph` also passes for an expression that reads the band and does nothing
    # with it, or that binds it to the wrong variable.
    assert _vi_expressions(coll) == [
        (MSVI_EXPRESSION, {"nir": "sur_refl_b02", "red": "sur_refl_b01"})
    ]


@pytest.mark.parametrize("sensors", [("Sentinel 2",), ("Landsat 8", "Landsat 9")])
def test_non_modis_msvi_is_the_transcribed_expression_over_red_and_nir(ctx, sensors):
    """`_calculate_msvi` (integration.py:386-395), which nothing else reaches.

    Its MODIS twin is covered twice over -- by the test above and by parity row s06
    -- but the non-MODIS builder is verified by neither. The corpus asks for all
    eighteen sensor x index pairs, yet every `msvi` row that is not MODIS carries a
    land-cover/water combination the legacy refuses, so stage A recorded a crash for
    it and there is no graph pair: `(sentinel2, msvi)`, `(landsat_pair, msvi)` and
    `(derived_vi, msvi)` reach no comparison at all. That left a hand-typed
    60-character expression string -- exactly the kind of transcription a
    byte-for-byte port has to protect -- with no verification of any kind.

    Both rungs that call it are covered, because `_process_sentinel2` and
    `_process_landsat_sensors` reach it through separate call sites
    (integration.py:550 and :524). This proves it against the transcription, not
    against the legacy; only moving a row onto a compared scenario would do that,
    and that means re-recording goldens.
    """
    r = make_resolved(
        vi_source=SensorSelection(names=sensors),
        vegetation_index=VegetationIndex.MSVI,
    )

    coll = build_vi_collection(r, ctx)

    assert _vi_expressions(coll) == [(MSVI_EXPRESSION, {"nir": "NIR", "red": "Red"})]


def test_the_two_msvi_builders_differ_only_in_the_bands_they_read(ctx):
    """The invariant that makes one of them easy to edit and forget.

    `_calculate_msvi` and `_calculate_msvi_modis` are two copies of one formula over
    two band vocabularies. Pinning each separately lets them drift apart silently;
    this says the text is the SAME text and the bands are the ones that differ.
    """
    landsat = make_resolved(
        vi_source=SensorSelection(names=("Landsat 8",)),
        vegetation_index=VegetationIndex.MSVI,
    )
    modis = make_resolved(
        vi_source=SensorSelection(names=("MODIS MOD13Q1",)),
        vegetation_index=VegetationIndex.MSVI,
    )

    [(landsat_text, landsat_bands)] = _vi_expressions(build_vi_collection(landsat, ctx))
    [(modis_text, modis_bands)] = _vi_expressions(build_vi_collection(modis, ctx))

    assert landsat_text == modis_text == MSVI_EXPRESSION
    assert landsat_bands != modis_bands
    assert set(landsat_bands) == set(modis_bands) == {"nir", "red"}


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
    # The name promises ORDER, not just presence: assert the actual nesting
    # (Landsat 8 merged first / innermost, Landsat 9 second / outermost),
    # not merely that both ids and two merge nodes exist.
    assert _merged_asset_order(coll) == [L8, L9]


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


def test_precomputed_vi_asset_is_rejected(ctx):
    # integration.py:79-80's "GEE Asset" branch is dropped; the replacement arm
    # is not wired in phase 1.
    r = make_resolved(vi_source=PrecomputedViAsset("users/x/vi", 30))

    with pytest.raises(SpecError):
        build_vi_collection(r, ctx)


@pytest.mark.parametrize(
    "sensors",
    [("MODIS MOD13Q1",), ("Sentinel 2",), ("Landsat 8",), ("Derived VI Landsat",)],
)
def test_an_unset_threshold_raises_on_every_rung_that_consumes_it(ctx, sensors):
    """The module's EXPECTED_DIVERGENCES note, pinned.

    `vi_threshold` (integration.py:410-415) calls `img.gt(threshold)`
    unconditionally, and `ee.Image.gt(None)` builds a node with its `image2`
    argument simply absent -- so the legacy shipped a silently broken graph.
    `require_float` raises instead, and this is the only test that says so.
    """
    r = make_resolved(vi_source=SensorSelection(names=sensors), threshold=None)

    with pytest.raises(SpecError, match=re.escape("spec.threshold")):
        build_vi_collection(r, ctx)


def test_terra_npp_still_builds_without_a_threshold(ctx):
    """The narrowing is at the point of consumption, not at the top of the ladder:
    `process_terra_npp` (integration.py:134-142) takes no threshold argument, so a
    Terra NPP spec the legacy ran must not start raising."""
    r = make_resolved(vi_source=SensorSelection(names=("Terra NPP",)), threshold=None)

    assert NPP in _loaded_asset_ids(build_vi_collection(r, ctx))


def test_year_band_is_present_only_on_the_non_monthly_annual_paths(ctx):
    # integration.py:154-157 (_annual_mean_via_monthly's docstring) documents
    # that _annual_mean/_annual_npp emit a `year` BAND (via addBands) while
    # the Landsat/Sentinel monthly path emits only the `year` PROPERTY.
    # Nothing pinned that asymmetry before this test.
    modis = make_resolved(vi_source=SensorSelection(names=("MODIS MOD13Q1",)))
    landsat = make_resolved(vi_source=SensorSelection(names=("Landsat 8",)))

    assert "year" in _renamed_bands(build_vi_collection(modis, ctx))
    assert "year" not in _renamed_bands(build_vi_collection(landsat, ctx))


# (selection, the rung resolve() lands it on, the asset ids that rung LOADS).
#
# `resolve()` hands every rung the whole per-sensor asset tuple, and the rungs
# consume different amounts of it (integration.py): `process_modis` reads
# ee_asset_list[0] and, when more than one sensor was selected, [1] -- never [2]
# (:106-111); `process_terra_npp` (:136) and the Sentinel 2 (:59) and derived-VI
# (:67-71) rungs read [0] alone; only `process_landsat_sensors` zips the whole
# list (:149-162). Those arities are the behaviour this table pins.
#
# The third column is written out as LITERAL ids and not recomputed from
# `r.vi_assets`, which is the whole point: a helper applying the same
# per-rung rule the engine applies would agree with the engine by construction
# and could not fail. Every id here is off the graph the engine actually built.
CONSUMED_ASSETS = [
    (("MODIS MOD13Q1",), ViProcessor.MODIS, {MODIS_MOD}),
    (("MODIS MYD13Q1",), ViProcessor.MODIS, {MODIS_MYD}),
    (("MODIS MOD13Q1", "MODIS MYD13Q1"), ViProcessor.MODIS, {MODIS_MOD, MODIS_MYD}),
    # The MODIS rung's arity, stated: L8 is vi_assets[2], process_modis never
    # indexes past [1], so L8 must be ABSENT from the graph even though
    # resolve() lists it. Same selection as test_modis_wins_the_ladder_over_landsat.
    (("MODIS MOD13Q1", "MODIS MYD13Q1", "Landsat 8"), ViProcessor.MODIS, {MODIS_MOD, MODIS_MYD}),
    (("Terra NPP",), ViProcessor.TERRA_NPP, {NPP}),
    (("Sentinel 2",), ViProcessor.SENTINEL2, {S2}),
    # Exactly one: the derived-VI rung takes the single id resolve() already
    # picked between the (ndvi, evi) pair, so the EVI composite is not loaded.
    (("Derived VI Landsat",), ViProcessor.DERIVED_VI_LANDSAT, {DERIVED_NDVI}),
    (("Landsat 4",), ViProcessor.LANDSAT_SENSORS, {L4}),
    # The Landsat rung is the one that reads EVERY element.
    (("Landsat 8", "Landsat 9"), ViProcessor.LANDSAT_SENSORS, {L8, L9}),
    # Widget-unreachable (sensor_select.py:82-84 DOES block mixing MODIS and
    # Landsat, unlike the Derived-VI-Landsat case), but SensorSelection itself
    # does not prevent constructing it, and resolve (test_resolve.py:287) pins
    # this EXACT order as the ladder's precedence proof: ee_asset_list[0] is
    # Landsat 8's id, a plain string, so the legacy defect at integration.py:
    # 67-71 indexes a single CHARACTER of it -- and "L" is what ee is asked to
    # load. Nothing but the graph itself would show that.
    (("Landsat 8", "Derived VI Landsat"), ViProcessor.DERIVED_VI_LANDSAT, {"L"}),
    (("Derived VI Landsat", "Landsat 8"), ViProcessor.DERIVED_VI_LANDSAT, {DERIVED_NDVI}),
    # A non-derived rung winning while "Derived VI Landsat" rides along:
    # vi_assets[1] is the (ndvi, evi) PAIR, unresolved, and process_modis hands
    # that pair straight to ee.ImageCollection -- which loads BOTH ids as
    # images. Three loads off a two-sensor selection.
    (
        ("MODIS MOD13Q1", "Derived VI Landsat"),
        ViProcessor.MODIS,
        {MODIS_MOD, DERIVED_NDVI, DERIVED_EVI},
    ),
]


@pytest.mark.parametrize(("sensor_names", "processor", "loaded"), CONSUMED_ASSETS)
def test_each_rung_loads_exactly_the_assets_it_consumes(sensor_names, processor, loaded, ctx):
    """Per-rung consumption arity, read off the graph the engine encoded.

    Every other test in this file hands build_vi_collection the make_resolved()
    stub; this one runs the real resolve(), so the row's claim covers the whole
    path a run takes -- the rung resolve() picks, the assets it resolves, and
    how much of them the engine then puts into the graph.

    The processor assertion is not decoration: it is what entitles the row to
    speak for a rung. Without it a selection that silently changed rungs would
    go on passing against an asset set that no longer describes the rung named.
    """
    spec = default_spec(vi_source=SensorSelection(names=sensor_names), threshold=0.0)
    r = resolve(spec)

    assert r.vi_processor is processor

    actual = _loaded_asset_ids(build_vi_collection(r, ctx))

    assert actual == loaded, (
        f"the {processor.value} rung, handed vi_assets={r.vi_assets!r} for "
        f"sensors {sensor_names}, should load exactly {loaded!r} but loaded {actual!r}"
    )


def test_every_rung_that_builds_a_graph_has_a_consumption_row():
    """PRECOMPUTED is the one rung that raises instead of building; the rest must
    each be exercised above, or a rung added later inherits no arity check."""
    covered = {processor for _, processor, _ in CONSUMED_ASSETS}

    assert covered == set(ViProcessor) - {ViProcessor.PRECOMPUTED}
