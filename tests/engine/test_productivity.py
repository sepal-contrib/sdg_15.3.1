"""Graph-shape tests for sdg1531.engine.productivity (legacy productivity.py)."""

from __future__ import annotations

import json

import ee
import pytest

from sdg1531.catalog import z_coefficient
from sdg1531.engine.productivity import (
    _LCEU_BUILDERS,
    _TRAJECTORY_BUILDERS,
    build_lc_ecological_units,
    build_performance,
    build_productivity,
    build_state,
    build_trajectory,
)
from sdg1531.enums import Lceu, Trajectory
from sdg1531.errors import SpecError
from sdg1531.spec import Period
from sdg1531.truth_table import PRODUCTIVITY_GPGV1, PRODUCTIVITY_GPGV2
from tests.engine.conftest import make_resolved

GAES = "users/amitghosh/sdg_module/fao/GAES_L4"

# The three productivity periods, deliberately DISTINCT and deliberately of two
# different lengths. conftest's make_resolved gives trend, state and performance
# the same Period(2001, 2015), which makes WHICH period a builder reads
# unobservable: build_state reading `r.trend` builds the right-shaped graph over
# the wrong years and stays green. Task 10's defaults are left alone -- its suite
# is green against them -- so every builder test here passes these instead.
TREND = Period(2004, 2010)
STATE = Period(2001, 2015)
PERFORMANCE = Period(2006, 2012)

# A constant no other stand-in uses. _restrend and _rain_use_efficiency_trend
# take the vi and climate collections as separate arguments and build a valid
# graph if they are exchanged -- `ee` is lazy and nothing checks a band name --
# so the two stand-ins have to be tellable apart inside the encoded graph.
CLIMATE_MARKER = -12345.0


def resolved_spec(**overrides):
    """make_resolved with the three productivity periods set to distinct windows."""
    periods = {"trend": TREND, "state": STATE, "performance": PERFORMANCE}
    return make_resolved(**{**periods, **overrides})


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


# --- reference-resolving graph walks ----------------------------------------
#
# Deliberately duplicated in spirit from test_integration.py rather than hoisted
# into conftest.py: that file is Task 10's and is shared by Tasks 11-17, and the
# two files need different slices of the walk. What both need is the same
# awareness -- `ee.serializer.encode()` hoists a repeated value into the
# `values` registry and points every use of it at that entry via
# `{"valueReference": K}`, so anything that reads an ARGUMENT's value (rather
# than merely noting a substring) has to resolve the indirection first.


def _deref_for(obj):
    """Return `(deref, graph)` for `obj`'s encoded graph."""
    graph = ee.serializer.encode(obj)
    values = graph.get("values", {})

    def deref(node):
        while isinstance(node, dict) and set(node) == {"valueReference"}:
            node = values[node["valueReference"]]
        return node

    return deref, graph


def _call(node):
    """The `functionInvocationValue` dict of `node`, or None."""
    if isinstance(node, dict):
        call = node.get("functionInvocationValue")
        if isinstance(call, dict):
            return call
    return None


def _walk(node, deref, graph):
    """Yield every resolved node reachable from `node`.

    A `.map()`/`.reduce()` callback body is a bare string key into `values`
    rather than a `{"valueReference": ...}` wrapper, so it is followed
    explicitly -- the second indirection test_integration.py documents.
    """
    values = graph.get("values", {})
    stack = [node]
    seen: set[int] = set()
    while stack:
        current = deref(stack.pop())
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)
        yield current
        if isinstance(current, dict):
            body = current.get("functionDefinitionValue")
            if isinstance(body, dict) and body.get("body") in values:
                stack.append(values[body["body"]])
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def _root(obj):
    """`(deref, graph, result node)` for `obj`."""
    deref, graph = _deref_for(obj)
    return deref, graph, deref({"valueReference": graph["result"]})


# The argument each node carries its receiver in: `Image.uint8` spells it
# `value`, the other two `input` (verified against the encoder).
_RECEIVER_ARG = {"Image.where": "input", "Image.rename": "input", "Image.uint8": "value"}


def _image_constant(node, deref):
    """The scalar behind an `ee.Image(k)` argument node, or None."""
    call = _call(node)
    if call is not None and call.get("functionName") == "Image.constant":
        inner = deref(call.get("arguments", {}).get("value", {}))
        if isinstance(inner, dict):
            return inner.get("constantValue")
    return None


def _string_list_arg(arg, deref):
    """The strings behind a `names`/`bandSelectors` argument.

    It is `{"constantValue": [...]}` when inlined and `{"arrayValue":
    {"values": [...]}}` when the list -- or one of its elements -- is itself
    hoisted into `values`, so both are resolved; the same handling
    test_integration.py's `_renamed_bands` needs.
    """
    if not isinstance(arg, dict):
        return []
    if isinstance(arg.get("constantValue"), list):
        items = arg["constantValue"]
    else:
        items = arg.get("arrayValue", {}).get("values", [])
    names = []
    for item in items:
        value = deref(item)
        if isinstance(value, dict):
            value = value.get("constantValue")
        if isinstance(value, str):
            names.append(value)
    return names


