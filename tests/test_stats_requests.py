"""Graph-shape tests for the statistics requests. Offline ee (tests/conftest.py).

These assert on the ENCODED graph rather than on substrings of it: which band each
operand carries, which argument of ``reduceRegion`` got which value, and the order
the two operand bands were added in -- that order is what ``group(1, ...)`` and
``group(2, ...)`` index into, so a swap would transpose the whole area table while
leaving every substring in place.

The file's centrepiece is
:func:`test_the_statistics_vocabulary_deliberately_differs_from_the_export_vocabulary`,
which fails if ``_STATS_BAND`` or ``_STATS_LABELS`` is ever "unified" with the engine's
export vocabulary. See ``sdg1531/stats/requests.py``'s docstring for why they must
be allowed to disagree.
"""

import ast
import json

import ee
import pytest
from conftest import REPO_ROOT
from helpers_stats import StubMaps, make_ctx, make_zones
from spec_factory import default_spec

from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.indicator import IndicatorMaps
from sdg1531.engine.land_cover import LandCoverMaps
from sdg1531.enums import IndicatorLayer
from sdg1531.resolve import resolve
from sdg1531.stats import decode as decode_module
from sdg1531.stats import requests as requests_module
from sdg1531.stats.decode import _STATS_LABELS
from sdg1531.stats.requests import (
    _STATS_BAND,
    build_areas_by_land_cover,
    build_band_names,
    build_distinct_pixel_values,
    build_transition_areas,
    build_zonal_areas,
)
from sdg1531.tables import (
    DEGRADATION_LABELS,
    PROD_PERFORMANCE_LABELS,
    PROD_STATE_5_LABELS,
    PROD_TREND_5_LABELS,
)
from tests.engine.graph import (
    _call,
    _loaded_asset_ids,
    _renamed_bands,
    _root,
    _scalar_list_arg,
    _select_bands_of,
    _spine,
    _spine_functions,
    _string_list_arg,
    _walk,
    count_calls,
)

# Which argument holds each function's receiver, for the two spines these tests
# walk: the reducer's own `.group()` nesting, and the operand image's `.addBands()`
# chain. Deliberately short -- a shared table would walk through a function the
# assertion never meant to follow (tests/engine/graph.py).
_RECEIVER_ARG = {
    "Reducer.group": "reducer",
    "Image.addBands": "dstImg",
    "Image.divide": "image1",
}


@pytest.fixture()
def ctx() -> ExecutionContext:
    return make_ctx()


# --- graph readers ------------------------------------------------------------
#
# The whole-graph readers in tests/engine/graph.py (`_selected_bands`,
# `_loaded_asset_ids`, `count_calls`) are imported and used as-is, and the readers
# below delegate to its node-level primitives rather than re-inlining them. What the
# shared readers cannot answer is WHICH operand contributed a given selection: a
# union over the request sees {"start", "state_5_levels"} whether the land cover side
# or the indicator side produced either one. These scope to one subtree, or to one
# node's arguments.


def _constant(deref, arg):
    """The scalar behind an argument node."""
    node = deref(arg)
    assert isinstance(node, dict) and "constantValue" in node, node
    return node["constantValue"]


def _selected_in(node, deref, graph) -> set[str]:
    """Every band name passed to `.select(...)` inside ONE subtree.

    The shared `_selected_bands` answers this for a whole request; only the walk's
    starting point differs, so the per-node extraction is the shared
    `_select_bands_of` rather than a second copy of it.
    """
    names: set[str] = set()
    for current in _walk(node, deref, graph):
        names.update(_select_bands_of(current, deref) or [])
    return names


def _sole_call(obj, function_name):
    """`(deref, graph, arguments)` of the ONE node invoking `function_name`."""
    deref, graph, root = _root(obj)
    found = [
        _call(node)["arguments"]
        for node in _walk(root, deref, graph)
        if (_call(node) or {}).get("functionName") == function_name
    ]
    assert len(found) == 1, f"expected one {function_name}, found {len(found)}"
    return deref, graph, found[0]


