"""The land-cover degradation stack. Transcribed from component/scripts/land_cover.py:6-111.

Every assertion here reads a specific argument out of the serialized graph rather
than looking for a substring: `"100" in graph` also matches a year, a scale and
any longer number, and `Image.remap` in the graph says nothing about WHICH table
went into WHICH argument.

The stub `ResolvedSpec` (tests/engine/conftest.py) is used deliberately over real
`resolve()` output for the shape tests: its `lc_class_combinations` /
`trans_matrix_flatten` stand-ins are short and unlike each other, so a builder
that swapped the two remap arguments is visible. One test at the bottom runs the
real `resolve()` to pin the other half -- that the years come from the LAND-COVER
sub-period rather than from `overall`.
"""

from __future__ import annotations

import dataclasses
from dataclasses import replace

import ee
import pytest

from sdg1531.catalog import ASSETS, INT16_MIN
from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.land_cover import LandCoverMaps, build_land_cover
from sdg1531.resolve import resolve
from sdg1531.spec import CustomLandCoverSource, EsaCciSource, PeriodOverride, PixelValueMask
from sdg1531.tables import TRANSLATION_MATRIX
from tests.engine.conftest import (
    STUB_CLASS_COMBINATIONS,
    STUB_TRANS_MATRIX_FLATTEN,
    make_resolved,
)
from tests.engine.graph import (
    _calendar_windows,
    _call,
    _image_constant,
    _loaded_asset_ids,
    _loaded_assets_in,
    _root,
    _spine,
    _spine_band,
    _spine_functions,
    _string_list_arg,
    _walk,
)
from tests.spec_factory import DEFAULT_PERIODS, default_spec

CCI_IC = ASSETS["land_cover_ic"]
JRC = ASSETS["jrc_water"]

# Distinct, non-degenerate and different from conftest's 2001/2015 defaults, so a
# builder that read the wrong year field -- or the same field twice -- shows up as
# a different calendarRange window rather than as an identical one.
LC_START = 1998
LC_END = 2012

CUSTOM = CustomLandCoverSource(
    start_asset="users/test/custom_start", end_asset="users/test/custom_end"
)


def stack_for(**overrides):
    """The stack for a stub resolved spec, with the CCI years set explicitly."""
    years = {"lc_year_start_esa": LC_START, "lc_year_end_esa": LC_END}
    r = make_resolved(**{**years, **overrides})
    ctx = ExecutionContext.from_feature_collection(ee.FeatureCollection("users/test/aoi"), 250)
    return build_land_cover(r, ctx)


# --- graph helpers ------------------------------------------------------------

# The argument each node on THIS module's chains carries its receiver in, verified
# against the encoder. Passed to the shared spine walkers; test_productivity.py
# keeps its own table, which lists a different set of functions.
_RECEIVER_ARG = {
    "Image.rename": "input",
    "Image.uint16": "value",
    "Image.remap": "image",
    "Image.clip": "input",
    "Image.select": "input",
    "Image.selfMask": "image",
}


def spine(node, deref):
    return _spine(node, deref, _RECEIVER_ARG)


def spine_functions(node, deref):
    return _spine_functions(node, deref, _RECEIVER_ARG)


def spine_band(node, deref):
    return _spine_band(node, deref, _RECEIVER_ARG)


def band_order(stack):
    """The band names of the `addBands` chain, in stack order.

    `a.addBands(b).addBands(c)` nests as `addBands(addBands(a, b), c)`, so the
    receiver (`dstImg`) is everything added so far and `srcImg` is the new band.
    """
    deref, graph, _root_node = _root(stack)
    bands = []

    def walk(node):
        node = deref(node)
        call = _call(node)
        if call and call.get("functionName") == "Image.addBands":
            walk(call["arguments"]["dstImg"])
            bands.append(spine_band(call["arguments"]["srcImg"], deref))
        else:
            bands.append(spine_band(node, deref))

    walk({"valueReference": graph["result"]})
    return bands


def stack_operands(stack):
    """`{band name: [function names on its receiver spine]}` for the five bands."""
    deref, graph, _root_node = _root(stack)
    operands = {}

    def walk(node):
        node = deref(node)
        call = _call(node)
        if call and call.get("functionName") == "Image.addBands":
            walk(call["arguments"]["dstImg"])
            src = deref(call["arguments"]["srcImg"])
            operands[spine_band(src, deref)] = spine_functions(src, deref)
        else:
            operands[spine_band(node, deref)] = spine_functions(node, deref)

    walk({"valueReference": graph["result"]})
    return operands


def band_subtree(stack, band):
    """`(deref, graph, node)` for the single `Image.rename` to `band`.

    Raises when the band is missing or ambiguous: an assertion written against a
    subtree that silently came back empty would pass vacuously.
    """
    deref, graph, root = _root(stack)
    found = [
        node
        for node in _walk(root, deref, graph)
        if (call := _call(node)) is not None
        and call.get("functionName") == "Image.rename"
        and _string_list_arg(deref(call["arguments"]["names"]), deref) == [band]
    ]
    if len(found) != 1:
        raise AssertionError(f"expected exactly one rename to {band!r}, found {len(found)}")
    return deref, graph, found[0]