def _select_bands_of(node, deref):
    """The band names of an `Image.select` node, or None if it is not one."""
    call = _call(node)
    if call is None or call.get("functionName") != "Image.select":
        return None
    return _string_list_arg(deref(call.get("arguments", {}).get("bandSelectors", {})), deref)


def _selected_bands(obj):
    """Every band name passed to `.select(...)` anywhere in the graph."""
    deref, graph, root = _root(obj)
    names = set()
    for current in _walk(root, deref, graph):
        names.update(_select_bands_of(current, deref) or [])
    return names


def _renamed_bands(obj):
    """Every band name passed to `.rename(...)` anywhere in the graph."""
    deref, graph, root = _root(obj)
    names = set()
    for current in _walk(root, deref, graph):
        call = _call(current)
        if call is None or call.get("functionName") != "Image.rename":
            continue
        names.update(_string_list_arg(deref(call.get("arguments", {}).get("names", {})), deref))
    return names


def _where_calls(obj, branches=()):
    """The `Image.where` calls on one spine of `obj`, innermost first, and `deref`.

    The spine is followed through each node's RECEIVER argument, so the order
    comes from the graph's nesting rather than from a count: CSE cannot collapse
    it, and swapping two `.where()` lines reorders what comes back. `.where()`
    calls sitting in other branches (an operand's own chain) are not on it.

    `branches` names arguments to descend through before the walk starts.
    `build_trajectory` and `build_state` return `Image.addBands`, which is not a
    receiver node, so their two ladders are reached with `("dstImg",)` -- the
    image bands were added TO, i.e. the 5-level chain -- and `("srcImg",)`, the
    3-level chain that was added to it.

    Raises rather than returning `[]` when the walk finds no `.where()` at all:
    an equality assertion written against a mistakenly-empty expectation would
    otherwise pass vacuously.
    """
    deref, _graph, node = _root(obj)
    for name in branches:
        call = _call(node)
        if call is None or name not in call.get("arguments", {}):
            raise AssertionError(
                f"cannot descend into {name!r}: the head is "
                f"{call.get('functionName') if call else type(node).__name__}"
            )
        node = deref(call["arguments"][name])

    calls = []
    while True:
        call = _call(node)
        name = call.get("functionName") if call else None
        if name not in _RECEIVER_ARG:
            break
        if name == "Image.where":
            calls.append(call)
        node = deref(call["arguments"][_RECEIVER_ARG[name]])

    if not calls:
        raise AssertionError(
            f"no Image.where on this spine (branches={branches!r}); the walk stopped at "
            f"{(_call(node) or {}).get('functionName')!r}"
        )
    return deref, list(reversed(calls))


def _where_chain(obj, branches=()):
    """`[(test function name, assigned value), ...]` for one where spine."""
    deref, calls = _where_calls(obj, branches)
    steps = []
    for call in calls:
        test = _call(deref(call["arguments"]["test"]))
        steps.append(
            (
                test.get("functionName") if test is not None else None,
                _image_constant(deref(call["arguments"]["value"]), deref),
            )
        )
    return steps


def _test_comparisons(node, deref):
    """`[(comparison function, threshold), ...]` for a where-test, left to right.

    Recurses through `Image.and`/`Image.or` so a two-sided band reports both of
    its comparisons, and reads only the RIGHT operand of each comparison -- the
    left is the z-score subtree, whose own constants are not thresholds.

    Reading the OPERATOR and not merely the constant is the point: a two-sided
    step's head node is `Image.and`, so a helper that stopped there would treat
    the comparison as a leaf and `z_score.lt(-1.28).And(...)` ->
    `z_score.gt(-1.28).And(...)` -- a direction flip that moves class 2 onto
    essentially every pixel above -1.28 -- would be invisible.
    """
    call = _call(node)
    if call is None:
        return []
    args = call.get("arguments", {})
    name = call.get("functionName")
    if name in ("Image.and", "Image.or"):
        return _test_comparisons(deref(args["image1"]), deref) + _test_comparisons(
            deref(args["image2"]), deref
        )
    constant = _image_constant(deref(args.get("image2", {})), deref)
    return [] if constant is None else [(name, constant)]


def _where_tests(obj, branches=()):
    """`[((comparison, threshold), ...), ...]` for one where spine, innermost first.

    `_where_chain` reads each step's head function -- the combinator -- and the
    class it assigns; this reads the comparison and the threshold on each side
    of that head. Between them they pin the step order, the combinator, every
    comparison operator, every threshold and every assigned class of a
    classification ladder.
    """
    deref, calls = _where_calls(obj, branches)
    return [tuple(_test_comparisons(deref(call["arguments"]["test"]), deref)) for call in calls]


def _windows_in(node, deref, graph):
    """`{(field, minValue, maxValue)}` for the `Filter.rangeContains` nodes
    under `node`."""
    windows = set()
    for current in _walk(node, deref, graph):
        call = _call(current)
        if call is None or call.get("functionName") != "Filter.rangeContains":
            continue
        args = call.get("arguments", {})
        windows.add(
            tuple(
                deref(args[key]).get("constantValue") for key in ("field", "minValue", "maxValue")
            )
        )
    return windows