def _reducer_groups(deref, args):
    """`([(groupField, groupName), ...], base reducer name)`, outermost group first."""
    groups = []
    base = None
    for node in _spine(deref(args["reducer"]), deref, _RECEIVER_ARG):
        call = _call(node)
        name = call.get("functionName") if call else None
        if name == "Reducer.group":
            groups.append(
                (
                    _constant(deref, call["arguments"]["groupField"]),
                    _constant(deref, call["arguments"]["groupName"]),
                )
            )
        else:
            base = name
    return groups, base


def _added_bands(deref, graph, image_node):
    """The band selections of each `.addBands()` operand, outermost (last added) first."""
    return [
        _selected_in(deref(_call(node)["arguments"]["srcImg"]), deref, graph)
        for node in _spine(image_node, deref, _RECEIVER_ARG)
        if (_call(node) or {}).get("functionName") == "Image.addBands"
    ]


def _divide_constant(deref, image_node):
    """The scalar the pixel-area image is divided by, off the operand image's spine."""
    for node in _spine(image_node, deref, _RECEIVER_ARG):
        call = _call(node)
        if call is not None and call.get("functionName") == "Image.divide":
            denominator = _call(deref(call["arguments"]["image2"]))
            return _constant(deref, denominator["arguments"]["value"])
    raise AssertionError("no Image.divide on the operand image's spine")


def _operand_selections(obj):
    """`(indicator selection, land cover selection)` for an areas-by-land-cover request."""
    deref, graph, args = _sole_call(obj, "Image.reduceRegion")
    added = _added_bands(deref, graph, deref(args["image"]))
    assert len(added) == 2, added
    return added[0], added[1]


# --- the transition request ---------------------------------------------------


def test_build_transition_areas_groups_on_the_transition_band(ctx):
    request = build_transition_areas(StubMaps(), ctx)

    assert isinstance(request, ee.Dictionary)
    deref, graph, args = _sole_call(request, "Image.reduceRegion")

    # run_15_3_1.py:227 -- one group, on band index 1, named "lc_comb"
    assert _reducer_groups(deref, args) == ([(1, "lc_comb")], "Reducer.sum")

    # :224 -- pixelArea / 10000 is band 0, the masked transition band is band 1
    image = deref(args["image"])
    assert _spine_functions(image, deref, _RECEIVER_ARG) == [
        "Image.addBands",
        "Image.divide",
        "Image.pixelArea",
    ]
    assert _added_bands(deref, graph, image) == [{"transition"}]
    assert count_calls(request, "Image.selfMask") == 1
    assert _divide_constant(deref, image) == 10000  # m2 -> hectares

    # :228-232
    assert _call(deref(args["geometry"]))["functionName"] == "Geometry.bounds"
    assert _constant(deref, args["scale"]) == 300
    assert _constant(deref, args["maxPixels"]) == 1e13
    assert _constant(deref, args["bestEffort"]) is True
    assert _constant(deref, args["tileScale"]) == 2


def test_build_transition_areas_reduces_at_the_context_scale():
    """:229 passes model.scale; the port passes ctx.analysis_scale, not a constant."""
    deref, _, args = _sole_call(
        build_transition_areas(StubMaps(), make_ctx(250)), "Image.reduceRegion"
    )
    assert _constant(deref, args["scale"]) == 250


# --- the areas-by-land-cover request ------------------------------------------