def remaps_on_spine(deref, node):
    """`[(from, to)]` for every `Image.remap` on `node`'s receiver spine, outermost first."""
    found = []
    for current in spine(node, deref):
        call = _call(current)
        if call is None or call.get("functionName") != "Image.remap":
            continue
        args = call["arguments"]
        found.append(
            (
                tuple(deref(args["from"]).get("constantValue")),
                tuple(deref(args["to"]).get("constantValue")),
            )
        )
    return found


# --- the stack ----------------------------------------------------------------


def test_build_land_cover_returns_land_cover_maps():
    assert isinstance(stack_for(), LandCoverMaps)


def test_stack_band_order_is_degradation_transition_start_end_water():
    """land_cover.py:104-109."""
    assert band_order(stack_for().stack) == [
        "degradation",
        "transition",
        "start",
        "end",
        "water",
    ]


def test_land_cover_maps_is_frozen():
    maps = stack_for()
    with pytest.raises(dataclasses.FrozenInstanceError):
        maps.stack = ee.Image(0)


@pytest.mark.parametrize("band", ["degradation", "transition", "water"])
def test_each_property_selects_its_own_band(band):
    """The property must be the OUTERMOST select: the stack's own graph already
    contains a `.select("seasonality")` from the JRC water branch, so a set of
    every select in the graph could not tell these apart."""
    maps = stack_for()
    deref, _graph, root = _root(getattr(maps, band))
    call = _call(root)

    assert call is not None and call["functionName"] == "Image.select"
    assert _string_list_arg(deref(call["arguments"]["bandSelectors"]), deref) == [band]


def test_every_stack_band_is_cast_to_uint16():
    """land_cover.py:100, :105-108 -- `degradation` casts before its rename, the
    other four cast as they are added."""
    for band, spine in stack_operands(stack_for().stack).items():
        assert "Image.uint16" in spine, f"{band} is not cast to uint16: {spine}"


# --- the CCI branch -----------------------------------------------------------


def test_esa_source_loads_only_the_cci_collection_and_the_water_asset():
    assert _loaded_asset_ids(stack_for().stack) == {CCI_IC, JRC}


def test_each_cci_image_filters_on_its_own_year():
    """land_cover.py:17-37. Asserted per band, not as one set over the whole graph:
    a set would be identical if both images filtered on the start year and the end
    year merely appeared somewhere else."""
    stack = stack_for().stack

    deref, graph, node = band_subtree(stack, "start")
    assert _calendar_windows(node, deref, graph) == {(LC_START, LC_START)}
    deref, graph, node = band_subtree(stack, "end")
    assert _calendar_windows(node, deref, graph) == {(LC_END, LC_END)}


def test_the_cci_years_are_clamped_to_the_collection_s_own_range():
    """resolve.py:241-242 clamps both endpoints to the CCI collection's coverage
    (indicator_model.py:156-168). Asserted through `resolve()` because the clamp is
    the reason the builder reads `lc_year_*_esa` rather than `land_cover_period`,
    which the stub cannot distinguish."""
    periods = replace(DEFAULT_PERIODS, land_cover=PeriodOverride(1980, 2050))
    r = resolve(default_spec(periods=periods, land_cover=EsaCciSource()))
    ctx = ExecutionContext.from_feature_collection(ee.FeatureCollection("users/test/aoi"), 250)
    stack = build_land_cover(r, ctx).stack

    deref, graph, node = band_subtree(stack, "start")
    assert _calendar_windows(node, deref, graph) == {(1992, 1992)}
    deref, graph, node = band_subtree(stack, "end")
    assert _calendar_windows(node, deref, graph) == {(2022, 2022)}


@pytest.mark.parametrize("band", ["start", "end"])
def test_each_cci_image_is_clipped_to_the_aoi_bounding_box(band):
    """land_cover.py:10 clips to `geometry().bounds()`, not to the geometry itself
    -- a rectangle around the AOI, which is what makes the CCI images cheap to
    fetch and is why `ExecutionContext` exposes the two separately."""
    deref, _graph, node = band_subtree(stack_for().stack, band)

    clips = [
        call
        for current in spine(node, deref)
        if (call := _call(current)) is not None and call.get("functionName") == "Image.clip"
    ]
    assert len(clips) == 1
    assert _call(deref(clips[0]["arguments"]["geometry"]))["functionName"] == "Geometry.bounds"


def test_esa_source_remaps_through_the_translation_matrix():
    """land_cover.py:48-55 -- `from` is the 37 ESA class codes, `to` the IPCC codes."""
    stack = stack_for().stack
    expected = (tuple(TRANSLATION_MATRIX[0]), tuple(TRANSLATION_MATRIX[1]))

    for band in ("start", "end"):
        deref, _graph, node = band_subtree(stack, band)
        assert remaps_on_spine(deref, node) == [expected]