def _range_windows(obj):
    """Every `Filter.rangeContains` window in the graph."""
    deref, graph, root = _root(obj)
    return _windows_in(root, deref, graph)


def _stddev_windows(obj):
    """The `Filter.rangeContains` windows feeding a `Reducer.stdDev` reduction.

    `_range_windows` alone cannot tell the recent window from the baseline one:
    exchanging the two filters leaves the SET of windows identical. Only the
    baseline period is reduced with stdDev (productivity.py:217-222), so
    reading the window under that reduction is what pins which is which.
    """
    deref, graph, root = _root(obj)
    for current in _walk(root, deref, graph):
        call = _call(current)
        if call is None or call.get("functionName") != "ImageCollection.reduce":
            continue
        reducer = _call(deref(call.get("arguments", {})["reducer"]))
        if reducer is None or reducer.get("functionName") != "Reducer.stdDev":
            continue
        return _windows_in(call["arguments"]["collection"], deref, graph)
    return set()


def _year_bounds(obj):
    """`{(wrapper, comparison, field, value)}` for every year bound in the graph.

    `ee.Filter.gte(f, v)` encodes as `Filter.not(Filter.lessThan(f, v))` and
    `.lte(f, v)` as `Filter.not(Filter.greaterThan(f, v))`, so those two names
    are where a bound actually lands -- but the NEGATION is what separates `gte`
    from `lt` and `lte` from `gt`. Reading the comparison leaf alone cannot tell
    them apart, so `wrapper` records whether the leaf was inside a `Filter.not`:
    `("Filter.not", "Filter.greaterThan", "year", 2012)` is `lte("year", 2012)`,
    while the same tuple with `wrapper=None` would be `gt("year", 2012)` -- a
    direction flip that selects the empty set rather than the period.
    """
    deref, graph, root = _root(obj)
    negated: set[int] = set()
    comparisons = []
    for current in _walk(root, deref, graph):
        call = _call(current)
        name = call.get("functionName") if call else None
        if name == "Filter.not":
            negated.add(id(deref(call["arguments"]["filter"])))
        elif name in ("Filter.lessThan", "Filter.greaterThan"):
            args = call["arguments"]
            comparisons.append(
                (
                    current,
                    name,
                    deref(args["leftField"]).get("constantValue"),
                    deref(args["rightValue"]).get("constantValue"),
                )
            )
    # resolved after the walk, not during it: a node is yielded before its
    # children, so the wrapper is always seen first, but deferring keeps that
    # from being load-bearing.
    return {
        ("Filter.not" if id(node) in negated else None, name, field, value)
        for node, name, field, value in comparisons
    }


def _subtract_operand_heads(obj):
    """`[(image1 function, image2 function), ...]` for every `Image.subtract`."""
    deref, graph, root = _root(obj)
    pairs = []
    for current in _walk(root, deref, graph):
        call = _call(current)
        if call is None or call.get("functionName") != "Image.subtract":
            continue
        args = call["arguments"]
        pairs.append(
            tuple(
                (_call(deref(args[key])) or {}).get("functionName") for key in ("image1", "image2")
            )
        )
    return sorted(pairs)


def _multiply_select_operands(obj):
    """`[(left band, right band), ...]` for every `Image.multiply` whose BOTH
    operands are band selects.

    Excludes `.multiply(coefficient)`, whose right operand is a constant.
    """
    deref, graph, root = _root(obj)
    pairs = []
    for current in _walk(root, deref, graph):
        call = _call(current)
        if call is None or call.get("functionName") != "Image.multiply":
            continue
        args = call["arguments"]
        bands = [_select_bands_of(deref(args[key]), deref) for key in ("image1", "image2")]
        if all(band is not None and len(band) == 1 for band in bands):
            pairs.append((bands[0][0], bands[1][0]))
    return sorted(pairs)


def _image_constants(obj):
    """Every `ee.Image(k)` constant in the graph."""
    deref, graph, root = _root(obj)
    return _constants_in(root, deref, graph)


def _constants_in(node, deref, graph):
    """Every `ee.Image(k)` constant under `node`."""
    values = set()
    for current in _walk(node, deref, graph):
        constant = _image_constant(current, deref)
        if constant is not None:
            values.add(constant)
    return values


def _constants_under_select(obj, band):
    """The `ee.Image(k)` constants of the collections `.select(band)` is applied to.

    `collection.select(band)` compiles to a `Collection.map` over an
    `Image.select`, so the collection being selected FROM is the map's
    `collection` argument. Which stand-in turns up there is what distinguishes
    `_restrend(start, end, vi, climate)` from the same call with its two
    collections exchanged.
    """
    deref, graph, root = _root(obj)
    values = graph.get("values", {})
    found = set()
    for current in _walk(root, deref, graph):
        call = _call(current)
        if call is None or call.get("functionName") != "Collection.map":
            continue
        args = call.get("arguments", {})
        base = deref(args.get("baseAlgorithm", {}))
        definition = base.get("functionDefinitionValue") if isinstance(base, dict) else None
        if not isinstance(definition, dict):
            continue
        if _select_bands_of(values.get(definition.get("body")), deref) != [band]:
            continue
        found |= _constants_in(args["collection"], deref, graph)
    return found