def test_build_areas_by_land_cover_groups_twice_and_selects_the_stats_band(ctx):
    request = build_areas_by_land_cover(StubMaps(), ctx, layer=IndicatorLayer.INDICATOR_15_3_1)

    assert isinstance(request, ee.Dictionary)
    deref, _graph, args = _sole_call(request, "Image.reduceRegion")

    # :274 -- group(1, "lc") wrapped by group(2, "indicator"); the outer one is the
    # one the payload nests on, which is why the order and not just the set matters
    assert _reducer_groups(deref, args) == ([(2, "indicator"), (1, "lc")], "Reducer.sum")

    # :268-271 -- area, then LAND COVER, then the indicator. Those positions are what
    # groupField 1 and 2 name, so a swapped pair transposes the whole table.
    image = deref(args["image"])
    assert _spine_functions(image, deref, _RECEIVER_ARG) == [
        "Image.addBands",
        "Image.addBands",
        "Image.divide",
        "Image.pixelArea",
    ]
    indicator, landcover = _operand_selections(request)
    assert landcover == {"start"}
    assert indicator == set()  # :446-447 selects no band for the 15.3.1 layer
    assert count_calls(request, "Image.selfMask") == 0  # unlike :224, no self-mask here

    # :275-279
    assert _call(deref(args["geometry"]))["functionName"] == "Geometry.bounds"
    assert _constant(deref, args["scale"]) == 300
    assert _constant(deref, args["maxPixels"]) == 1e13
    assert _constant(deref, args["bestEffort"]) is True
    assert _constant(deref, args["tileScale"]) == 2


def test_build_areas_by_land_cover_always_counts_against_the_start_classes():
    """compute_stats_by_lc's `select_landcover` (:253) is only ever left at "start",
    and its label mapping at :266 is keyed on the start vocabulary regardless."""
    for layer in IndicatorLayer:
        _, landcover = _operand_selections(
            build_areas_by_land_cover(StubMaps(), make_ctx(), layer=layer)
        )
        assert landcover == {"start"}, layer


@pytest.mark.parametrize(
    "layer,stats_band",
    [
        (IndicatorLayer.PRODUCTIVITY_STATE, "state_5_levels"),
        (IndicatorLayer.PRODUCTIVITY_TREND, "trajectory_5_levels"),
    ],
)
def test_productivity_state_and_trend_statistics_use_the_five_level_band(layer, stats_band):
    """run_15_3_1.py:437-442 counts state and trend on their 5-level bands."""
    request = build_areas_by_land_cover(StubMaps(), make_ctx(), layer=layer)

    indicator, landcover = _operand_selections(request)
    assert indicator == {stats_band}

    # The 3-class export band is on the very same image -- it appears in the
    # graph, under the .rename() that put it there -- and is deliberately not what
    # gets counted. Both halves matter: without the first, "not selected" would also
    # be satisfied by an image that never carried the band at all.
    export_band = _export_layers()[layer].band
    assert export_band != stats_band
    assert export_band in _renamed_bands(request)
    assert export_band not in indicator
    assert export_band not in landcover


def test_each_statistics_table_lives_in_the_module_the_docs_send_readers_to():
    """The split is pinned, not just described.

    ``_STATS_BAND`` belongs beside the request that selects it, ``_STATS_LABELS``
    beside the decoder that applies it -- and it has to stay there, because
    ``decode.py`` is on ``tests/test_isolation.py``'s ee-freedom roster and importing
    ``requests`` would drag ``ee`` into it. ``sdg1531/engine/indicator.py``'s
    docstrings send the parity harness to these two modules, and that prose has
    already drifted once (it named ``stats/requests.py`` for both), so the fact it
    describes is asserted here rather than trusted.
    """
    assert "_STATS_BAND" in vars(requests_module)
    assert "_STATS_LABELS" not in vars(requests_module)
    assert "_STATS_LABELS" in vars(decode_module)
    assert "_STATS_BAND" not in vars(decode_module)


def test_both_statistics_tables_match_the_legacy_branch_for_branch():
    """``_STATS_BAND`` and ``_STATS_LABELS`` are checked against the legacy SOURCE.

    Re-reading the tables to test them would be circular -- a typo'd band would agree
    with itself. :func:`_legacy_stats_vocabulary` parses
    ``indicator_n_category_label`` (run_15_3_1.py:425-450) instead, so this fails on
    any entry that does not match the branch it claims to transcribe.
    """
    legacy = _legacy_stats_vocabulary()

    assert set(legacy) == set(IndicatorLayer)
    assert dict(_STATS_BAND) == {layer: band for layer, (band, _) in legacy.items()}
    assert dict(_STATS_LABELS) == {
        layer: _LEGACY_LABEL_TABLES[table] for layer, (_, table) in legacy.items()
    }