# --- the custom-asset branch --------------------------------------------------


def test_custom_source_uses_the_user_assets_raw():
    """land_cover.py:40-43 -- user assets are NOT put through TRANSLATION_MATRIX,
    so no remap sits between the asset and the `start`/`end` bands."""
    stack = stack_for(land_cover=CUSTOM, water_mask=PixelValueMask(33)).stack

    for band, asset in (("start", CUSTOM.start_asset), ("end", CUSTOM.end_asset)):
        deref, graph, node = band_subtree(stack, band)
        assert _loaded_assets_in(node, deref, graph) == {asset}
        assert remaps_on_spine(deref, node) == []


def test_the_cci_collection_is_absent_from_a_custom_source_graph():
    """land_cover.py:17-37 builds `landcover_start`/`landcover_end` unconditionally,
    but an unreferenced ee object is never serialized, and branch 1 of the water
    mask pre-empts the only arm that would have referenced the raw end image."""
    stack = stack_for(land_cover=CUSTOM, water_mask=PixelValueMask(33)).stack

    assert _loaded_asset_ids(stack) == {CUSTOM.start_asset, CUSTOM.end_asset}


# --- transition and degradation -----------------------------------------------


def test_transition_is_the_start_map_times_one_hundred_plus_the_end_map():
    """land_cover.py:84-88. The START map carries the leading two digits; exchanging
    the operands builds an equally valid graph that decodes every transition
    backwards, so both the factor and WHICH side it multiplies are pinned."""
    stack = stack_for().stack
    deref, _graph, node = band_subtree(stack, "transition")

    add = _call(deref(_call(node)["arguments"]["input"]))
    assert add["functionName"] == "Image.add"

    multiply = _call(deref(add["arguments"]["image1"]))
    assert multiply["functionName"] == "Image.multiply"
    assert _image_constant(deref(multiply["arguments"]["image2"]), deref) == 100

    assert spine_band(multiply["arguments"]["image1"], deref) == "start"
    assert spine_band(add["arguments"]["image2"], deref) == "end"


def test_degradation_remaps_the_scheme_tables_then_the_byte_convention():
    """land_cover.py:92-102, innermost first: the transition codes go through the
    scheme's own two tables, then -1/0/1 are renumbered to the 1/2/3 byte
    convention. The INT16_MIN -> 0 entry is unreachable -- the first remap has no
    defaultValue, so unmatched pixels are masked, not set to INT16_MIN -- and is
    transcribed as found, so the graph stays byte-identical."""
    stack = stack_for().stack
    deref, _graph, node = band_subtree(stack, "degradation")

    assert remaps_on_spine(deref, node) == [
        ((1, 0, -1, INT16_MIN), (3, 2, 1, 0)),
        (STUB_CLASS_COMBINATIONS, STUB_TRANS_MATRIX_FLATTEN),
    ]


# --- the water band's wiring --------------------------------------------------


def test_the_esa_water_branch_reads_the_raw_end_image_not_the_remapped_one():
    """land_cover.py:65-66 against :53-55. Both images exist in this graph, so this
    is the one wiring mistake the branch table in test_water_mask.py cannot catch:
    there the two are separate assets, here they are two chains off the same
    collection and only the band name tells them apart."""
    stack = stack_for(water_mask=PixelValueMask(70)).stack
    deref, graph, root = _root(stack)

    eq_nodes = [
        call
        for node in _walk(root, deref, graph)
        if (call := _call(node)) is not None and call.get("functionName") == "Image.eq"
    ]
    # exactly 1: the water mask is the only branch in the whole stack that
    # compares anything, and its pixel-value arm emits a single `Image.eq`. The
    # two remaps and the multiply/add carry no comparison. Guards the [0] below.
    assert len(eq_nodes) == 1

    assert spine_band(eq_nodes[0]["arguments"]["image1"], deref) == "landcover_end"


# --- the real resolve() -------------------------------------------------------


def test_the_cci_years_come_from_the_land_cover_sub_period_not_the_overall_one():
    """`resolve()` derives `lc_year_start_esa` / `lc_year_end_esa` from
    `periods.land_cover` (resolve.py:212, :241-242). The override and `overall` are
    given four different years, so a builder -- or a derivation -- reading the
    wrong one lands a different window in the graph."""
    periods = replace(DEFAULT_PERIODS, land_cover=PeriodOverride(1995, 2010))
    assert (DEFAULT_PERIODS.overall.start, DEFAULT_PERIODS.overall.end) == (2000, 2020)

    r = resolve(default_spec(periods=periods, land_cover=EsaCciSource()))
    ctx = ExecutionContext.from_feature_collection(ee.FeatureCollection("users/test/aoi"), 250)
    stack = build_land_cover(r, ctx).stack

    deref, graph, node = band_subtree(stack, "start")
    assert _calendar_windows(node, deref, graph) == {(1995, 1995)}
    deref, graph, node = band_subtree(stack, "end")
    assert _calendar_windows(node, deref, graph) == {(2010, 2010)}