def _loaded_assets_in(node, deref, graph):
    """Every asset id loaded under `node`."""
    ids = set()
    for current in _walk(node, deref, graph):
        call = _call(current)
        if call is None or call.get("functionName") not in ("Image.load", "ImageCollection.load"):
            continue
        value = deref(call.get("arguments", {}).get("id", {}))
        if isinstance(value, dict) and isinstance(value.get("constantValue"), str):
            ids.add(value["constantValue"])
    return ids


def _addbands_operand_assets(obj):
    """`(assets under dstImg, assets under srcImg)` for the first `Image.addBands`."""
    deref, graph, root = _root(obj)
    for current in _walk(root, deref, graph):
        call = _call(current)
        if call is None or call.get("functionName") != "Image.addBands":
            continue
        args = call["arguments"]
        return tuple(_loaded_assets_in(args[key], deref, graph) for key in ("dstImg", "srcImg"))
    raise AssertionError("no Image.addBands in the graph")


def _number_sqrt_inputs(obj):
    """The constants passed to every `Number.sqrt`."""
    deref, graph, root = _root(obj)
    inputs = set()
    for current in _walk(root, deref, graph):
        call = _call(current)
        if call is None or call.get("functionName") != "Number.sqrt":
            continue
        value = deref(call.get("arguments", {}).get("input", {}))
        if isinstance(value, dict) and "constantValue" in value:
            inputs.add(value["constantValue"])
    return inputs


def fake_vi_collection() -> ee.ImageCollection:
    """A stand-in for build_vi_collection's output: band `vi`, property `year`."""
    return ee.ImageCollection(
        [ee.Image(0.1 * (year - 2000)).rename("vi").set("year", year) for year in range(2001, 2016)]
    )


def fake_climate_collection() -> ee.ImageCollection:
    """A stand-in for build_climate_collection's output: band `clim`.

    Every image carries CLIMATE_MARKER so that a builder handed this collection
    where it should have had the vi one is visible in the encoded graph.
    """
    return ee.ImageCollection(
        [ee.Image(CLIMATE_MARKER).rename("clim").set("year", year) for year in range(2001, 2016)]
    )


def trajectory_for(method: Trajectory) -> ee.Image:
    """build_trajectory over the two stand-ins, for `method`."""
    return build_trajectory(
        resolved_spec(trajectory=method), fake_vi_collection(), fake_climate_collection()
    )


def test_lceu_builders_cover_every_lceu_member():
    # productivity.py:92-116 leaves the local unbound for an unknown lceu.
    assert set(_LCEU_BUILDERS) == set(Lceu)


@pytest.mark.parametrize(
    "lceu, asset",
    [
        (Lceu.GAES, GAES),
        (Lceu.AEZ, "users/amitghosh/sdg_module/fao/aez_v9v2_CRUTS32_Hist_8110_100_avg"),
        (Lceu.HRU, "users/amitghosh/sdg_module/hru_250"),
        (Lceu.WTE, "users/amitghosh/sdg_module/wte_2020"),
    ],
)
def test_static_ecological_units_load_their_asset(lceu, asset):
    r = resolved_spec(lceu=lceu)

    assert asset in encoded(build_lc_ecological_units(r))


def test_calculated_ecological_unit_combines_soil_and_land_cover():
    r = resolved_spec(lceu=Lceu.CALCULATE, lc_year_start_esa=2001)

    img = build_lc_ecological_units(r)
    graph = encoded(img)

    # productivity.py:99-114: soil taxonomy band b0 * 100 + IPCC-reclassed LC.
    assert "OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02" in graph
    assert "users/amitghosh/sdg_module/esa/cci_landcover" in graph
    assert '"b0"' in graph
    assert count_calls(img, "Image.remap") == 1
    assert count_calls(img, "Image.multiply") == 1
    assert count_calls(img, "Image.add") == 1


def test_unknown_lceu_raises_a_spec_error():
    # productivity.py:92-116 has no else branch, so an unknown value falls
    # through and raises UnboundLocalError; spec 7 makes it explicit. A plain
    # string is used because Lceu mixes in `str`, so any real member would hash
    # equal to its own value and hit the table.
    r = resolved_spec(lceu="not_an_lceu")

    with pytest.raises(SpecError, match="land cover ecological unit"):
        build_lc_ecological_units(r)


def test_trajectory_builders_cover_every_trajectory_member():
    # productivity.py:30-51 leaves z_score unbound for an unhandled trajectory.
    assert set(_TRAJECTORY_BUILDERS) == set(Trajectory)