def test_every_indicator_layer_has_a_statistics_band_mapping():
    """All seven layers are in ``_STATS_BAND``, and each request selects exactly it.

    ``indicator_n_category_label``'s seven-branch chain (:427-448) had no ``else``,
    so an unrecognised name left both locals unbound; the table is total instead.
    Which band each entry should hold is
    :func:`test_both_statistics_tables_match_the_legacy_branch_for_branch`'s job;
    this one pins that the request actually selects it.
    """
    assert set(_STATS_BAND) == set(IndicatorLayer)

    for layer in IndicatorLayer:
        request = build_areas_by_land_cover(StubMaps(), make_ctx(), layer=layer)
        assert isinstance(request, ee.Dictionary)
        band = _STATS_BAND[layer]
        indicator, _ = _operand_selections(request)
        assert indicator == (set() if band is None else {band}), layer


def test_the_statistics_vocabulary_deliberately_differs_from_the_export_vocabulary():
    """The engine's export band/legend and this task's statistics band/legend must NOT
    be unified: for trend and state the legacy counted six classes off a 5-level band
    (:437-442) while the port exports three off a separate band. Collapsing the two
    tables would silently republish four-category statistics.
    """
    export = _export_layers()

    for layer in (IndicatorLayer.PRODUCTIVITY_TREND, IndicatorLayer.PRODUCTIVITY_STATE):
        assert _STATS_BAND[layer] != export[layer].band, layer
        assert _STATS_BAND[layer] == f"{export[layer].band}_5_levels", layer
        assert _STATS_LABELS[layer] != export[layer].labels, layer
        assert len(_STATS_LABELS[layer]) == 6, layer
        assert len(export[layer].labels) == 4, layer

    # the other five agree, and that agreement is asserted rather than assumed: it is
    # what makes the two rows above a deliberate exception and not a general drift
    for layer in IndicatorLayer:
        if layer in (IndicatorLayer.PRODUCTIVITY_TREND, IndicatorLayer.PRODUCTIVITY_STATE):
            continue
        assert _STATS_LABELS[layer] == export[layer].labels, layer
        assert _STATS_BAND[layer] in (None, export[layer].band), layer


# parameter/matrix.py:30-47, the four dicts `indicator_n_category_label` names.
# ``sdg1531.tables`` retyped them; this is the name each legacy branch refers to them by.
_LEGACY_LABEL_TABLES = {
    "degradation_class": DEGRADATION_LABELS,
    "prod_trend_5_class": PROD_TREND_5_LABELS,
    "prod_state_5_class": PROD_STATE_5_LABELS,
    "prod_performance_class": PROD_PERFORMANCE_LABELS,
}


def _legacy_stats_vocabulary():
    """``{IndicatorLayer: (selected band or None, pm table name)}``, read by AST.

    Parses ``indicator_n_category_label`` (run_15_3_1.py:425-450) out of the legacy
    SOURCE -- it is never imported, which would pull ipyvuetify in. Each branch is
    ``indicator = model.<attr>`` or ``model.<attr>.select("<band>")`` followed by
    ``cat_labels = pm.<table>``, and ``<attr>`` is exactly an ``IndicatorLayer``
    value (the trait names of indicator_model.py:272-278).

    Strict on purpose: an unrecognised branch raises rather than being skipped
    silently, the rule tools/extract_legacy_tables.py follows. A lenient walk that
    quietly dropped a branch would make the caller's equality assertion vacuous for
    that layer.
    """
    source = (REPO_ROOT / "component" / "scripts" / "run_15_3_1.py").read_text()
    module = ast.parse(source)
    functions = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "indicator_n_category_label"
    ]
    assert len(functions) == 1, "indicator_n_category_label is not where it was"

    body = [n for n in functions[0].body if not isinstance(n, ast.Expr)]
    assert len(body) == 2, "expected one if/elif chain and one return"
    chain, _return = body
    assert isinstance(chain, ast.If)

    out = {}
    while True:
        assert isinstance(chain.test, ast.Compare), ast.dump(chain.test)
        out.update([_legacy_branch(chain.body)])
        if not chain.orelse:
            return out
        assert len(chain.orelse) == 1, "the chain has an else the walk does not model"
        chain = chain.orelse[0]
        assert isinstance(chain, ast.If), ast.dump(chain)