def test_unknown_trajectory_raises_a_spec_error():
    r = resolved_spec(trajectory="not_a_trajectory")

    with pytest.raises(SpecError, match="trajectory method"):
        build_trajectory(r, fake_vi_collection(), fake_climate_collection())


def test_s_res_trend_raises_a_spec_error_not_a_name_error():
    # productivity.py:42-43 raises a bare NameError from inside the chain; the
    # method is marked disabled at parameter/ui.py:35 and validate() rejects it.
    # `match` matters here: build_trajectory narrows the trend period first, so
    # a bare `raises(SpecError)` would also pass on a period error.
    r = resolved_spec(trajectory=Trajectory.S_RES_TREND)

    with pytest.raises(SpecError, match="water use efficiency"):
        build_trajectory(r, fake_vi_collection(), fake_climate_collection())


def test_build_trajectory_requires_a_resolved_trend():
    # Port-only divergence 1: the legacy would pass None into ee.Filter.
    r = resolved_spec(trend=Period(2004, None))

    with pytest.raises(SpecError, match=r"trend\.end"):
        build_trajectory(r, fake_vi_collection(), fake_climate_collection())


def test_trajectory_emits_both_bands_and_seven_where_nodes():
    img = trajectory_for(Trajectory.NDVI_TREND)
    graph = encoded(img)

    assert '"trajectory_5_levels"' in graph
    assert '"trajectory"' in graph
    # The 5-level chain has 5 wheres and the 3-level chain 3, but their first
    # node -- ee.Image(0).where(z.lt(-1.96), 1) -- is shared, and the serializer
    # collapses identical subtrees. 5 + 3 - 1 = 7.
    assert count_calls(img, "Image.where") == 7
    assert count_calls(img, "Image.uint8") == 2
    assert count_calls(img, "Image.addBands") == 1


def test_trajectory_ladders_assign_the_kendall_classes_at_the_kendall_thresholds():
    # productivity.py:54-63 (5 levels) and :65-72 (3 levels). The where COUNT
    # above says how many steps there are; it says nothing about which class
    # each step assigns or at which threshold, and a single-digit typo in these
    # eight lines changes what "degraded / at risk / stable / improving" means
    # while leaving the count -- and every band name -- untouched.
    img = trajectory_for(Trajectory.NDVI_TREND)

    assert _where_chain(img, branches=("dstImg",)) == [
        ("Image.lt", 1),
        ("Image.and", 2),
        ("Image.and", 3),
        ("Image.and", 4),
        ("Image.gt", 5),
    ]
    assert _where_tests(img, branches=("dstImg",)) == [
        (("Image.lt", -1.96),),
        (("Image.lt", -1.28), ("Image.gte", -1.96)),
        (("Image.gte", -1.28), ("Image.lte", 1.28)),
        (("Image.gt", 1.28), ("Image.lte", 1.96)),
        (("Image.gt", 1.96),),
    ]
    assert _where_chain(img, branches=("srcImg",)) == [
        ("Image.lt", 1),
        ("Image.and", 2),
        ("Image.gt", 3),
    ]
    assert _where_tests(img, branches=("srcImg",)) == [
        (("Image.lt", -1.96),),
        (("Image.gte", -1.96), ("Image.lte", 1.96)),
        (("Image.gt", 1.96),),
    ]


def test_vi_trend_multiplies_the_tau_by_the_z_coefficient():
    graph = encoded(trajectory_for(Trajectory.NDVI_TREND))

    # productivity.py:435-442: n = end - start + 1, over TREND = 2004..2010.
    assert str(z_coefficient(7)) in graph
    assert '"vi_tau"' in graph


def test_trajectory_filters_on_the_trend_period_upper_bound_only():
    # TREND is Period(2004, 2010) while STATE and PERFORMANCE are other windows,
    # so reading the wrong period moves this bound. Only the UPPER bound is
    # asserted because only the upper bound exists -- see
    # test_year_filters_silently_drop_their_lower_bound.
    img = trajectory_for(Trajectory.NDVI_TREND)

    assert _year_bounds(img) == {("Filter.not", "Filter.greaterThan", "year", 2010)}


def test_year_filters_silently_drop_their_lower_bound(ctx):
    # `ee.Filter.And` is a STATICMETHOD, so in
    # `ee.Filter.gte("year", start).And(ee.Filter.lte("year", end))` the
    # receiver is discarded: the expression encodes as `Filter.and([lte(end)])`
    # and the START bound never reaches the graph. The legacy spells it exactly
    # this way (productivity.py:430-432, :465-470, :532-537, :119-123), so D9
    # requires reproducing it -- but a later "fix" to `ee.Filter.And(gte, lte)`
    # WOULD change the graph and break parity, so it is pinned rather than left
    # to a comment. A correct fix belongs in phase 2 with a golden update.
    trajectory = trajectory_for(Trajectory.NDVI_TREND)
    performance = build_performance(resolved_spec(lceu=Lceu.GAES), ctx, fake_vi_collection())

    for img in (trajectory, performance):
        assert not [bound for bound in _year_bounds(img) if bound[1] == "Filter.lessThan"]