def _legacy_branch(statements):
    """One ``(layer, (band, table))`` pair out of a branch body."""
    assert len(statements) == 2, ast.dump(ast.Module(body=statements, type_ignores=[]))
    indicator, labels = statements
    assert isinstance(indicator, ast.Assign) and isinstance(labels, ast.Assign)

    value = indicator.value
    if isinstance(value, ast.Call):  # model.<attr>.select("<band>")
        assert isinstance(value.func, ast.Attribute) and value.func.attr == "select"
        assert len(value.args) == 1 and isinstance(value.args[0], ast.Constant)
        band = value.args[0].value
        source = value.func.value
    else:  # model.<attr>, counted on every band it carries
        band = None
        source = value
    assert isinstance(source, ast.Attribute), ast.dump(source)
    assert isinstance(source.value, ast.Name) and source.value.id == "model"

    table = labels.value
    assert isinstance(table, ast.Attribute)
    assert isinstance(table.value, ast.Name) and table.value.id == "pm"
    assert table.attr in _LEGACY_LABEL_TABLES, table.attr

    return IndicatorLayer(source.attr), (band, table.attr)


def _export_layers():
    """The map/export vocabulary, read off a real ``IndicatorMaps``."""
    image = ee.Image.constant(1)
    maps = IndicatorMaps(
        resolved=resolve(default_spec()),
        land_cover=LandCoverMaps(stack=image),
        soc=image,
        productivity=image,
        productivity_trend=image,
        productivity_state=image,
        productivity_performance=image,
        indicator=image,
    )
    return maps.layers()


# --- the zonal request --------------------------------------------------------


def test_build_zonal_areas_returns_a_mapped_collection():
    zones = make_zones()

    request = build_zonal_areas(StubMaps(), zones, scale=100)

    assert isinstance(request, ee.FeatureCollection)
    assert count_calls(request, "Collection.map") == 1
    assert count_calls(request, "If") == 1  # :526-531 guards the empty group list
    assert count_calls(request, "Element.setMulti") == 1  # :533 feature.set(new_props)

    deref, _graph, args = _sole_call(request, "Image.reduceRegion")
    # :502-505 -- one group on band index 1, named "class"
    assert _reducer_groups(deref, args) == ([(1, "class")], "Reducer.sum")
    # :506-509 -- the FEATURE's geometry, not the AOI bounds
    assert _call(deref(args["geometry"]))["functionName"] == "Feature.geometry"
    assert _constant(deref, args["scale"]) == 100
    assert _constant(deref, args["maxPixels"]) == 1e13
    assert _constant(deref, args["tileScale"]) == 1.0

    # :495 -- the value raster is selected by INDEX, so any single band works
    select_args = _sole_call(request, "Image.select")[2]
    assert _scalar_list_arg(deref(select_args["bandSelectors"]), deref) == [0]

    # :519-520 -- key spelling and the m2 -> km2 denominator
    format_args = _sole_call(request, "Number.format")[2]
    assert _constant(deref, format_args["pattern"]) == "Class_%d"
    divide_args = _sole_call(request, "Number.divide")[2]
    assert _constant(deref, divide_args["right"]) == 1000000


def test_build_zonal_areas_uses_the_scale_it_is_given():
    zones = make_zones()
    deref, _, args = _sole_call(
        build_zonal_areas(StubMaps(), zones, scale=300), "Image.reduceRegion"
    )
    assert _constant(deref, args["scale"]) == 300


def test_build_zonal_areas_counts_the_indicator_layer():
    """:330 passes model.indicator_15_3_1, not one of the sub-indicators."""
    zones = make_zones()
    deref, graph, args = _sole_call(
        build_zonal_areas(StubMaps(), zones, scale=300), "Image.reduceRegion"
    )
    added = _added_bands(deref, graph, deref(args["image"]))
    assert added == [set()]  # selected by index, so no band NAME appears
    renamed = {
        name
        for node in _walk(deref(args["image"]), deref, graph)
        if (_call(node) or {}).get("functionName") == "Image.rename"
        for name in _string_list_arg(deref(_call(node)["arguments"]["names"]), deref)
    }
    assert renamed == {"indicator_15_3_1"}


# --- the two asset probes -----------------------------------------------------


def test_build_distinct_pixel_values_and_band_names_are_lists():
    distinct = build_distinct_pixel_values("users/x/asset")
    names = build_band_names("users/x/asset")

    assert isinstance(distinct, ee.List)
    assert isinstance(names, ee.List)

    # :416-420 -- a frequency histogram over the image's OWN geometry, best effort
    assert count_calls(distinct, "Reducer.frequencyHistogram") == 1
    assert count_calls(distinct, "Dictionary.keys") == 1
    assert _loaded_asset_ids(distinct) == {"users/x/asset"}
    deref, _, args = _sole_call(distinct, "Image.reduceRegion")
    assert _call(deref(args["geometry"]))["functionName"] == "Image.geometry"
    assert _constant(deref, args["bestEffort"]) is True
    assert "maxPixels" not in args  # :418-420 passes none, unlike the three area reducers

    # the band-name probe is just bandNames(); it must not reduce anything
    assert count_calls(names, "Image.bandNames") == 1
    assert count_calls(names, "Image.reduceRegion") == 0
    assert _loaded_asset_ids(names) == {"users/x/asset"}


# --- the constants whose Python TYPE is load-bearing ---------------------------
#
# `int` and `float` are DIFFERENT serialized graphs and the parity harness diffs the string:
# `json.dumps` writes 10000000000000.0 for the float and 10000000000000 for the int.
# `assert x == 1e13` cannot see that, because `1 == 1.0` in Python -- so every
# assertion above that compares a constant with `==` is blind to its type, and every
# numeric constant this module puts into a graph is pinned below AS JSON instead,
# which carries the type. Only the constants this module OWNS are listed; `scale` is
# a pass-through whose type belongs to the caller.


def _pinned_constants(request):
    """`{name: json}` for every constant `requests.py` chose, in one request."""
    deref, _graph, args = _sole_call(request, "Image.reduceRegion")
    pinned = {
        key: json.dumps(_constant(deref, args[key]))
        for key in ("maxPixels", "tileScale")
        if key in args
    }
    if "Image.divide" in _spine_functions(deref(args["image"]), deref, _RECEIVER_ARG):
        pinned["area divisor"] = json.dumps(_divide_constant(deref, deref(args["image"])))
    return pinned


def test_the_two_area_reducers_keep_the_legacy_constant_types():
    """run_15_3_1.py:230/:276 pass the FLOAT 1e13, :232/:279 the INT 2, :224/:269 the
    INT 10000. A float `tileScale` or divisor is a real serialized difference."""
    for request in (
        build_transition_areas(StubMaps(), make_ctx()),
        build_areas_by_land_cover(StubMaps(), make_ctx(), layer=IndicatorLayer.SOC),
    ):
        assert _pinned_constants(request) == {
            "maxPixels": "10000000000000.0",
            "tileScale": "2",
            "area divisor": "10000",
        }


def test_the_zonal_reducer_keeps_the_legacy_constant_types():
    """:508 passes the FLOAT 1e13 and :335 the FLOAT 1.0 -- the tile scale is a float
    only because the call site spells it ``1.0``, which next to ``_TILE_SCALE = 2``
    reads like a typo and is exactly what makes it worth pinning. :520's denominator
    is an int."""
    request = build_zonal_areas(StubMaps(), make_zones(), scale=300)

    assert _pinned_constants(request) == {
        "maxPixels": "10000000000000.0",
        "tileScale": "1.0",
    }
    deref, _graph, divide_args = _sole_call(request, "Number.divide")
    assert json.dumps(_constant(deref, divide_args["right"])) == "1000000"