def test_ndvi_trend_never_touches_the_climate_collection():
    # _TRAJECTORY_BUILDERS[NDVI_TREND] passes only `vi` to _vi_trend
    # (productivity.py:30-31). Handing it `climate` instead builds a perfectly
    # valid graph, so the only thing that can catch the swap is whether the
    # climate stand-in's marker constant reaches the graph at all.
    assert CLIMATE_MARKER not in _image_constants(trajectory_for(Trajectory.NDVI_TREND))


@pytest.mark.parametrize("method", [Trajectory.P_RES_TREND, Trajectory.UE_TREND])
def test_climate_corrected_trajectories_read_vi_from_the_vi_collection(method):
    # Both methods call _ndvi_climate_merge(climate, vi) (productivity.py:473,
    # :540). Exchanging the two collections also builds cleanly -- the merge
    # would select "clim" out of the vi collection and "vi" out of the climate
    # one. `.select("vi")` is applied to the vi collection in exactly one place,
    # so the marker turning up under it means the arguments were exchanged.
    img = trajectory_for(method)

    assert CLIMATE_MARKER not in _constants_under_select(img, "vi")


def test_restrend_fits_one_unsegmented_linear_model():
    # Preserved, not fixed (spec 3): productivity.py:477-480 reduces the whole
    # trend period with a single linearFit, with no breakpoint.
    img = trajectory_for(Trajectory.P_RES_TREND)
    graph = encoded(img)

    assert count_calls(img, "Reducer.linearFit") == 1
    assert '"vi_res_tau"' in graph
    assert '"offset"' in graph
    assert '"scale"' in graph


def test_restrend_residual_is_observed_minus_predicted():
    # productivity.py:599 is ndvi_o.subtract(ndvi_p) -- OBSERVED minus predicted
    # -- while the module prose at :451 says "(Predicted - Obsedved)". The code
    # is right and the prose is wrong, so a reader who "fixes" the code to match
    # the prose flips the sign of every p_res_trend run, invisibly without
    # ground truth. image1 is the mapped image's `vi` select; image2 is the
    # modeled collection's `.first()`.
    img = trajectory_for(Trajectory.P_RES_TREND)

    assert _subtract_operand_heads(img) == [("Image.select", "Collection.first")]


def test_restrend_predicts_ndvi_as_offset_plus_scale_times_climate():
    # productivity.py:485-491, inside the .iterate() closure. The four
    # assertions above only check that offset, scale, vi_res_tau and one
    # linearFit appear SOMEWHERE in the graph; between them, `.add` ->
    # `.subtract` and `select("clim")` -> `select("vi")` are the whole
    # climate->NDVI prediction model and both survive them.
    img = trajectory_for(Trajectory.P_RES_TREND)

    # the offset + (scale * clim) sum is the only `.add()` in the restrend graph
    assert count_calls(img, "Image.add") == 1
    assert _multiply_select_operands(img) == [("scale", "clim")]


def test_rain_use_efficiency_divides_climate_by_one_thousand():
    graph = encoded(trajectory_for(Trajectory.UE_TREND))

    # productivity.py:611: clim / 1000, then vi / clim, band "ue".
    assert '"ue_tau"' in graph
    # A bare `"1000" in graph` is satisfied by any longer number containing it
    # -- a scale, a year, a projection parameter; the serializer's structured
    # constant form pins the divisor.
    assert '"constantValue": 1000}' in graph


def test_performance_reduces_with_best_effort_at_the_analysis_scale(ctx):
    # Preserved, not fixed (spec 3): productivity.py:141-145 passes
    # bestEffort=True, which silently coarsens the scale on large AOIs.
    r = resolved_spec(lceu=Lceu.GAES, analysis_scale=250)

    img = build_performance(r, ctx, fake_vi_collection())
    graph = encoded(img)

    assert '"bestEffort": {"constantValue": true}' in graph
    # Closing brace included on both: `'"scale": {"constantValue": 250'` alone
    # also matches 2500, and `'"maxPixels": {"constantValue": 1'` matches any
    # maxPixels beginning with a 1.
    assert '"scale": {"constantValue": 250}' in graph
    assert '"maxPixels": {"constantValue": 1000000000000000.0}' in graph
    assert count_calls(img, "Image.reduceRegion") == 1
    assert count_calls(img, "Reducer.percentile") == 1


def test_performance_filters_on_the_performance_period_upper_bound_only(ctx):
    # PERFORMANCE is Period(2006, 2012), distinct from TREND and STATE, so this
    # also pins that build_performance reads r.performance. Upper bound only --
    # see test_year_filters_silently_drop_their_lower_bound.
    img = build_performance(resolved_spec(lceu=Lceu.GAES), ctx, fake_vi_collection())

    assert _year_bounds(img) == {("Filter.not", "Filter.greaterThan", "year", 2012)}


def test_performance_stays_server_side_through_remap(ctx):
    # The reduceRegion result is consumed as ee.List(...).get("groups") and fed
    # back into remap; nothing is fetched. productivity.py:150-155.
    img = build_performance(resolved_spec(lceu=Lceu.GAES), ctx, fake_vi_collection())
    graph = encoded(img)

    assert '"groups"' in graph
    assert '"code"' in graph
    assert '"p90"' in graph
    assert count_calls(img, "Image.remap") == 1


def test_performance_groups_by_the_ecological_unit_not_by_ndvi(ctx):
    # productivity.py:138 is ndvi_mean.addBands(lc_eco_functional_unit_filled)
    # and :142 groups with groupField=1 -- the SECOND band. Exchanging the two
    # operands groups by NDVI and takes the 90th percentile of the unit codes:
    # it builds cleanly, keeps every count and band name, and is silently wrong.
    img = build_performance(resolved_spec(lceu=Lceu.GAES), ctx, fake_vi_collection())
    graph = encoded(img)

    dst_assets, src_assets = _addbands_operand_assets(img)
    assert dst_assets == set()  # the NDVI mean, from the stand-in collection
    assert src_assets == {GAES}  # the ecological unit raster
    # The operand order and groupField are only meaningful together: grouping by
    # band 0 reaches the same wrong answer from the other half of the pair, and
    # `Reducer.percentile == 1` counts the node without reading which percentile
    # it takes. Closing braces per this file's bare-substring discipline.
    assert '"groupField": {"constantValue": 1}' in graph
    assert '"percentiles": {"constantValue": [90]}' in graph


def test_performance_names_and_types_its_band(ctx):
    img = build_performance(resolved_spec(lceu=Lceu.GAES), ctx, fake_vi_collection())
    graph = encoded(img)

    assert '"performance"' in graph
    assert count_calls(img, "Image.uint8") == 1
    # ee.Image(-1).where(lceu, lceu); the 0 -> 0.001 guard; and the two
    # observed-ratio classes. productivity.py:133, :157, :166-172.
    assert count_calls(img, "Image.where") == 4
    assert '"constantValue": 0.001}' in graph


def test_performance_classifies_a_ratio_of_exactly_one_half_as_degraded(ctx):
    # productivity.py:166-172's two conditions OVERLAP at exactly 0.5:
    # `.gte(0.5)` assigns 2 and the LATER `.lte(0.5)` overwrites it with 1, so
    # a pixel sitting exactly on the threshold is degraded, not stable. That
    # ordering is the most behaviour-defining line in build_performance and
    # nothing else here holds it -- swapping the two `.where()` lines leaves
    # the where COUNT, every band name and every constant in the graph
    # unchanged. Walking the chain's NESTING is what makes the swap visible.
    img = build_performance(resolved_spec(lceu=Lceu.GAES), ctx, fake_vi_collection())

    assert _where_chain(img) == [("Image.gte", 2), ("Image.lte", 1)]


def test_build_performance_requires_a_resolved_performance_period(ctx):
    r = resolved_spec(lceu=Lceu.GAES, performance=Period(2006, None))

    with pytest.raises(SpecError, match=r"performance\.end"):
        build_performance(r, ctx, fake_vi_collection())


def test_state_compares_the_last_three_years_to_the_baseline():
    img = build_state(resolved_spec(), fake_vi_collection())

    # productivity.py:195-200: recent = [end-2, end], baseline = [start, end-3],
    # over STATE = 2001..2015. TREND and PERFORMANCE are different windows, so
    # this also pins that build_state reads r.state.
    assert _range_windows(img) == {("year", 2013, 2015), ("year", 2001, 2012)}
    # ... and which window is which: only the baseline is reduced with stdDev,
    # so exchanging the two filters -- which the set above cannot see -- flips
    # the sign of the z-score and fails here.
    assert _stddev_windows(img) == {("year", 2001, 2012)}


def test_state_divides_sigma_by_a_hardcoded_root_three():
    # productivity.py:224 divides by ee.Number(3).sqrt() -- a literal 3, not the
    # recent-year count. It is right only because that window happens to be
    # three years wide. Preserved, and pinned so a later "generalisation" to
    # sqrt(n) cannot land silently.
    img = build_state(resolved_spec(), fake_vi_collection())

    assert _number_sqrt_inputs(img) == {3}


def test_state_emits_both_bands_and_seven_where_nodes():
    img = build_state(resolved_spec(), fake_vi_collection())
    graph = encoded(img)

    assert '"state_5_levels"' in graph
    assert '"state"' in graph
    # Same shared-first-node arithmetic as the trajectory chains: 5 + 3 - 1.
    assert count_calls(img, "Image.where") == 7
    assert count_calls(img, "Reducer.stdDev") == 1
    assert count_calls(img, "Image.uint8") == 2


def test_state_ladders_assign_the_kendall_classes_at_the_kendall_thresholds():
    # productivity.py:228-247, the same two ladders as the trajectory ones and
    # unpinned by the where count for the same reason.
    img = build_state(resolved_spec(), fake_vi_collection())

    assert _where_chain(img, branches=("dstImg",)) == [
        ("Image.lt", 1),
        ("Image.and", 2),
        ("Image.and", 3),
        ("Image.and", 4),
        ("Image.gt", 5),
    ]
    assert _where_tests(img, branches=("dstImg",)) == [
        (("Image.lt", -1.96),),
        (("Image.lt", -1.28), ("Image.gte", -1.96)),
        (("Image.gte", -1.28), ("Image.lte", 1.28)),
        (("Image.gt", 1.28), ("Image.lte", 1.96)),
        (("Image.gt", 1.96),),
    ]
    assert _where_chain(img, branches=("srcImg",)) == [
        ("Image.lt", 1),
        ("Image.and", 2),
        ("Image.gt", 3),
    ]
    assert _where_tests(img, branches=("srcImg",)) == [
        (("Image.lt", -1.96),),
        (("Image.gte", -1.96), ("Image.lte", 1.96)),
        (("Image.gt", 1.96),),
    ]


def test_build_state_requires_a_resolved_state_period():
    r = resolved_spec(state=Period(None, 2015))

    with pytest.raises(SpecError, match=r"state\.start"):
        build_state(r, fake_vi_collection())


def fake_trajectory() -> ee.Image:
    """Stand-in for build_trajectory's output: the two trajectory bands.

    The real builder casts each band with ``.uint8()``; the stand-ins do not,
    so that every ``Image.uint8`` node in the collapse graph can only come from
    build_productivity's own terminal cast.
    """
    five_levels = ee.Image(3).rename("trajectory_5_levels")
    return five_levels.addBands(ee.Image(2).rename("trajectory"))


def fake_state() -> ee.Image:
    """Stand-in for build_state's output; uncast, for the same reason."""
    five_levels = ee.Image(3).rename("state_5_levels")
    return five_levels.addBands(ee.Image(2).rename("state"))


def fake_performance() -> ee.Image:
    """Stand-in for build_performance's output; uncast, for the same reason."""
    return ee.Image(2).rename("performance")


def _collapse(table) -> ee.Image:
    """build_productivity over the three stand-ins, for `table`."""
    return build_productivity(
        resolved_spec(productivity_table=table),
        trajectory=fake_trajectory(),
        state=fake_state(),
        performance=fake_performance(),
    )


def test_productivity_collapse_emits_one_where_per_rule():
    img = _collapse(PRODUCTIVITY_GPGV2)
    graph = encoded(img)

    # productivity.py:252-334 -- 18 rules, all distinct conditions.
    assert len(PRODUCTIVITY_GPGV2.rules) == 18
    assert count_calls(img, "Image.where") == 18
    assert '"productivity"' in graph
    assert count_calls(img, "Image.uint8") == 1


def test_productivity_collapse_assigns_each_rule_s_value_in_table_order():
    # The count above is a post-CSE node count and says nothing about ORDER or
    # about WHICH class each rule assigns; the chain's nesting says both. This
    # is what ties the emitted graph to the table data (spec D9: same nodes, in
    # the same order), and it fails if any cell of the table is edited, if two
    # rules are transposed, or if a rule is dropped.
    img = _collapse(PRODUCTIVITY_GPGV2)

    assert [value for _test, value in _where_chain(img)] == [
        rule.value for rule in PRODUCTIVITY_GPGV2.rules
    ]


def test_productivity_selects_the_three_input_bands_by_name():
    img = _collapse(PRODUCTIVITY_GPGV2)

    # productivity.py:253-255 selects one band from each input image once and
    # reuses it, so the collapse carries exactly three Image.select nodes.
    # Selecting does not prune the parent graph -- the 5-level rename nodes stay
    # reachable through the selected image -- so this reads WHICH bands the
    # selects name rather than looking for those names in the graph, where the
    # stand-ins' own `.rename()` calls put them regardless.
    assert count_calls(img, "Image.select") == 3
    assert _selected_bands(img) == {"trajectory", "state", "performance"}


@pytest.mark.parametrize("table", [PRODUCTIVITY_GPGV2, PRODUCTIVITY_GPGV1])
def test_the_collapse_band_matches_the_table_s_own_band(table):
    # build_productivity passes the literal "productivity" (productivity.py:331)
    # rather than reading r.productivity_table.band, so TruthTable.band goes
    # unread on this path and editing it would silently do nothing. The literal
    # is brief-mandated and matches the legacy; this keeps the two from drifting.
    assert table.band in _renamed_bands(_collapse(table))


def test_the_two_lookup_tables_build_different_graphs():
    # productivity.py:252-334 vs :337-419 differ in exactly two cells.
    v2 = _collapse(PRODUCTIVITY_GPGV2)
    v1 = _collapse(PRODUCTIVITY_GPGV1)

    assert encoded(v1) != encoded(v2)
    # ... at rules 4 and 9 (1-based), and nowhere else: byte inequality alone
    # would also pass if the two graphs differed for some unrelated reason.
    v1_values = [value for _test, value in _where_chain(v1)]
    v2_values = [value for _test, value in _where_chain(v2)]
    assert [i for i, (a, b) in enumerate(zip(v1_values, v2_values, strict=True)) if a != b] == [
        3,
        8,
    ]
